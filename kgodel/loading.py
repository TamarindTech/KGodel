"""Bounded local module loading; text parsing and checkpoint loading remain pure."""

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath

from .model import KGodelError, Program
from .objects import ObjectSpace
from .parser import Parser


@dataclass(frozen=True)
class SourceFile:
    path: str
    declaration: str
    name: str
    sha256: str
    bytes: int
    includes: tuple[str, ...]

    def as_dict(self):
        return {"path": self.path, "declaration": self.declaration, "name": self.name,
                "sha256": self.sha256, "bytes": self.bytes, "includes": list(self.includes)}


@dataclass(frozen=True)
class LoadedProject:
    program: Program
    root: Path
    entry: str
    sources: tuple[SourceFile, ...]

    def as_dict(self):
        return {"format": "kgodel-project", "version": 1, "root": str(self.root),
                "entry": self.entry, "agent": self.program.name,
                "files": [source.as_dict() for source in self.sources],
                "total_bytes": sum(source.bytes for source in self.sources)}


def load_project(filename: str | Path, *, max_files: int = 64, max_depth: int = 16,
                 max_file_bytes: int = 1024 * 1024, max_bytes: int = 8 * 1024 * 1024) -> LoadedProject:
    """Read one agent and its module graph below the entry file's resolved directory.

    Files are expanded at their first include, depth first. Each resolved path is
    read once per load. The returned Program has no filesystem dependencies.
    """
    for name, value in (("max_files", max_files), ("max_depth", max_depth),
                        ("max_file_bytes", max_file_bytes), ("max_bytes", max_bytes)):
        if type(value) is not int or value < 0:
            raise KGodelError(f"{name} must be a nonnegative integer.")
    try:
        entry = Path(filename).resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise KGodelError(f"Cannot open entry program {filename}: {error}") from error
    root = entry.parent
    active, order = [], []
    loaded, modules = {}, {}
    total_bytes = 0

    def label(path):
        return path.relative_to(root).as_posix()

    def resolve_reference(parent, reference):
        # Forward-slash relative paths have identical meaning on every platform.
        if (not reference or "\\" in reference or ":" in reference
                or any(ord(char) < 32 for char in reference)
                or PurePosixPath(reference).is_absolute() or PureWindowsPath(reference).drive):
            raise KGodelError("Include paths must be nonempty relative paths using forward slashes.")
        try:
            target = (parent / reference).resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as error:
            raise KGodelError(f"Cannot load include {reference!r}: {error}") from error
        if not target.is_relative_to(root):
            raise KGodelError(f"Include escapes the project directory: {reference!r}.")
        return target

    def visit(path, depth):
        nonlocal total_bytes
        if path in active:
            chain = " -> ".join(map(label, [*active, path]))
            raise KGodelError(f"Circular include: {chain}.")
        if depth > max_depth:
            raise KGodelError(f"Include depth limit exceeded ({max_depth}).")
        if path in loaded:
            return None
        if len(order) >= max_files:
            raise KGodelError(f"Source file limit exceeded ({max_files}).")
        active.append(path)
        order.append(path)
        try:
            if not path.is_file():
                raise KGodelError("Source must be a regular file.")
            allowance = min(max_file_bytes, max_bytes - total_bytes)
            with path.open("rb") as stream:
                content = stream.read(allowance + 1)
            if len(content) > max_file_bytes:
                raise KGodelError(f"Source file byte limit exceeded ({max_file_bytes}).")
            if total_bytes + len(content) > max_bytes:
                raise KGodelError(f"Total source byte limit exceeded ({max_bytes}).")
            total_bytes += len(content)
            source = content.decode("utf-8-sig")
            includes = []

            def include(reference):
                target = resolve_reference(path.parent, reference)
                includes.append(label(target))
                return visit(target, depth + 1)

            declaration = "agent" if path == entry else "module"
            program = Parser(source).program(declaration=declaration, include=include, validate=False)
            if declaration == "module":
                if program.name in modules:
                    raise KGodelError(f"Duplicate module name {program.name!r} in {label(modules[program.name])} and {label(path)}.")
                modules[program.name] = path
            loaded[path] = SourceFile(label(path), declaration, program.name,
                                      hashlib.sha256(content).hexdigest(), len(content), tuple(includes))
            return program
        except (KGodelError, OSError, UnicodeError) as error:
            raise KGodelError(f"{label(path)}: {error}") from error
        finally:
            active.pop()

    program = visit(entry, 0)
    try:
        ObjectSpace(program).validate_program()
    except KGodelError as error:
        raise KGodelError(f"Linked program {entry.name}: {error}") from error
    return LoadedProject(program, root, entry.name, tuple(loaded[path] for path in order))


def parse_file(filename: str | Path, **limits) -> Program:
    """Load an agent file with its modules; unlike parse(), this reads the filesystem."""
    return load_project(filename, **limits).program


def format_imports(project: LoadedProject) -> str:
    report = project.as_dict()
    lines = [f"Project: {report['agent']}; {len(project.sources)} files, {report['total_bytes']} bytes",
             f"Root: {project.root}"]
    for source in project.sources:
        lines.append(f"{source.path}: {source.declaration} {source.name}")
        lines.extend(f"  includes {target}" for target in source.includes)
    return "\n".join(lines)

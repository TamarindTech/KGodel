"""Small, self-contained projects for the installed command-line product."""

from importlib.resources import files
from pathlib import Path

from .demos import DEMOS
from .model import KGodelError


TEMPLATES = ("route", "logic")


def create_project(directory: str | Path, template: str = "route") -> Path:
    """Create a new directory only; never merge into or overwrite an existing one."""
    if template not in TEMPLATES:
        raise KGodelError(f"Unknown project template: {template}.")
    resources = files("kgodel.templates").joinpath(template)
    contents = {name: resources.joinpath(name).read_text(encoding="utf-8")
                for name in ("README.md", "queries.kgq")}
    if template == "route":
        demo = files("kgodel.demos")
        stem = DEMOS["multistep-route"][0]
        contents["agent.kg"] = demo.joinpath(stem + ".kg").read_text(encoding="utf-8")
        contents["agent.world.json"] = demo.joinpath(stem + ".world.json").read_text(encoding="utf-8")
    else:
        contents["agent.kg"] = resources.joinpath("agent.kg").read_text(encoding="utf-8")
    contents[".gitignore"] = "__pycache__/\n.venv/\n*.trace.json\n*.trace.txt\n*.session.json\n"
    target = Path(directory).absolute()
    try:
        target.mkdir()  # Existing directories, files, and symlinks are all refused.
    except FileExistsError as error:
        raise KGodelError(f"Project destination already exists: {target}. Choose a new folder.") from error
    created = []
    try:
        for name, content in contents.items():
            path = target / name
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                created.append(path)
                stream.write(content)
    except OSError:
        # Remove only files created by this invocation, retaining any unrelated files.
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            target.rmdir()
        except OSError:
            pass
        raise
    return target

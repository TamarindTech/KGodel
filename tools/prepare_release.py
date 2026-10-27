"""Build a source distribution, wheel, and offline starter kit; never publish.

Usage: python tools/prepare_release.py --output dist/release
Requires the build and twine packages in the invoking environment.
"""

import argparse
from email.parser import Parser
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def validate_distributions(directory: Path, version: str):
    wheel = directory / f"kgodel-{version}-py3-none-any.whl"
    source = directory / f"kgodel-{version}.tar.gz"
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        metadata = Parser().parsestr(archive.read(f"kgodel-{version}.dist-info/METADATA").decode("utf-8"))
        if (metadata["Name"] != "kgodel" or metadata["Version"] != version
                or metadata["Requires-Python"] != ">=3.10" or metadata.get_all("Requires-Dist")
                or metadata["License-Expression"] != "MIT"):
            raise ValueError("Distribution metadata does not match the release contract.")
        required = {"kgodel/templates/route/README.md", "kgodel/templates/route/queries.kgq",
                    "kgodel/templates/logic/README.md", "kgodel/templates/logic/agent.kg",
                    "kgodel/templates/logic/queries.kgq", "kgodel/demos/multistep_route.kg",
                    "kgodel/demos/multistep_route.world.json", f"kgodel-{version}.dist-info/licenses/LICENSE"}
        if not required <= names:
            raise ValueError(f"Wheel is missing resources: {sorted(required - names)}")
    with tarfile.open(source) as archive:
        prefix = f"kgodel-{version}/"
        names = {item.name.removeprefix(prefix) for item in archive.getmembers() if item.isfile()}
        required = {"README.md", "PACKAGE.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md",
                    "docs/releasing.md", "docs/product-preview.md", "tools/verify_install.py",
                    "tools/verify_tutorials.py", "tests/test_product.py", "pyproject.toml"}
        if not required <= names:
            raise ValueError(f"Source distribution is missing files: {sorted(required - names)}")
        if any(name.startswith(("output/branding/", ".git/", ".venv/")) for name in names):
            raise ValueError("Source distribution contains local workspace files.")
    return wheel, source


def package_kit(directory: Path, version: str):
    wheel, source = validate_distributions(directory, version)
    prefix = f"kgodel-{version}"
    kit = directory / f"kgodel-{version}-starter-kit.zip"
    instructions = f"""# KGodel {version} developer preview

Python 3.10 or newer is required. Extract this entire archive, open a terminal
in this folder, and install the bundled wheel in a new environment:

Windows:
    python -m venv .venv
    .venv\\Scripts\\python -m pip install --no-index --no-deps wheels/{wheel.name}
    .venv\\Scripts\\python -m kgodel doctor
    .venv\\Scripts\\python -m kgodel init my-agent
    .venv\\Scripts\\python -m kgodel run my-agent/agent.kg

macOS / Linux:
    python3 -m venv .venv
    .venv/bin/python -m pip install --no-index --no-deps wheels/{wheel.name}
    .venv/bin/python -m kgodel doctor
    .venv/bin/python -m kgodel init my-agent
    .venv/bin/python -m kgodel run my-agent/agent.kg

The wheel installs without a package index or runtime dependencies. Python and
its venv/pip tools must already be installed. The expected result is achieved.
The source, examples, and Markdown documentation are included for offline use.
Start with docs/product-preview.md, then docs/tutorials/README.md. Some reference
links point to online material. This is an alpha preview; see its documented
limits before relying on it. No hosted service, API keys, or telemetry are used.
"""
    # Read archive members into the ZIP without extracting paths onto the filesystem.
    with tarfile.open(source) as archive, zipfile.ZipFile(kit, "x", zipfile.ZIP_DEFLATED) as output:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != prefix:
                raise ValueError(f"Unexpected source path: {member.name}")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"Source archive contains a non-regular file: {member.name}")
            output.writestr(member.name, archive.extractfile(member).read())
        output.write(wheel, f"{prefix}/wheels/{wheel.name}")
        output.writestr(f"{prefix}/START_HERE.md", instructions)
    artifacts = (wheel, source, kit)
    (directory / "SHA256SUMS.txt").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts), encoding="utf-8")
    (directory / "release.json").write_text(json.dumps({
        "version": version, "channel": "alpha", "python": ">=3.10",
        "artifacts": [{"name": path.name, "bytes": path.stat().st_size,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in artifacts]
    }, indent=2) + "\n", encoding="utf-8")
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New output directory (must not already exist)")
    args = parser.parse_args()
    version = re.search(r'^__version__ = "([^"]+)"', (ROOT / "kgodel/__init__.py").read_text(), re.M)[1]
    if not re.fullmatch(r"\d+\.\d+\.\d+a\d+", version):
        parser.error("This preview release tool requires an alpha version such as 0.13.0a1.")
    target = args.output.resolve()
    if target.exists():
        parser.error("Output directory already exists; choose a new directory to avoid mixing releases.")
    target.mkdir(parents=True)
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(target), str(ROOT)], check=True)
    validate_distributions(target, version)
    subprocess.run([sys.executable, "-m", "twine", "check", "--strict", *map(str, sorted(target.iterdir()))], check=True)
    for path in package_kit(target, version):
        print(path)
    print("Prepared locally. Run verify_install.py on the wheel before publishing.")


if __name__ == "__main__":
    main()

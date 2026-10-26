"""Check the release manifest, checksums, and starter kit against its distributions."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile
import zipfile

from prepare_release import validate_distributions


def verify(directory: Path):
    manifest = json.loads((directory / "release.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+a\d+", version):
        raise ValueError("Release manifest must name an alpha version.")
    wheel, source = validate_distributions(directory, version)
    kit = directory / f"kgodel-{version}-starter-kit.zip"
    expected = {wheel.name, source.name, kit.name}
    entries = manifest["artifacts"]
    if len(entries) != 3 or {item["name"] for item in entries} != expected:
        raise ValueError("Release manifest has unexpected artifacts.")
    checksums = {}
    for line in (directory / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if name in checksums:
            raise ValueError("Duplicate checksum entry.")
        checksums[name] = digest
    if set(checksums) != expected:
        raise ValueError("Checksum list has unexpected artifacts.")
    for item in entries:
        path = directory / item["name"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"] or digest != checksums[path.name] or path.stat().st_size != item["bytes"]:
            raise ValueError(f"Integrity check failed: {path.name}")
    with zipfile.ZipFile(kit) as archive, tarfile.open(source) as sources:
        if archive.testzip() is not None:
            raise ValueError("Starter kit ZIP is damaged.")
        names = archive.namelist()
        members = [item for item in sources.getmembers() if item.isfile()]
        wheel_name = f"kgodel-{version}/wheels/{wheel.name}"
        start_name = f"kgodel-{version}/START_HERE.md"
        if len(names) != len(set(names)) or set(names) != {item.name for item in members} | {wheel_name, start_name}:
            raise ValueError("Starter kit has missing, duplicate, or unexpected files.")
        if archive.read(wheel_name) != wheel.read_bytes():
            raise ValueError("Starter kit wheel differs from the standalone wheel.")
        for member in members:
            if archive.read(member.name) != sources.extractfile(member).read():
                raise ValueError(f"Starter kit source differs: {member.name}")
    print(f"Release {version}: metadata, resources, all three checksums, and starter kit contents verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    verify(parser.parse_args().directory)

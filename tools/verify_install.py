"""Install a built wheel in a fresh environment and exercise it outside the checkout.

Usage: python tools/verify_install.py dist
Requires only the standard library and venv/pip. Installation uses no package index.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import venv


def verify(wheel: Path):
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory(prefix="kgodel-install-") as temporary:
        root = Path(temporary)
        isolated = root / "venv"
        outside = root / "outside checkout"
        outside.mkdir()
        venv.EnvBuilder(with_pip=True).create(isolated)
        scripts = isolated / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        console = scripts / ("kgodel.exe" if os.name == "nt" else "kgodel")

        def run(*arguments, input=None, expected_code=0):
            result = subprocess.run(list(map(str, arguments)), cwd=outside, env=environment,
                                    input=input, capture_output=True, text=True, timeout=120)
            if result.returncode != expected_code:
                raise RuntimeError(f"Command failed ({result.returncode}): {arguments}\n{result.stdout}\n{result.stderr}")
            return result.stdout

        run(python, "-I", "-m", "pip", "install", "--no-index", "--no-deps", wheel)
        metadata = json.loads(run(python, "-I", "-c",
            "import json,kgodel,importlib.metadata as m; "
            "print(json.dumps({'path':kgodel.__file__,'version':kgodel.__version__,"
            "'installed':m.version('kgodel'),'requires':m.requires('kgodel')}))"))
        assert Path(metadata["path"]).resolve().is_relative_to(isolated.resolve()), metadata
        assert metadata["version"] == metadata["installed"], metadata
        assert not metadata["requires"], metadata
        module_version = run(python, "-I", "-m", "kgodel", "--version").strip()
        assert module_version == f"KGodel {metadata['version']}", module_version
        assert run(console, "--version").strip() == module_version
        names = json.loads(run(python, "-I", "-c",
                              "import json; from kgodel.demos import DEMOS; print(json.dumps(list(DEMOS)))"))
        listing = run(console, "demo", "--list")
        for name in names:
            assert name in listing
            trace = outside / f"{name}.json"
            run(python, "-I", "-m", "kgodel", "demo", name, "--trace-json", trace)
            result = json.loads(trace.read_text(encoding="utf-8"))
            assert result["status"] == "achieved", result
            print(f"Installed demo {name}: achieved")
        transcript = run(console, "shell", "--demo", "multistep-route", input="\n".join([
            "clear(forest).", ":step 3", ":explain at(forest)", ":preview", ":run",
            ':save "session trace.json"', ":quit", ""]))
        assert "unknown: clear(forest)" in transcript, transcript
        assert "true: at(forest)" in transcript, transcript
        assert "Result: achieved" in transcript, transcript
        result = json.loads((outside / "session trace.json").read_text(encoding="utf-8"))
        assert result["status"] == "achieved" and result["steps"] == 5, result
        checkpoint = outside / "saved session.json"
        run(console, "demo", "--max-steps", "3", "--checkpoint", checkpoint, expected_code=1)
        paused = checkpoint.read_bytes()
        resumed_trace = outside / "resumed.json"
        run(python, "-I", "-m", "kgodel", "resume", checkpoint, "--trace-json", resumed_trace)
        resumed = json.loads(resumed_trace.read_text(encoding="utf-8"))
        uninterrupted = json.loads((outside / "multistep-route.json").read_text(encoding="utf-8"))
        assert resumed == uninterrupted, resumed
        assert checkpoint.read_bytes() == paused
        transcript = run(console, "shell", "--resume", checkpoint,
                         input=":trace\n:explain at(forest)\n:run\n:quit\n")
        assert "simulator:step_3" in transcript and "Result: achieved" in transcript, transcript
        print(f"{module_version}: installation, demos, shell, and cross-process session restart verified outside checkout")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="A KGodel wheel or a directory containing exactly one")
    args = parser.parse_args()
    wheels = sorted(args.wheel.glob("kgodel-*.whl")) if args.wheel.is_dir() else [args.wheel]
    if len(wheels) != 1 or not wheels[0].is_file():
        parser.error("Supply one wheel file, or a directory containing exactly one KGodel wheel")
    verify(wheels[0].resolve())

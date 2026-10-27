"""Local installation diagnostics. No network, file writes, or external actions."""

from importlib import metadata
from pathlib import Path
import platform
import sys

from . import __version__
from .demos import load_demo


def diagnose() -> dict:
    checks = []
    installed = None
    try:
        installed = metadata.version("kgodel")
        status = "pass" if installed == __version__ else "warning"
        detail = ("Installed metadata matches the imported package." if status == "pass" else
                  "Installed metadata differs from the imported source. Use the intended Python environment.")
    except metadata.PackageNotFoundError:
        status, detail = "warning", "Running from source without installed metadata; install this checkout to use it elsewhere."
    checks.append({"name": "package", "status": status, "detail": detail})
    try:
        agent = load_demo()
        report = agent.run()
        if report["status"] != "achieved" or agent.world.position != "goal":
            raise RuntimeError(f"Demo did not reach its goal: {report['status']}.")
        checks.append({"name": "bundled_demo", "status": "pass",
                       "detail": f"Bundled route demo reached its goal in {report['steps']} operations."})
    except Exception as error:
        checks.append({"name": "bundled_demo", "status": "fail", "detail": str(error)})
    status = "error" if any(item["status"] == "fail" for item in checks) else (
        "warning" if any(item["status"] == "warning" for item in checks) else "ok")
    return {"status": status, "version": __version__, "installed_version": installed,
            "python": platform.python_version(), "executable": sys.executable,
            "package_path": str(Path(__file__).resolve().parent), "platform": platform.system(),
            "checks": checks}


def format_diagnostics(report: dict) -> str:
    lines = [f"KGodel {report['version']}: {report['status']}",
             f"Python {report['python']}: {report['executable']}",
             f"Package: {report['package_path']}"]
    lines += [f"{item['status'].upper()}: {item['name']}: {item['detail']}" for item in report["checks"]]
    return "\n".join(lines)

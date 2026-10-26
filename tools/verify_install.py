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
        diagnostics = json.loads(run(console, "doctor", "--json"))
        assert diagnostics["status"] == "ok" and diagnostics["version"] == metadata["version"], diagnostics
        for template in ("route", "logic"):
            project = outside / f"{template} starter"
            run(console, "init", project, "--template", template)
            run(console, "check", project / "agent.kg")
            run(console, "explain", project / "agent.kg", "--file", project / "queries.kgq")
            if template == "route":
                assert "Result: achieved" in run(console, "run", project / "agent.kg")
            original = (project / "agent.kg").read_bytes()
            run(console, "init", project, expected_code=2)
            assert (project / "agent.kg").read_bytes() == original
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
        finished = outside / "finished session.json"
        run(python, "-I", "-m", "kgodel", "resume", checkpoint, "--trace-json", resumed_trace,
            "--checkpoint", finished)
        resumed = json.loads(resumed_trace.read_text(encoding="utf-8"))
        uninterrupted = json.loads((outside / "multistep-route.json").read_text(encoding="utf-8"))
        assert resumed == uninterrupted, resumed
        assert checkpoint.read_bytes() == paused
        transcript = run(console, "shell", "--resume", checkpoint,
                         input=":trace\n:explain at(forest)\n:run\n:quit\n")
        assert "simulator:step_3" in transcript and "Result: achieved" in transcript, transcript
        comparison = outside / "comparison.json"
        rendered = run(console, "compare", checkpoint, finished, "--query", "at(goal)",
                       "--explain", "--result-json", comparison)
        assert "at(goal): unknown -> true" in rendered, rendered
        report = json.loads(comparison.read_text(encoding="utf-8"))
        assert report["status"] == "ok" and report["changed"], report
        assert report["history"]["operations"]["common_prefix"] == 3, report
        assert checkpoint.read_bytes() == paused
        partial = run(python, "-I", "-m", "kgodel", "compare", checkpoint, finished,
                      "--max-work", "0", expected_code=1)
        assert "Comparison: partial" in partial, partial
        transcript = run(console, "shell", "--resume", checkpoint,
                         input=f':run\n:compare "{checkpoint}"\n:quit\n')
        assert "position: forest -> goal" in transcript, transcript
        object_checkpoint = outside / "object session.json"
        transcript = run(console, "shell", "--demo", "object-routes", input="\n".join([
            ":objects", "[cautious candidateFrom: start to: forest].", ":step",
            ':checkpoint "object session.json"', ":quit", ""]))
        assert "Class ApprovedPolicy extends RoutePolicy" in transcript, transcript
        assert "true: [cautious candidateFrom: start to: forest]" in transcript, transcript
        object_finished = outside / "object finished.json"
        run(console, "resume", object_checkpoint, "--checkpoint", object_finished)
        rendered = run(console, "compare", object_checkpoint, object_finished,
                       "--query", "[cautious finished]", "--explain")
        assert "[cautious finished]: unknown -> true" in rendered, rendered
        assert "method:RoutePolicy>>finished@cautious" in rendered, rendered
        super_checkpoint = outside / "super session.json"
        transcript = run(console, "shell", "--demo", "super-routes", input="\n".join([
            ":explain [cautious candidateFrom: start to: forest]",
            ":abduce [cautious mayMoveFrom: start to: bridge] from (open(bridge), clear(bridge))",
            "[cautious candidateFrom: start to: bridge].", ":step",
            ':checkpoint "super session.json"', ":quit", ""]))
        assert "[cautious ^ApprovedPolicy candidateFrom: start to: forest]" in transcript, transcript
        assert "[cautious ^RoutePolicy candidateFrom: start to: forest]" in transcript, transcript
        assert "unknown: [cautious candidateFrom: start to: bridge]" in transcript, transcript
        assert "Explanation 1: assume clear(bridge), open(bridge)." in transcript, transcript
        saved = json.loads(super_checkpoint.read_text(encoding="utf-8"))
        assert saved["schema_version"] == 5 and saved["intention"] is not None, saved
        super_trace = outside / "super resumed.json"
        run(console, "resume", super_checkpoint, "--trace-json", super_trace)
        expected = json.loads((outside / "super-routes.json").read_text(encoding="utf-8"))
        assert json.loads(super_trace.read_text(encoding="utf-8")) == expected
        abduction = outside / "abduction.json"
        query = "[cautious mayMoveFrom: start to: bridge]"
        run(console, "abduce", "--demo", "super-routes", query,
            "--assume", "clear(bridge)", "--assume", "open(bridge)", "--result-json", abduction)
        report = json.loads(abduction.read_text(encoding="utf-8"))
        assert report["status"] == "complete" and report["search"]["exhaustive"], report
        assert [row["assumptions"] for row in report["solutions"]] == [["clear(bridge)", "open(bridge)"]], report
        assert "^RoutePolicy" in json.dumps(report["solutions"][0]["proof"]), report
        saved_bytes = super_checkpoint.read_bytes()
        partial = run(console, "abduce", "--resume", super_checkpoint, query,
                      "--assume", "open(bridge)", "--assume", "clear(bridge)",
                      "--max-contexts", "0", expected_code=1)
        assert "Abduction: partial" in partial, partial
        assert super_checkpoint.read_bytes() == saved_bytes
        prolog = outside / "prolog.kg"
        prolog.write_text(r"""agent route {
            at(start). path(start, goal). label('Mary Jane', accepted).
            has_label(X) :- label(X, _), X \== ignored.
            goal at(goal).
            plan travel(_From, _To) for at(_To) {
                when at(_From), path(_From, _To), label(_, _), _From \== _To.
                suppose(clear(_To)) { path(_From, _To), (clear(_To); open(_To)), _From \== _To. }
                observe clear(_To).
                require clear(_To), _From \== _To.
                act move(_From, _To).
            }
        }""", encoding="utf-8")
        prolog.with_suffix(".world.json").write_text(json.dumps({
            "position": "start", "edges": [["start", "goal"]], "blocked": []}), encoding="utf-8")
        request = outside / "prolog.kgq"
        request.write_text(r"?- (label(Name, _); has_label(Name)), path(_, _), Name \== 'Nobody'.", encoding="utf-8")
        prolog_report = outside / "prolog query.json"
        rendered = run(console, "explain", prolog, "--file", request, "--result-json", prolog_report)
        assert "query:and" in rendered and "query:or" in rendered, rendered
        assert "builtin:" in rendered, rendered
        report = json.loads(prolog_report.read_text(encoding="utf-8"))
        assert [row["bindings"] for row in report["results"][0]["answers"]] == [{"Name": "Mary Jane"}], report
        prolog_checkpoint = outside / "prolog session.json"
        transcript = run(console, "shell", prolog, input="\n".join([
            "?- path(_, _).", ":step", ':checkpoint "prolog session.json"', ":quit", ""]))
        assert "true (no named bindings)" in transcript, transcript
        saved = json.loads(prolog_checkpoint.read_text(encoding="utf-8"))
        assert saved["schema_version"] == 5 and saved["intention"] is not None, saved
        prolog_trace = outside / "prolog resumed.json"
        run(python, "-I", "-m", "kgodel", "resume", prolog_checkpoint, "--trace-json", prolog_trace)
        result = json.loads(prolog_trace.read_text(encoding="utf-8"))
        assert result["status"] == "achieved" and result["steps"] == 2, result
        print(f"{module_version}: installation, diagnostics, starter projects, demos, objects, super dispatch, abduction, Prolog queries, shell, session restart, and comparisons verified outside checkout")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, help="A KGodel wheel or a directory containing exactly one")
    args = parser.parse_args()
    wheels = sorted(args.wheel.glob("kgodel-*.whl")) if args.wheel.is_dir() else [args.wheel]
    if len(wheels) != 1 or not wheels[0].is_file():
        parser.error("Supply one wheel file, or a directory containing exactly one KGodel wheel")
    verify(wheels[0].resolve())

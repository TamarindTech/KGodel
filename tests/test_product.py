from contextlib import redirect_stderr, redirect_stdout
from importlib import metadata
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kgodel import __version__
from kgodel.__main__ import main
from kgodel.demos import load_demo
from kgodel.diagnostics import diagnose
from kgodel.model import KGodelError
from kgodel.parser import parse
from kgodel.projects import create_project
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import load_session, save_session


class ProductTests(unittest.TestCase):
    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(map(str, args)))
        return code, out.getvalue(), err.getvalue()

    def test_route_project_runs_and_explains_without_repository_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = create_project(Path(temporary) / "my agent")
            program = parse((target / "agent.kg").read_text())
            world = RouteWorld.from_json((target / "agent.world.json").read_text())
            self.assertEqual(Agent(program, world).run()["status"], "achieved")
            self.assertEqual(self.invoke(["explain", target / "agent.kg", "--file", target / "queries.kgq"])[0], 0)
            self.assertTrue((target / "README.md").is_file())

    def test_logic_project_produces_distinct_pairs_and_temporary_hypotheses(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "knowledge"
            self.assertEqual(self.invoke(["init", target, "--template", "logic"])[0], 0)
            result = target / "result.json"
            self.assertEqual(self.invoke(["query", target / "agent.kg", "--file", target / "queries.kgq",
                                          "--result-json", result])[0], 0)
            rows = json.loads(result.read_text())["results"]
            self.assertEqual(rows[1]["answers"][0]["bindings"], {"First": "bob", "Second": "carol"})
            self.assertEqual(rows[2]["status"], "unknown")
            self.assertEqual(rows[3]["results"][0]["status"], "true")
            self.assertEqual(rows[4]["status"], "unknown")
            self.assertFalse((target / "agent.world.json").exists())

    def test_init_never_overwrites_existing_directory_or_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder, existing = root / "folder", root / "existing"
            folder.mkdir()
            existing.write_text("keep")
            for target in (folder, existing):
                code, _, error = self.invoke(["init", target])
                self.assertEqual(code, 2)
                self.assertIn("already exists", error)
            self.assertEqual(existing.read_text(), "keep")
            self.assertEqual(list(folder.iterdir()), [])

    def test_invalid_template_and_missing_parent_make_no_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "project"
            with self.assertRaises(KGodelError):
                create_project(target, "../../outside")
            self.assertFalse(target.exists())
            self.assertEqual(self.invoke(["init", target / "child"])[0], 2)
            self.assertFalse(target.exists())

    def test_partial_init_removes_only_its_own_created_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "project"
            original = Path.open

            def fail(path, *args, **kwargs):
                if path.name == "queries.kgq" and args and args[0] == "x":
                    (target / "unrelated.txt").write_text("keep")
                    raise PermissionError("write interrupted")
                return original(path, *args, **kwargs)

            with patch.object(Path, "open", fail), self.assertRaises(PermissionError):
                create_project(target)
            self.assertEqual([p.name for p in target.iterdir()], ["unrelated.txt"])

    def test_doctor_reports_matching_install_and_does_not_change_cwd(self):
        before = Path.cwd()
        with patch("kgodel.diagnostics.metadata.version", return_value=__version__):
            code, output, _ = self.invoke(["doctor", "--json"])
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["version"], __version__)
        self.assertTrue(all(c["status"] == "pass" for c in result["checks"]))
        self.assertEqual(Path.cwd(), before)

    def test_doctor_handles_missing_and_conflicting_metadata(self):
        for version in (None, "0.0.0"):
            options = {"side_effect": metadata.PackageNotFoundError()} if version is None else {"return_value": version}
            with patch("kgodel.diagnostics.metadata.version", **options):
                code, output, _ = self.invoke(["doctor", "--json"])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output)["installed_version"], version)

    def test_doctor_reports_missing_demo_as_failure(self):
        with patch("kgodel.diagnostics.load_demo", side_effect=FileNotFoundError("missing resource")):
            report = diagnose()
        self.assertEqual(report["status"], "error")
        self.assertIn("missing resource", report["checks"][-1]["detail"])

    def test_exports_cannot_overwrite_any_input_or_each_other(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = create_project(Path(temporary) / "agent")
            program, world, query = root / "agent.kg", root / "agent.world.json", root / "queries.kgq"
            before = {p: p.read_bytes() for p in (program, world, query)}
            cases = [["run", program, "--trace-json", program],
                     ["run", program, "--checkpoint", world],
                     ["run", program, "--world", world, "--trace-text", world],
                     ["query", program, "--file", query, "--result-json", query],
                     ["explain", program, "at(start)", "--result-json", program],
                     ["deliberate", program, "--result-json", program],
                     ["demo", "--trace-text", root / "result", "--trace-json", root / "result"]]
            for args in cases:
                with self.subTest(args=args), patch("kgodel.__main__.execute_agent") as execute:
                    self.assertEqual(self.invoke(args)[0], 2)
                    execute.assert_not_called()
            self.assertEqual(before, {p: p.read_bytes() for p in before})
            self.assertFalse((root / "result").exists())

    def test_output_hardlink_to_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = create_project(Path(temporary) / "agent")
            alias = root / "alias.json"
            os.link(root / "agent.kg", alias)
            before = alias.read_bytes()
            self.assertEqual(self.invoke(["run", root / "agent.kg", "--trace-json", alias])[0], 2)
            self.assertEqual(alias.read_bytes(), before)

    def test_resume_can_replace_its_checkpoint_but_not_with_a_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "session.json"
            agent = load_demo()
            agent.run(1)
            save_session(agent, target)
            before = target.read_bytes()
            self.assertEqual(self.invoke(["resume", target, "--trace-json", target])[0], 2)
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(self.invoke(["resume", target, "--checkpoint", target])[0], 0)
            self.assertEqual(load_session(target).world.position, "goal")

    def test_invalid_utf8_is_a_readable_cli_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "bad.kg"
            target.write_bytes(b"\xff\xfeinvalid")
            code, _, error = self.invoke(["check", target])
            self.assertEqual(code, 2)
            self.assertIn("KGodel error:", error)
            self.assertNotIn("Traceback", error)


if __name__ == "__main__":
    unittest.main()

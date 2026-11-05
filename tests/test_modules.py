from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kgodel.__main__ import main
from kgodel.loading import load_project, parse_file
from kgodel.logic import Inference, Knowledge
from kgodel.model import KGodelError
from kgodel.parser import parse, parse_query
from kgodel.projects import create_project
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import load_session, program_source, save_session


class ModuleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="kgodel-modules-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path

    def entry(self, body):
        return self.write("agent.kg", "agent example { " + body + " }")

    def logic(self, path):
        program = parse_file(path)
        return Inference(Knowledge(program.beliefs), program.effective_rules)

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(map(str, args)))
        return code, out.getvalue(), err.getvalue()

    def route(self):
        self.write("lib/routes.kg", """module routes {
            path(start, goal).
            plan travel(From, To) for at(To) {
                when at(From), path(From, To), From \\== To.
                observe clear(To).
                require clear(To), From \\== To.
                act move(From, To).
            }
        }""")
        entry = self.entry('include "lib/routes.kg". at(start). goal at(goal).')
        self.write("agent.world.json", json.dumps({"position": "start", "edges": [["start", "goal"]], "blocked": []}))
        return entry

    def test_single_file_matches_text_parser(self):
        entry = self.entry("fact(a). derived(X) :- fact(X).")
        self.assertEqual(parse_file(entry), parse(entry.read_text()))

    def test_packaged_modular_starter_runs_and_exposes_four_sources(self):
        folder = create_project(self.root / "starter", "modular")
        project = load_project(folder / "agent.kg")
        self.assertEqual(len(project.sources), 4)
        agent = Agent(project.program, RouteWorld.from_json((folder / "agent.world.json").read_text()))
        result = agent.run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["steps"], 4)
        self.assertEqual(agent.world.position, "goal")

    def test_fact_and_recursive_rule_modules_link_with_entry_facts(self):
        self.write("rules.kg", """module family {
            ancestor(X, Y) :- parent(X, Y).
            ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
        }""")
        entry = self.entry('parent(a, b). include "rules.kg". parent(b, c).')
        self.assertEqual(self.logic(entry).status(parse_query("ancestor(a, c)")), "true")

    def test_nested_relative_includes_and_diamonds_load_once(self):
        self.write("common.kg", "module common { shared(a). shared_rule(X) :- shared(X). }")
        self.write("lib/left.kg", 'module left { include "../common.kg". left. }')
        self.write("right.kg", 'module right { include "common.kg". right. }')
        project = load_project(self.entry('include "lib/left.kg". include "right.kg". include "./common.kg".'))
        self.assertEqual([s.path for s in project.sources], ["agent.kg", "lib/left.kg", "common.kg", "right.kg"])
        self.assertEqual([str(x) for x in project.program.beliefs], ["shared(a)", "left", "right"])
        self.assertEqual(len(project.program.rules), 1)
        self.assertEqual(project.as_dict()["files"][1]["includes"], ["common.kg"])

    def test_include_position_controls_global_rule_order_and_proofs(self):
        self.write("rules.kg", "module middle { via_module :- fact. }")
        program = parse_file(self.entry('fact. before :- fact. include "rules.kg". after :- via_module.'))
        self.assertEqual([r.name for r in program.rules], ["rule_1", "rule_2", "rule_3"])
        logic = Inference(Knowledge(program.beliefs), program.effective_rules)
        proof = logic.explanation(parse_query("after"))
        self.assertEqual(proof.source, "rule_3")
        self.assertEqual(proof.premises[0].source, "rule_2")
        self.assertEqual(parse(program_source(program)), program)

    def test_inheritance_can_reference_later_modules_and_entry_objects(self):
        self.write("child.kg", """module child {
            class Child extends Base { method allowed: X { [super allowed: X]. X \\== blocked. } }
        }""")
        self.write("base.kg", "module base { class Base { method allowed: X { available(X). } } }")
        entry = self.entry('include "child.kg". include "base.kg". object policy : Child {} available(ok). available(blocked).')
        logic = self.logic(entry)
        self.assertEqual(logic.status(parse_query("[policy allowed: ok]")), "true")
        self.assertEqual(logic.status(parse_query("[policy allowed: blocked]")), "unknown")

    def test_module_plan_can_execute_and_resume_without_source_files(self):
        entry = self.route()
        program = parse_file(entry)
        agent = Agent(program, RouteWorld("start", [["start", "goal"]], []))
        expected = Agent(program, RouteWorld("start", [["start", "goal"]], [])).run()
        self.assertEqual(agent.run(1)["status"], "step_limit")
        checkpoint = self.root / "saved.json"
        save_session(agent, checkpoint)
        snapshot = json.loads(checkpoint.read_text())
        self.assertEqual(snapshot["schema_version"], 5)
        self.assertNotIn("include ", snapshot["program"])
        entry.unlink()
        (self.root / "lib/routes.kg").unlink()
        restored = load_session(checkpoint)
        self.assertEqual(restored.run(), expected)

    def test_text_parser_does_not_follow_includes(self):
        with patch.object(Path, "open", side_effect=AssertionError("unexpected file read")):
            with self.assertRaisesRegex(KGodelError, "parse_file"):
                parse('agent a { include "secret.kg". }')

    def test_checkpoint_parser_does_not_follow_includes(self):
        agent = Agent(parse("agent a { at(start). goal at(start). }"), RouteWorld("start", [], []))
        checkpoint = self.root / "saved.json"
        save_session(agent, checkpoint)
        data = json.loads(checkpoint.read_text())
        data["program"] = 'agent a { include "secret.kg". }'
        checkpoint.write_text(json.dumps(data))
        with self.assertRaisesRegex(KGodelError, "parse_file"):
            load_session(checkpoint)

    def test_circular_includes_report_the_dependency_chain(self):
        self.write("a.kg", 'module a { include "b.kg". }')
        self.write("b.kg", 'module b { include "a.kg". }')
        with self.assertRaisesRegex(KGodelError, "agent.kg -> a.kg -> b.kg -> a.kg"):
            parse_file(self.entry('include "a.kg".'))

    def test_direct_self_include_is_not_silently_deduplicated(self):
        with self.assertRaisesRegex(KGodelError, "Circular include"):
            parse_file(self.entry('include "agent.kg".'))

    def test_includes_require_module_sources_and_entry_requires_agent(self):
        module = self.write("library.kg", "module library { available. }")
        with self.assertRaisesRegex(KGodelError, "Expected 'agent'"):
            parse_file(module)
        self.write("library.kg", "agent library { available. }")
        with self.assertRaisesRegex(KGodelError, "Expected 'module'"):
            parse_file(self.entry('include "library.kg".'))

    def test_modules_cannot_introduce_agent_goals(self):
        self.write("lib.kg", "module library { goal finished. }")
        with self.assertRaisesRegex(KGodelError, "Modules cannot declare goals"):
            parse_file(self.entry('include "lib.kg".'))

    def test_distinct_files_cannot_reuse_module_name(self):
        for name in ("one.kg", "two.kg"):
            self.write(name, "module same { fact. }")
        with self.assertRaisesRegex(KGodelError, "Duplicate module name"):
            parse_file(self.entry('include "one.kg". include "two.kg".'))

    def test_duplicate_classes_objects_and_plans_fail_after_linking(self):
        cases = ["class Same { method ok { ready. } }", "object same : Base {}",
                 "plan same for done { when ready. observe clear(goal). }"]
        for body in cases:
            with self.subTest(body=body):
                self.write("one.kg", f"module one {{ {body} }}")
                self.write("two.kg", f"module two {{ {body} }}")
                with self.assertRaisesRegex(KGodelError, "Duplicate"):
                    parse_file(self.entry('class Base { method ok { ready. } } include "one.kg". include "two.kg".'))

    def test_imported_conflicts_are_still_logical_conflicts(self):
        self.write("positive.kg", "module positive { ready. }")
        code, _, error = self.invoke(["check", self.entry('include "positive.kg". not ready.')])
        self.assertEqual(code, 2)
        self.assertIn("ready", error)

    def test_errors_identify_module_and_original_line(self):
        self.write("broken.kg", "module broken {\n  good.\n  bad($).\n}")
        with self.assertRaisesRegex(KGodelError, "broken.kg: Line 3"):
            parse_file(self.entry('include "broken.kg".'))

    def test_missing_and_invalid_utf8_sources_have_filename_diagnostics(self):
        entry = self.entry('include "missing.kg".')
        with self.assertRaisesRegex(KGodelError, "missing.kg"):
            parse_file(entry)
        (self.root / "missing.kg").write_bytes(b"\xff")
        with self.assertRaisesRegex(KGodelError, "missing.kg"):
            parse_file(entry)

    def test_utf8_bom_unicode_names_and_comments_in_paths(self):
        path = self.write("lib/space name é.kg", '\ufeffmodule named { label("include fake.kg"). }')
        entry = self.entry('% include "missing.kg".\n include "lib/space name é.kg".')
        project = load_project(entry)
        self.assertEqual(project.sources[1].sha256, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(project.sources[1].bytes, len(path.read_bytes()))

    def test_include_predicate_names_remain_backward_compatible(self):
        program = parse_file(self.entry('include. include(value). module(value). include(X) :- item(X).'))
        self.assertEqual([str(x) for x in program.beliefs], ["include", "include(value)", "module(value)"])

    def test_absolute_and_nonportable_paths_are_rejected(self):
        for reference in ("", "/etc/passwd", "C:/somewhere/file.kg", "lib\\file.kg", "file\n.kg"):
            with self.subTest(reference=reference), self.assertRaisesRegex(KGodelError, "relative paths"):
                parse_file(self.entry(f"include {json.dumps(reference)}."))

    def test_parent_escape_is_rejected(self):
        nested = self.write("nested/agent.kg", 'agent a { include "../outside.kg". }')
        self.write("outside.kg", "module outside {}")
        with self.assertRaisesRegex(KGodelError, "escapes the project"):
            parse_file(nested)

    def test_symlink_escape_is_rejected_when_supported(self):
        nested = self.write("nested/agent.kg", 'agent a { include "link.kg". }')
        outside = self.write("outside.kg", "module outside {}")
        try:
            (nested.parent / "link.kg").symlink_to(outside)
        except OSError:
            self.skipTest("Symlink creation is unavailable on this system")
        with self.assertRaisesRegex(KGodelError, "escapes the project"):
            parse_file(nested)

    def test_source_limits_and_boundary_values(self):
        module = self.write("lib.kg", "module library { ready. }")
        entry = self.entry('include "lib.kg".')
        total = entry.stat().st_size + module.stat().st_size
        self.assertEqual(len(load_project(entry, max_files=2, max_depth=1, max_bytes=total).sources), 2)
        cases = [({"max_files": 1}, "file limit"), ({"max_depth": 0}, "depth limit"),
                 ({"max_bytes": total - 1}, "Total source byte limit"),
                 ({"max_file_bytes": entry.stat().st_size - 1}, "file byte limit")]
        for limits, message in cases:
            with self.subTest(limits=limits), self.assertRaisesRegex(KGodelError, message):
                load_project(entry, **limits)
        for limits in ({"max_files": True}, {"max_bytes": -1}, {"max_depth": 1.5}):
            with self.assertRaisesRegex(KGodelError, "nonnegative integer"):
                load_project(entry, **limits)

    def test_repeated_modules_do_not_consume_more_file_or_byte_budget(self):
        module = self.write("lib.kg", "module library { ready. }")
        entry = self.entry('include "lib.kg". include "./lib.kg".')
        total = entry.stat().st_size + module.stat().st_size
        self.assertEqual(load_project(entry, max_files=2, max_bytes=total).as_dict()["total_bytes"], total)

    def test_new_load_reads_changed_sources_without_mutating_previous_program(self):
        module = self.write("lib.kg", "module library { before. }")
        entry = self.entry('include "lib.kg".')
        before = load_project(entry)
        module.write_text("module library { after. }")
        after = load_project(entry)
        self.assertNotEqual(before.sources[1].sha256, after.sources[1].sha256)
        self.assertEqual(str(before.program.beliefs[0]), "before")
        self.assertEqual(str(after.program.beliefs[0]), "after")

    def test_imports_report_does_not_execute_agent_or_infer_facts(self):
        entry = self.route()
        report = self.root / "imports.json"
        with patch("kgodel.__main__.execute_agent") as execute, patch("kgodel.__main__.Inference") as inference:
            code, text, _ = self.invoke(["imports", entry, "--result-json", report])
        self.assertEqual(code, 0)
        execute.assert_not_called()
        inference.assert_not_called()
        self.assertIn("lib/routes.kg: module routes", text)
        self.assertEqual(json.loads(report.read_text())["format"], "kgodel-project")

    def test_cli_queries_objects_hypotheses_abduction_planning_and_shell_link_modules(self):
        entry = self.route()
        cases = [["check", entry], ["objects", entry], ["query", entry, "path(start, To)"],
                 ["explain", entry, "suppose(clear(goal)) { clear(goal). }"],
                 ["abduce", "--program", entry, "clear(goal)", "--assume", "clear(goal)"],
                 ["deliberate", entry], ["run", entry]]
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(args)[0], 0)
        with patch("builtins.input", side_effect=[":run", ":quit"]):
            self.assertIn("Result: achieved", self.invoke(["shell", entry])[1])

    def test_exports_cannot_overwrite_imports_including_hardlink_alias(self):
        entry = self.route()
        module = self.root / "lib/routes.kg"
        before = module.read_bytes()
        alias = self.root / "alias.json"
        os.link(module, alias)
        cases = [["imports", entry, "--result-json", module],
                 ["query", entry, "at(start)", "--result-json", alias],
                 ["abduce", "--program", entry, "at(start)", "--result-json", module],
                 ["run", entry, "--checkpoint", module], ["run", entry, "--trace-text", alias]]
        for args in cases:
            with self.subTest(args=args), patch("kgodel.__main__.execute_agent") as execute:
                self.assertEqual(self.invoke(args)[0], 2)
                execute.assert_not_called()
                self.assertEqual(module.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

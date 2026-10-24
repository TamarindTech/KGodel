import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kgodel.__main__ import main
from kgodel.demos import DEMOS, load_demo
from kgodel.model import KGodelError
from kgodel.parser import parse
from kgodel.runtime import Agent, RouteWorld
from kgodel.shell import ShellSession, run_shell


ROOT = Path(__file__).resolve().parents[1]


def state(agent):
    return copy.deepcopy((agent.knowledge.facts, agent.events, agent.decisions, agent.attempts,
                          agent.intention, agent.intention_events, agent._next_intention_id,
                          agent.world.__dict__))


class DemoTests(unittest.TestCase):
    def test_all_bundled_experiments_are_self_contained_and_reach_the_goal(self):
        for name in DEMOS:
            with self.subTest(name=name):
                result = load_demo(name).run()
                self.assertEqual(result["status"], "achieved")
                self.assertEqual(result["world_position"], "goal")

    def test_demo_instances_do_not_share_world_or_agent_state(self):
        first, second = load_demo(), load_demo()
        first.run()
        self.assertEqual(second.world.position, "start")
        self.assertEqual(second.events, [])
        self.assertIsNone(second.intention)

    def test_resource_names_cannot_be_arbitrary_paths(self):
        for name in ("../LICENSE", "multistep_route", "missing", "/etc/passwd"):
            with self.subTest(name=name), self.assertRaisesRegex(KGodelError, "Unknown demo"):
                load_demo(name)

    def test_bundled_examples_match_the_editable_repository_examples(self):
        from importlib.resources import files
        for stem, _ in DEMOS.values():
            for extension in (".kg", ".world.json"):
                name = stem + extension
                with self.subTest(name=name):
                    self.assertEqual(files("kgodel.demos").joinpath(name).read_text(encoding="utf-8"),
                                     (ROOT / "examples" / name).read_text(encoding="utf-8"))

    def test_list_does_not_load_or_execute_an_agent(self):
        with patch("kgodel.__main__.load_demo") as load, redirect_stdout(io.StringIO()) as output:
            code = main(["demo", "--list"])
        load.assert_not_called()
        self.assertEqual(code, 0)
        for name in DEMOS:
            self.assertIn(name, output.getvalue())

    def test_cli_demo_writes_requested_trace_and_honors_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "demo.json"
            with redirect_stdout(io.StringIO()):
                code = main(["demo", "--max-steps", "1", "--trace-json", str(target)])
            result = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(code, 1)
            self.assertEqual(result["status"], "step_limit")
            self.assertEqual(result["active_intention"]["next_step"], 2)

    def test_invalid_demo_arguments_fail_before_loading(self):
        for arguments in (["demo", "--list", "blocked-route"],
                          ["demo", "--list", "--trace-json", "unused.json"],
                          ["demo", "missing"]):
            with self.subTest(arguments=arguments), patch("kgodel.__main__.load_demo") as load:
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    main(arguments)
                self.assertEqual(error.exception.code, 2)
                load.assert_not_called()


class ShellTests(unittest.TestCase):
    def test_inspection_commands_and_hypotheses_are_pure(self):
        agent = load_demo()
        session = ShellSession(agent)
        before = state(agent)
        for request in (":help", ":status", ":beliefs", ":preview", "clear(forest).",
                        ":explain at(start)", ":query not clear(bridge)",
                        "suppose(clear(forest)) { prove(clear(forest)). }"):
            with self.subTest(request=request):
                self.assertTrue(session.execute(request))
                self.assertEqual(state(agent), before)
        self.assertIsNone(session.last_result)

    def test_steps_continue_the_same_intention_and_queries_see_live_beliefs(self):
        session = ShellSession(load_demo())
        self.assertIn("unknown: clear(bridge)", session.execute("clear(bridge)."))
        first = session.execute(":step")
        self.assertIn("1. observe clear(bridge)", first)
        self.assertIn("false: clear(bridge)", session.execute("clear(bridge)."))
        second = session.execute(":step 2")
        self.assertNotIn("1. observe", second)
        self.assertIn("Released intention 1: requirements_failed", second)
        self.assertIn("true: at(forest)", session.execute(":query at(forest)"))
        self.assertIn("next step 3 of 4", session.execute(":status"))
        self.assertIn("simulator:step_3", session.execute(":explain at(forest)"))
        self.assertIn("Next operation: observe clear(goal)", session.execute(":preview"))
        self.assertIn("Result: achieved", session.execute(":run"))
        self.assertEqual(session.last_result, load_demo().run())

    def test_trace_and_export_retain_cumulative_history_without_advancing(self):
        session = ShellSession(load_demo())
        session.execute(":step 3")
        session.execute(":run")
        before = state(session.agent)
        self.assertIn("simulator:step_4", session.execute(":trace"))
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "nested folder" / "agent trace.json"
            session.execute(f':save "{target}"')
            saved = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(saved, session.last_result)
            self.assertEqual(saved["steps"], 5)
        self.assertEqual(state(session.agent), before)

    def test_invalid_commands_do_not_advance_or_reset_session(self):
        session = ShellSession(load_demo())
        session.execute(":step")
        before = state(session.agent)
        for request in (":unknown", ":step -1", ":step 1.5", ":run many", ":run 1 2",
                        ":run ١", ":status extra", ":quit now", ":query", ":explain", ":save", ':save ""'):
            with self.subTest(request=request), self.assertRaises(KGodelError):
                session.execute(request)
            self.assertEqual(state(session.agent), before)

    def test_blank_input_and_quit_have_no_effects(self):
        session = ShellSession(load_demo())
        before = state(session.agent)
        self.assertEqual(session.execute(" \t "), "")
        self.assertIsNone(session.execute(":quit"))
        self.assertEqual(state(session.agent), before)

    def test_bare_predicates_named_like_shell_commands_remain_queries(self):
        session = ShellSession(load_demo())
        self.assertIn("unknown: run", session.execute("run."))
        self.assertEqual(session.agent.events, [])

    def test_trace_and_save_require_an_execution_record(self):
        session = ShellSession(load_demo())
        for request in (":trace", ":save unused.json"):
            with self.subTest(request=request), self.assertRaisesRegex(KGodelError, "No execution record"):
                session.execute(request)

    def test_zero_budget_records_status_without_performing_operations(self):
        session = ShellSession(load_demo())
        self.assertIn("step_limit", session.execute(":step 0"))
        self.assertEqual(session.last_result["steps"], 0)

    def test_hypothesis_budget_applies_to_queries_and_execution(self):
        session = ShellSession(load_demo(), max_hypotheses=0)
        self.assertIn("error", session.execute("suppose(clear(a)) { prove(clear(a)). }"))
        self.assertIn("reasoning_error", session.execute(":preview"))
        self.assertIn("reasoning_error", session.execute(":step"))
        self.assertEqual(session.agent.world.observation_calls, 0)
        with self.assertRaisesRegex(KGodelError, "nonnegative"):
            ShellSession(load_demo(), max_hypotheses=-1)

    def test_knowledge_conflict_remains_inspectable(self):
        program = parse("""agent test {
            belief ready. belief not safe. rule safe :- clear(a). goal done.
            plan inspect for done { when ready. observe clear(a). }
        }""")
        session = ShellSession(Agent(program, RouteWorld("a", [], [])))
        self.assertIn("reasoning_error", session.execute(":step"))
        self.assertIn("clear(a) [simulator:step_1]", session.execute(":beliefs"))
        self.assertIn("Knowledge conflict", session.execute(":trace"))
        with self.assertRaisesRegex(KGodelError, "Knowledge conflict"):
            session.execute(":status")

    def test_shell_recovers_from_bad_input_and_preserves_progress(self):
        agent = load_demo()
        requests = [":step", "invalid(", ":unknown", ":step -1", ":run", ":status", ":quit"]
        with patch("builtins.input", side_effect=requests), redirect_stdout(io.StringIO()) as output:
            code = run_shell(agent)
        self.assertEqual(code, 0)
        self.assertEqual(len(agent.events), 5)
        self.assertIn("KGodel error:", output.getvalue())
        self.assertIn("all goals supported", output.getvalue())

    def test_eof_and_interrupt_end_without_operations(self):
        for exception, expected in ((EOFError, 0), (KeyboardInterrupt, 130)):
            with self.subTest(exception=exception):
                agent = load_demo()
                with patch("builtins.input", side_effect=exception), redirect_stdout(io.StringIO()):
                    self.assertEqual(run_shell(agent), expected)
                self.assertEqual(agent.events, [])

    def test_cli_shell_accepts_bundled_demo_or_program_file(self):
        for arguments in (["shell", "--demo", "multistep-route"],
                          ["shell", str(ROOT / "examples" / "multistep_route.kg")]):
            with self.subTest(arguments=arguments), patch("builtins.input", side_effect=[":step", ":quit"]):
                with redirect_stdout(io.StringIO()) as output:
                    code = main(arguments)
                self.assertEqual(code, 0)
                self.assertIn("1. observe clear(bridge)", output.getvalue())

    def test_cli_rejects_ambiguous_or_missing_shell_source(self):
        for arguments in (["shell"], ["shell", "example.kg", "--demo", "multistep-route"],
                          ["shell", "--demo", "multistep-route", "--world", "ignored.json"]):
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(arguments)
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

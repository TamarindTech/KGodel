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
from kgodel.parser import parse, parse_query
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import (MAX_BYTES, dumps_session, load_session, loads_session,
                             program_source, save_session)
from kgodel.shell import ShellSession


def state(agent):
    return copy.deepcopy((agent.program, agent.knowledge.facts, agent.events, agent.decisions,
                          agent.attempts, agent.intention, agent.intention_events,
                          agent._next_intention_id, agent._last_outcome, agent.world.__dict__))


class CheckpointTests(unittest.TestCase):
    def test_every_demo_restores_at_every_operation_boundary(self):
        for name in DEMOS:
            expected = load_demo(name).run()
            for pause in range(expected["steps"] + 2):
                with self.subTest(name=name, pause=pause):
                    original = load_demo(name)
                    original.run(pause)
                    restored = loads_session(dumps_session(original))
                    self.assertEqual(state(restored), state(original))
                    self.assertEqual(restored.run(), original.run())
                    self.assertEqual(state(restored), state(original))
                    self.assertEqual(restored.world.position, "goal")
                    self.assertEqual(len(restored.events), expected["steps"])

    def test_saving_and_loading_do_not_execute_or_mutate_an_agent(self):
        agent = load_demo()
        agent.run(3)
        before = state(agent)
        with patch.object(RouteWorld, "act", side_effect=AssertionError("action replay")), \
                patch.object(RouteWorld, "observe", side_effect=AssertionError("observation replay")), \
                patch.object(Agent, "run", side_effect=AssertionError("run during restore")):
            restored = loads_session(dumps_session(agent))
        self.assertEqual(state(agent), before)
        self.assertEqual(state(restored), before)
        self.assertIn("simulator:step_3", ShellSession(restored).execute(":explain at(forest)"))

    def test_fresh_checkpoint_can_be_created_before_any_run(self):
        agent = load_demo()
        restored = loads_session(dumps_session(agent))
        self.assertEqual(state(restored), state(agent))
        self.assertIsNone(restored.execution_record())
        self.assertEqual(restored.run()["status"], "achieved")

    def test_restored_agents_do_not_share_mutable_state(self):
        agent = load_demo()
        agent.run(3)
        before = state(agent)
        source = dumps_session(agent)
        first, second = loads_session(source), loads_session(source)
        first.run()
        self.assertEqual(state(agent), before)
        self.assertEqual(state(second), before)

    def test_self_contained_program_handles_quoted_constants_and_nested_hypotheses(self):
        program = parse(r'''agent quoted {
            belief at("start space"). belief path("start space", "goal\\\"\n").
            rule ready(X) :- clear(X).
            goal at("goal\\\"\n").
            plan travel(X, Y) for at(Y) priority 7 {
                when at(X), path(X, Y), unknown(clear(Y)).
                suppose(clear(Y)) { suppose(ready(Y)) { prove(ready(Y)). } }
                observe clear(Y).
                require ready(Y), not at(Y).
                act move(X, Y).
            }
        }''')
        self.assertEqual(parse(program_source(program)), program)
        destination = program.goals[0].args[0]
        agent = Agent(program, RouteWorld("start space", [["start space", destination]], []))
        agent.run(1)
        restored = loads_session(dumps_session(agent))
        self.assertEqual(state(restored), state(agent))
        self.assertEqual(restored.run(), agent.run())

    def test_unknown_location_failure_and_retry_suppression_survive_restore(self):
        program = parse("""agent test {
            belief ready. goal done.
            plan inspect for done { when ready. observe clear(missing). }
        }""")
        agent = Agent(program, RouteWorld("a", [], []))
        self.assertEqual(agent.run()["status"], "stuck")
        restored = loads_session(dumps_session(agent))
        result = restored.run()
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(restored.world.observation_calls, 1)
        self.assertEqual(result, agent.run())

    def test_derived_conflict_remains_inspectable_after_restore(self):
        program = parse("""agent test {
            belief ready. belief not safe. rule safe :- clear(a). goal done.
            plan inspect for done { when ready. observe clear(a). observe clear(a). }
        }""")
        agent = Agent(program, RouteWorld("a", [], []))
        self.assertEqual(agent.run()["status"], "reasoning_error")
        restored = loads_session(dumps_session(agent))
        self.assertEqual(state(restored), state(agent))
        self.assertIn("Knowledge conflict", ShellSession(restored).execute(":trace"))
        self.assertEqual(restored.run()["status"], "reasoning_error")
        self.assertEqual(restored.world.observation_calls, 1)

    def test_checkpoint_does_not_release_an_intention_with_a_newly_supported_goal(self):
        agent = load_demo()
        agent.run(3)
        agent.knowledge.observe(parse_query("at(goal)"), "test:external_evidence")
        before = state(agent)
        restored = loads_session(dumps_session(agent))
        self.assertEqual(state(agent), before)
        self.assertEqual(state(restored), before)
        self.assertIsNotNone(restored.intention)
        result = restored.run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["steps"], 3)
        self.assertIsNone(restored.intention)

    def test_world_nodes_are_preserved_independently_of_current_position(self):
        agent = load_demo()
        agent.run(3)
        agent.world.nodes.add("old isolated location")
        agent.world.blocked.add("old isolated location")
        restored = loads_session(dumps_session(agent))
        self.assertEqual(restored.world.__dict__, agent.world.__dict__)

    def test_invalid_json_and_trace_exports_are_rejected(self):
        for value in ("", "{", "[]", "null", '{"format":"one","format":"two"}',
                      '{"value":NaN}', json.dumps(load_demo().run()), "[" * 2000):
            with self.subTest(value=value[:50]), self.assertRaises(KGodelError):
                loads_session(value)

    def test_incompatible_or_damaged_state_is_rejected_without_operations(self):
        agent = load_demo()
        agent.run(3)
        good = json.loads(dumps_session(agent))
        mutations = [
            lambda d: d.update(schema_version=99),
            lambda d: d.update(schema_version=True),
            lambda d: d.update(format="trace"),
            lambda d: d.update(extra="unexpected"),
            lambda d: d.update(program="agent missing {"),
            lambda d: d.update(beliefs=d["beliefs"] + [d["beliefs"][0]]),
            lambda d: d["beliefs"][0].update(conclusion="at(X)"),
            lambda d: d["beliefs"][0].update(premises={}),
            lambda d: d["world"].update(nodes=[]),
            lambda d: d["world"].update(action_calls=True),
            lambda d: d["world"].update(observation_calls=999),
            lambda d: d["intention"].update(next_step=1),
            lambda d: d["intention"].update(next_step=99),
            lambda d: d["intention"].update(next_step=2),
            lambda d: d["intention"].update(bindings={}),
            lambda d: d["intention"].update(plan="missing"),
            lambda d: d["intention"].update(goal="at(other)"),
            lambda d: d.update(attempts=[]),
            lambda d: d.update(intention=None),
            lambda d: d.update(next_intention_id=1),
            lambda d: d["events"][0].update(decision=999),
            lambda d: d["events"][0].update(operation="delete"),
            lambda d: d["events"][0].update(plan_step=2),
            lambda d: d["events"][-1].update(success=False),
            lambda d: d.update(intention_events=[]),
            lambda d: d.update(last_outcome=None),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index), self.assertRaises(KGodelError), \
                    patch.object(RouteWorld, "act", side_effect=AssertionError("replay")), \
                    patch.object(RouteWorld, "observe", side_effect=AssertionError("replay")):
                damaged = copy.deepcopy(good)
                mutate(damaged)
                loads_session(json.dumps(damaged))

    def test_unsupported_world_adapter_is_not_silently_converted(self):
        class OtherWorld(RouteWorld):
            pass
        agent = load_demo()
        agent.world = OtherWorld("start", [], [])
        with self.assertRaisesRegex(KGodelError, "built-in route simulator"):
            dumps_session(agent)

    def test_atomic_replacement_and_nested_paths(self):
        agent = load_demo()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested folder" / "session.json"
            save_session(agent, path)
            agent.run(3)
            save_session(agent, path)
            self.assertEqual(state(load_session(path)), state(agent))
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_failed_replace_keeps_previous_checkpoint_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            agent = load_demo()
            save_session(agent, path)
            before = path.read_bytes()
            agent.run(3)
            with patch("kgodel.sessions.os.replace", side_effect=OSError("disk failure")), \
                    self.assertRaisesRegex(OSError, "disk failure"):
                save_session(agent, path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_failed_validation_preserves_existing_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            agent = load_demo()
            save_session(agent, path)
            before = path.read_bytes()
            agent.world.action_calls = -1
            with self.assertRaises(KGodelError):
                save_session(agent, path)
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_encoding_missing_file_and_size_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            with self.assertRaises(FileNotFoundError):
                load_session(path)
            path.write_bytes(b"\xff\xfe\x00")
            with self.assertRaisesRegex(KGodelError, "UTF-8"):
                load_session(path)
            with patch("kgodel.sessions.MAX_BYTES", 16):
                path.write_bytes(b" " * 17)
                with self.assertRaisesRegex(KGodelError, "exceeds"):
                    load_session(path)
                with self.assertRaisesRegex(KGodelError, "exceeds"):
                    loads_session(" " * 17)
            self.assertEqual(MAX_BYTES, 32 * 1024 * 1024)


class SessionCommandTests(unittest.TestCase):
    def test_cli_checkpoint_resume_matches_uninterrupted_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            trace = Path(temporary) / "result.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["demo", "--max-steps", "3", "--checkpoint", str(path)]), 1)
                self.assertEqual(main(["resume", str(path), "--checkpoint", str(path), "--trace-json", str(trace)]), 0)
            self.assertEqual(json.loads(trace.read_text()), load_demo().run())
            self.assertIsNone(load_session(path).intention)

    def test_resume_does_not_overwrite_input_without_explicit_checkpoint_option(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            agent = load_demo()
            agent.run(3)
            save_session(agent, path)
            before = path.read_bytes()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["resume", str(path)]), 0)
            self.assertEqual(path.read_bytes(), before)

    def test_shell_can_save_before_execution_and_inspect_a_resumed_trace(self):
        session = ShellSession(load_demo())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint with spaces.json"
            self.assertIn("Saved resumable", session.execute(f':checkpoint "{path}"'))
            self.assertEqual(load_session(path).events, [])
            session.execute(":step 3")
            before = state(session.agent)
            session.execute(f':checkpoint "{path}"')
            self.assertEqual(state(session.agent), before)
            requests = [":status", ":trace", ":explain at(forest)", ":preview", ":run", ":quit"]
            with patch("builtins.input", side_effect=requests), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["shell", "--resume", str(path)]), 0)
            self.assertIn("next step 3 of 4", output.getvalue())
            self.assertIn("simulator:step_3", output.getvalue())
            self.assertIn("Result: achieved", output.getvalue())
            self.assertEqual(len(load_session(path).events), 3)

    def test_missing_or_bad_checkpoint_reports_input_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.json"
            for content in (None, "{", json.dumps(load_demo().run())):
                if content is not None:
                    path.write_text(content)
                for command in (["resume", str(path)], ["shell", "--resume", str(path)]):
                    with redirect_stderr(io.StringIO()) as output:
                        self.assertEqual(main(command), 2)
                    self.assertIn("KGodel error", output.getvalue())
                    self.assertNotIn("Traceback", output.getvalue())

    def test_ambiguous_options_and_empty_checkpoint_paths_are_rejected(self):
        for args in (["shell", "--demo", "multistep-route", "--resume", "session.json"],
                     ["shell", "--resume", "session.json", "--world", "world.json"],
                     ["demo", "--list", "--checkpoint", "session.json"]):
            with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(args)
        for command in (":checkpoint", ':checkpoint ""'):
            with self.subTest(command=command), self.assertRaises(KGodelError):
                ShellSession(load_demo()).execute(command)


if __name__ == "__main__":
    unittest.main()

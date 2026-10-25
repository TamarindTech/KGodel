import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kgodel.__main__ import main
from kgodel.comparison import compare_agents, format_comparison
from kgodel.demos import load_demo
from kgodel.logic import Inference
from kgodel.model import KGodelError
from kgodel.parser import parse, parse_query
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import dumps_session, load_session, loads_session, save_session
from kgodel.shell import ShellSession


def clone(agent):
    return loads_session(dumps_session(agent))


def question(rows, literal):
    return next(row for row in rows if row["literal"] == literal)


class ComparisonTests(unittest.TestCase):
    def test_identical_sessions_have_no_changes_and_stable_json(self):
        agent = load_demo()
        agent.run(3)
        report = compare_agents(agent, clone(agent))
        self.assertEqual(report["status"], "ok")
        self.assertFalse(report["changed"])
        self.assertFalse(any(report["beliefs"].values()))
        self.assertEqual(report["consequences"]["changes"], [])
        self.assertEqual(report["history"]["operations"]["relation"], "equal")
        self.assertIn("No state changes.", format_comparison(report))
        self.assertEqual(json.loads(json.dumps(report)), report)
        self.assertEqual(compare_agents(agent, clone(agent)), report)

    def test_blockage_revises_evidence_and_withdraws_a_derived_conclusion(self):
        before = load_demo("blocked-route")
        after = clone(before)
        after.run(1)
        report = compare_agents(before, after, queries=["can_move(start, bridge)"])
        revised = report["beliefs"]["revised"]
        self.assertEqual(len(revised), 1)
        self.assertEqual(revised[0]["before"]["conclusion"], "clear(bridge)")
        self.assertEqual(revised[0]["after"]["conclusion"], "not clear(bridge)")
        self.assertEqual(revised[0]["after"]["source"], "simulator:step_1")
        self.assertEqual(report["beliefs"]["added"], [])
        row = question(report["consequences"]["changes"], "can_move(start, bridge)")
        self.assertEqual((row["before"]["status"], row["after"]["status"]), ("true", "unknown"))
        self.assertIsNone(row["after"]["proof"])
        self.assertIn("clear(bridge)", str(row["before"]["proof"]))
        self.assertEqual(report["queries"], [row])

    def test_repeated_observation_changes_evidence_without_changing_truth(self):
        before = load_demo("blocked-route")
        after = clone(before)
        after.knowledge.observe(parse_query("clear(bridge)"), "test:new_evidence")
        report = compare_agents(before, after, queries=["clear(bridge)"])
        self.assertTrue(report["changed"])
        self.assertEqual(len(report["beliefs"]["evidence_changed"]), 1)
        row = report["queries"][0]
        self.assertFalse(row["truth_changed"])
        self.assertTrue(row["evidence_changed"])
        derived = question(report["consequences"]["changes"], "can_move(start, bridge)")
        self.assertFalse(derived["truth_changed"])
        self.assertTrue(derived["evidence_changed"])

    def test_alternative_proof_keeps_a_conclusion_supported(self):
        program = parse("""agent test {
            belief primary. belief backup.
            rule ready :- primary. rule ready :- backup. goal ready.
        }""")
        before = Agent(program, RouteWorld("a", [], []))
        after = clone(before)
        after.knowledge.observe(parse_query("not primary"), "test:revision")
        row = question(compare_agents(before, after)["consequences"]["changes"], "ready")
        self.assertEqual(row["before"]["proof"]["source"], "rule_1")
        self.assertEqual(row["after"]["proof"]["source"], "rule_2")
        self.assertFalse(row["truth_changed"])
        self.assertTrue(row["evidence_changed"])

    def test_false_query_returns_opposing_proof_and_unknown_has_none(self):
        before = load_demo("blocked-route")
        after = clone(before)
        after.run(1)
        rows = compare_agents(before, after, queries=["clear(bridge)", "not clear(bridge)", "missing"])["queries"]
        self.assertEqual(rows[0]["after"]["status"], "false")
        self.assertEqual(rows[0]["after"]["proof"]["conclusion"], "not clear(bridge)")
        self.assertEqual(rows[1]["after"]["status"], "true")
        self.assertEqual(rows[2]["after"], {"status": "unknown", "proof": None})

    def test_intention_progress_goal_support_and_cumulative_history(self):
        before = load_demo()
        before.run(3)
        after = clone(before)
        after.run()
        report = compare_agents(before, after)
        self.assertEqual(report["intention"]["before"]["next_step"], 3)
        self.assertIsNone(report["intention"]["after"])
        self.assertEqual(report["world"]["position"], {"before": "forest", "after": "goal", "changed": True})
        self.assertEqual(report["goals"][0]["after"]["status"], "true")
        history = report["history"]["operations"]
        self.assertEqual(history["common_prefix"], 3)
        self.assertEqual([row["step"] for row in history["after_tail"]], [4, 5])
        self.assertEqual(history["before_tail"], [])

    def test_reverse_comparison_reverses_changes_without_assuming_time_order(self):
        before = load_demo("blocked-route")
        after = clone(before)
        after.run(1)
        report = compare_agents(after, before)
        self.assertEqual(report["history"]["operations"]["relation"], "before_extends_after")
        self.assertEqual(report["beliefs"]["revised"][0]["after"]["conclusion"], "clear(bridge)")
        self.assertEqual(report["world"]["action_calls"]["after"], 0)

    def test_different_scenarios_have_diverged_histories_and_distinct_worlds(self):
        before, after = load_demo(), load_demo()
        after.world.blocked.clear()
        before.run()
        after.run()
        report = compare_agents(before, after)
        self.assertEqual(report["history"]["operations"]["relation"], "diverged")
        self.assertEqual(report["history"]["operations"]["common_prefix"], 0)
        self.assertEqual(report["world"]["blocked"]["removed"], ["bridge"])
        self.assertEqual(report["program"]["changed_sections"], [])

    def test_program_changes_and_goal_declarations_are_explicit(self):
        before = Agent(parse("agent first { belief ready. goal ready. }"), RouteWorld("a", [], []))
        after = Agent(parse("agent second { belief ready. goal done. }"), RouteWorld("a", [], []))
        report = compare_agents(before, after)
        self.assertEqual(report["program"]["changed_sections"], ["name", "goals"])
        ready = question(report["goals"], "ready")
        self.assertTrue(ready["before"]["declared"])
        self.assertFalse(ready["after"]["declared"])
        self.assertEqual(ready["after"]["status"], "true")
        self.assertIn("Goal declaration removed.", format_comparison(report))

    def test_world_edges_nodes_and_blocked_locations_are_compared(self):
        before, after = load_demo(), load_demo()
        after.world.edges.add(("goal", "return"))
        after.world.nodes.add("return")
        after.world.blocked.add("return")
        report = compare_agents(before, after)
        self.assertTrue(report["changed"])
        self.assertEqual(report["world"]["edges"]["added"], [["goal", "return"]])
        self.assertEqual(report["world"]["nodes"]["added"], ["return"])
        self.assertEqual(report["world"]["blocked"]["added"], ["return"])

    def test_reasoning_conflict_keeps_base_differences_and_marks_answers_unresolved(self):
        before = Agent(parse("""agent test { belief ready. belief not safe.
            rule safe :- clear(a). goal done.
            plan inspect for done { when ready. observe clear(a). }
        }"""), RouteWorld("a", [], []))
        after = clone(before)
        after.run()
        report = compare_agents(before, after, queries=["safe"])
        self.assertEqual(report["status"], "partial")
        self.assertIn("Knowledge conflict", report["reasoning"]["after"]["error"])
        self.assertEqual(report["queries"][0]["after"]["status"], "unresolved")
        self.assertIsNone(report["queries"][0]["truth_changed"])
        self.assertEqual(report["consequences"], {"status": "unavailable", "changes": []})
        self.assertEqual(report["beliefs"]["added"][0]["conclusion"], "clear(a)")
        self.assertIn("Comparison: partial", format_comparison(report))

    def test_limits_are_per_side_and_do_not_turn_incomplete_reasoning_into_false(self):
        before, after = load_demo(), load_demo()
        for limits in ({"max_work": 0}, {"max_facts": 0}):
            with self.subTest(limits=limits):
                report = compare_agents(before, after, queries=["at(start)"], **limits)
                self.assertFalse(report["changed"])
                self.assertEqual(report["status"], "partial")
                self.assertEqual(report["queries"][0]["before"]["status"], "unresolved")
                self.assertIsNone(report["queries"][0]["evidence_changed"])
        for invalid in (-1, True, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(KGodelError):
                compare_agents(before, after, max_work=invalid)

    def test_checkpoint_loading_does_not_spend_a_hidden_inference_budget(self):
        agent = load_demo()
        agent.run(3)
        source = dumps_session(agent)
        with patch.object(Inference, "__init__", side_effect=AssertionError("hidden inference")):
            restored = loads_session(source)
        self.assertEqual(restored.intention, agent.intention)

    def test_comparison_and_returned_report_do_not_mutate_either_agent(self):
        before, after = load_demo(), load_demo()
        after.run(3)
        snapshots = (dumps_session(before), dumps_session(after))
        with patch.object(Agent, "run", side_effect=AssertionError("run")), \
                patch.object(RouteWorld, "act", side_effect=AssertionError("act")), \
                patch.object(RouteWorld, "observe", side_effect=AssertionError("observe")):
            report = compare_agents(before, after)
            format_comparison(report, explain=True)
        report["history"]["operations"]["after_tail"][0]["detail"] = "changed outside"
        report["intention"]["after"]["bindings"].clear()
        report["beliefs"]["added"][0]["source"] = "changed outside"
        self.assertEqual((dumps_session(before), dumps_session(after)), snapshots)

    def test_queries_are_ground_literals_deduplicated_in_request_order(self):
        agent = load_demo()
        report = compare_agents(agent, agent, queries=["at(start).", "missing", "at(start)"])
        self.assertEqual([row["literal"] for row in report["queries"]], ["at(start)", "missing"])
        for queries in (["at(X)"], ["suppose(ready) { prove(ready). }"], ["prove(at(start))"], [42], "ready"):
            with self.subTest(queries=queries), self.assertRaises(KGodelError):
                compare_agents(agent, agent, queries=queries)
        self.assertEqual(compare_agents(agent, agent, queries=["prove(ready)"])["queries"][0]["literal"],
                         "prove(ready)")

    def test_attempt_only_and_zero_budget_history_changes_are_visible(self):
        before = load_demo()
        before.run(3)
        after = clone(before)
        after.attempts.clear()
        report = compare_agents(before, after)
        self.assertTrue(report["changed"])
        self.assertTrue(report["attempts"]["removed"])
        before, after = load_demo(), load_demo()
        after.run(0)
        report = compare_agents(before, after)
        self.assertTrue(report["changed"])
        self.assertEqual(report["history"]["operations"]["relation"], "equal")
        self.assertTrue(report["last_outcome"]["changed"])


class ComparisonCommandTests(unittest.TestCase):
    def test_cli_compares_files_and_exports_without_overwriting_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second, result = root / "before.json", root / "after.json", root / "comparison.json"
            before = load_demo("blocked-route")
            after = clone(before)
            after.run(1)
            save_session(before, first)
            save_session(after, second)
            content = first.read_bytes(), second.read_bytes()
            with redirect_stdout(io.StringIO()) as output:
                code = main(["compare", str(first), str(second), "--query", "not clear(bridge)",
                             "--query", "at(goal)", "--explain", "--result-json", str(result)])
            self.assertEqual(code, 0)
            self.assertIn("not clear(bridge): false -> true", output.getvalue())
            report = json.loads(result.read_text())
            self.assertEqual(report, compare_agents(before, after, queries=["not clear(bridge)", "at(goal)"]))
            self.assertEqual((first.read_bytes(), second.read_bytes()), content)

    def test_cli_exit_codes_for_equal_states_partial_reasoning_and_bad_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            save_session(load_demo(), path)
            args = ["compare", str(path), str(path)]
            for suffix, expected in (([], 0), (["--max-work", "0"], 1), (["--max-facts", "0"], 1),
                                     (["--max-work", "-1"], 2), (["--query", "at(X)"], 2)):
                with self.subTest(suffix=suffix), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(main(args + suffix), expected)
            path.write_text("{")
            with redirect_stderr(io.StringIO()) as output:
                self.assertEqual(main(args), 2)
            self.assertNotIn("Traceback", output.getvalue())

    def test_output_cannot_replace_checkpoint_or_a_hardlink_to_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            alias = Path(temporary) / "alias.json"
            save_session(load_demo(), path)
            os.link(path, alias)
            before = path.read_bytes()
            for target in (path, alias):
                with self.subTest(target=target), redirect_stderr(io.StringIO()) as output:
                    self.assertEqual(main(["compare", str(path), str(path), "--result-json", str(target)]), 2)
                self.assertIn("must not overwrite", output.getvalue())
            self.assertEqual(path.read_bytes(), before)

    def test_shell_compares_saved_baseline_to_live_state_and_recovers_from_bad_path(self):
        session = ShellSession(load_demo())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "saved baseline.json"
            session.execute(f':checkpoint "{path}"')
            session.execute(":step 3")
            before = dumps_session(session.agent)
            last = copy.deepcopy(session.last_result)
            rendered = session.execute(f':compare "{path}"')
            self.assertIn("position: start -> forest", rendered)
            self.assertIn("step 3 of 4", rendered)
            self.assertEqual(dumps_session(session.agent), before)
            self.assertEqual(session.last_result, last)
            for request in (":compare", ':compare ""'):
                with self.assertRaises(KGodelError):
                    session.execute(request)
            with self.assertRaises(OSError):
                session.execute(f':compare "{path}.missing"')
            self.assertIn("Result: achieved", session.execute(":run"))

    def test_comparison_accepts_schema_one_checkpoint_from_version_six(self):
        source = json.loads(dumps_session(load_demo()))
        source["kgodel_version"] = "0.6.0"
        source["schema_version"] = 1
        restored = loads_session(json.dumps(source))
        self.assertFalse(compare_agents(restored, load_demo())["changed"])


if __name__ == "__main__":
    unittest.main()

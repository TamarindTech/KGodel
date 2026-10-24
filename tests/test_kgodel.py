from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from kgodel.__main__ import main
from kgodel.logic import Inference, Knowledge
from kgodel.model import Atom, KGodelError, Literal, Var, match
from kgodel.parser import parse, parse_query
from kgodel.runtime import Agent, RouteWorld


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "blocked_route.kg"


def engine(source):
    program = parse("agent test { " + source + " }")
    return Inference(Knowledge(program.beliefs), program.rules)


def demo():
    program = parse(EXAMPLE.read_text(encoding="utf-8"))
    world = RouteWorld.from_json(EXAMPLE.with_suffix(".world.json").read_text(encoding="utf-8"))
    return Agent(program, world)


class LogicTests(unittest.TestCase):
    def test_unknown_is_not_false(self):
        logic = engine("belief clear(a). belief not clear(b).")
        self.assertEqual([logic.status(parse_query(f"clear({x})")) for x in ("a", "b", "c")],
                         ["true", "false", "unknown"])
        self.assertEqual(logic.status(parse_query("not clear(b)")), "true")
        self.assertEqual(logic.status(parse_query("not clear(c)")), "unknown")

    def test_repeated_variables_unify_consistently(self):
        pattern = Atom("edge", (Var("X"), Var("X")))
        self.assertIsNone(match(pattern, Atom("edge", ("a", "b"))))
        self.assertEqual(match(pattern, Atom("edge", ("a", "a"))), {"X": "a"})

    def test_recursive_rules_terminate_on_cycle(self):
        logic = engine("""
            belief edge(a, b). belief edge(b, a). belief edge(b, c).
            rule reach(X, Y) :- edge(X, Y).
            rule reach(X, Y) :- edge(X, Z), reach(Z, Y).
        """)
        answers = {bindings["Y"] for bindings, _ in logic.solve((parse_query("reach(a, Y)"),))}
        self.assertEqual(answers, {"a", "b", "c"})

    def test_explicit_negative_rule_body_and_head(self):
        logic = engine("belief not clear(bridge). rule not usable(X) :- not clear(X).")
        self.assertEqual(logic.status(parse_query("usable(bridge)")), "false")
        self.assertEqual(logic.status(parse_query("usable(forest)")), "unknown")

    def test_initial_conflict_rejected(self):
        with self.assertRaisesRegex(KGodelError, "Conflicting initial"):
            engine("belief clear(a). belief not clear(a).")

    def test_derived_conflict_rejected(self):
        with self.assertRaisesRegex(KGodelError, "Knowledge conflict"):
            engine("belief clear(a). belief blocked(a). rule not clear(X) :- blocked(X).")

    def test_revision_invalidates_dependent_conclusions(self):
        program = parse("""agent test {
            belief clear(a).
            rule usable(X) :- clear(X).
            rule reachable(X) :- usable(X).
        }""")
        knowledge = Knowledge(program.beliefs)
        before = Inference(knowledge, program.rules)
        self.assertEqual(before.status(parse_query("reachable(a)")), "true")
        change = knowledge.observe(parse_query("not clear(a)"), "sensor")
        after = Inference(knowledge, program.rules)
        self.assertEqual(change["retracted"], "clear(a)")
        self.assertEqual(after.status(parse_query("clear(a)")), "false")
        self.assertEqual(after.status(parse_query("reachable(a)")), "unknown")

    def test_alternative_support_survives_revision(self):
        program = parse("""agent test {
            belief clear(a). belief exception(a).
            rule usable(X) :- clear(X).
            rule usable(X) :- exception(X).
        }""")
        knowledge = Knowledge(program.beliefs)
        knowledge.observe(parse_query("not clear(a)"), "sensor")
        logic = Inference(knowledge, program.rules)
        self.assertEqual(logic.status(parse_query("usable(a)")), "true")
        proof = logic.explanation(parse_query("usable(a)")).as_dict()
        self.assertEqual(proof["premises"][0]["conclusion"], "exception(a)")

    def test_explanation_tracks_rule_and_source(self):
        logic = engine("belief clear(a). rule usable(X) :- clear(X).")
        proof = logic.explanation(parse_query("usable(a)")).as_dict()
        self.assertEqual(proof["source"], "rule_1")
        self.assertEqual(proof["premises"][0]["source"], "program")

    def test_budget_exhaustion_is_error_not_false(self):
        program = parse("agent test { belief p(a). rule q(X) :- p(X). }")
        with self.assertRaisesRegex(KGodelError, "work limit"):
            Inference(Knowledge(program.beliefs), program.rules, max_work=0)
        with self.assertRaisesRegex(KGodelError, "fact limit"):
            Inference(Knowledge(program.beliefs), program.rules, max_facts=1)


class ParserTests(unittest.TestCase):
    def test_quoted_constants_and_comments(self):
        logic = engine('% comment\nbelief at("Room A"). // comment\n')
        self.assertEqual(logic.status(parse_query('at("Room A").')), "true")

    def test_unsafe_rule_rejected(self):
        with self.assertRaisesRegex(KGodelError, "rule-head"):
            parse("agent test { rule p(X) :- q(Y). }")

    def test_variable_beliefs_and_goals_rejected(self):
        for source in ("belief at(X).", "goal at(X)."):
            with self.subTest(source=source), self.assertRaisesRegex(KGodelError, "ground"):
                parse("agent test { " + source + " }")

    def test_unbound_plan_variable_rejected(self):
        with self.assertRaisesRegex(KGodelError, "unbound variables"):
            parse("""agent test {
                plan inspect(X) for done { when unknown(clear(X)). observe clear(X). }
            }""")

    def test_malformed_source_reports_location(self):
        with self.assertRaisesRegex(KGodelError, r"Line 3, column 1"):
            parse("agent test {\n belief p(a)\n}")

    def test_duplicate_plan_names_rejected(self):
        with self.assertRaisesRegex(KGodelError, "Duplicate plan"):
            parse("""agent test {
                plan go for done { when ready. act move(a, b). }
                plan go for done { when ready. act move(a, c). }
            }""")


class AgentTests(unittest.TestCase):
    def test_blocked_route_revises_belief_and_reaches_goal(self):
        agent = demo()
        result = agent.run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["world_position"], "goal")
        self.assertEqual(result["steps"], 5)
        self.assertEqual(result["action_calls"], 3)
        self.assertEqual(result["observation_calls"], 2)
        self.assertFalse(result["events"][0]["success"])
        self.assertEqual(result["events"][0]["belief_changes"][0]["retracted"], "clear(bridge)")
        self.assertIn("not clear(bridge)", result["beliefs"])
        self.assertNotIn("clear(bridge)", result["beliefs"])
        self.assertEqual(result["goals"], {"at(goal)": "true"})
        self.assertEqual(result["goal_proofs"]["at(goal)"]["source"], "simulator:step_5")

    def test_queries_do_not_execute_actions(self):
        agent = demo()
        for _ in range(3):
            list(agent.inference().solve((parse_query("can_move(X, Y)"),)))
        self.assertEqual(agent.world.action_calls, 0)
        self.assertEqual(agent.world.observation_calls, 0)
        self.assertEqual(agent.world.position, "start")

    def test_unknown_guard_excludes_known_negative(self):
        result = demo().run()
        observed = [event["argument"] for event in result["events"] if event["operation"] == "observe"]
        self.assertEqual(observed, ["clear(forest)", "clear(goal)"])

    def test_failed_move_does_not_claim_goal_achieved(self):
        agent = demo()
        result = agent.run(max_steps=1)
        self.assertEqual(result["status"], "step_limit")
        self.assertEqual(result["world_position"], "start")
        self.assertEqual(result["goals"]["at(goal)"], "unknown")

    def test_budget_checked_after_final_action(self):
        self.assertEqual(demo().run(max_steps=5)["status"], "achieved")
        self.assertEqual(demo().run(max_steps=0)["action_calls"], 0)

    def test_unreachable_goal_reports_stuck(self):
        agent = demo()
        agent.world.blocked.add("forest")
        result = agent.run()
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(result["world_position"], "start")
        self.assertEqual(result["action_calls"], 1)

    def test_failed_observation_not_repeated_without_belief_change(self):
        program = parse("""agent test {
            belief ready. goal done.
            plan inspect for done { when ready. observe clear(missing). }
        }""")
        agent = Agent(program, RouteWorld("a", [], []))
        result = agent.run()
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(result["observation_calls"], 1)
        self.assertEqual(result["steps"], 1)

    def test_repeatable_trace(self):
        self.assertEqual(demo().run(), demo().run())

    def test_resume_preserves_step_numbers_and_evidence_sources(self):
        agent = demo()
        self.assertEqual(agent.run(max_steps=1)["status"], "step_limit")
        result = agent.run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual([event["step"] for event in result["events"]], [1, 2, 3, 4, 5])
        self.assertEqual(result["goal_proofs"]["at(goal)"]["source"], "simulator:step_5")

    def test_wrong_location_reports_observed_location(self):
        world = RouteWorld("b", [["a", "c"]], [])
        outcome = world.act(parse_query("move(a, c)").atom)
        self.assertFalse(outcome.success)
        self.assertIn(parse_query("at(b)"), outcome.observations)
        self.assertEqual(world.position, "b")

    def test_missing_actual_path_revises_map(self):
        world = RouteWorld("a", [["b", "c"]], [])
        outcome = world.act(parse_query("move(a, c)").atom)
        self.assertFalse(outcome.success)
        self.assertIn(parse_query("not path(a, c)"), outcome.observations)

    def test_bad_world_is_rejected(self):
        for source in ('{}', '{"position":"a","edges":"bad","blocked":[]}',
                       '{"position":"a","edges":[],"blocked":["missing"]}'):
            with self.subTest(source=source), self.assertRaises(KGodelError):
                RouteWorld.from_json(source)

    def test_post_observation_conflict_stops_with_trace(self):
        program = parse("""agent test {
            belief ready. belief trusted.
            rule clear(b) :- trusted.
            goal done.
            plan inspect for done { when ready. observe clear(b). }
        }""")
        result = Agent(program, RouteWorld("a", [["a", "b"]], ["b"])).run()
        self.assertEqual(result["status"], "reasoning_error")
        self.assertEqual(result["steps"], 1)
        self.assertIn("Knowledge conflict", result["reason"])


class CliTests(unittest.TestCase):
    def test_demo_cli_writes_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "trace.json"
            process = subprocess.run([sys.executable, "-m", "kgodel", "run", str(EXAMPLE),
                                      "--trace-json", str(target)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            trace = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(trace["status"], "achieved")
            self.assertIn("Revised clear(bridge) -> not clear(bridge)", process.stdout)

    def test_variable_query_and_false_explanation(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(["query", str(EXAMPLE), "reachable(start, Destination)"])
        self.assertEqual(code, 0)
        self.assertIn("Destination = goal", stream.getvalue())
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(["explain", str(EXAMPLE), "not clear(bridge)"])
        self.assertEqual(code, 0)
        self.assertIn("false: not clear(bridge)", stream.getvalue())
        self.assertIn("clear(bridge) [program]", stream.getvalue())

    def test_missing_file_has_readable_error(self):
        stream = io.StringIO()
        with redirect_stderr(stream):
            code = main(["check", str(ROOT / "does-not-exist.kg")])
        self.assertEqual(code, 2)
        self.assertIn("KGodel error:", stream.getvalue())


if __name__ == "__main__":
    unittest.main()

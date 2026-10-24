import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

from kgodel.__main__ import main
from kgodel.logic import Knowledge
from kgodel.model import KGodelError
from kgodel.parser import parse, parse_query
from kgodel.planning import deliberate, format_decision
from kgodel.runtime import Agent, RouteWorld, format_trace


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "multistep_route.kg"


def program_with(body, *, beliefs="belief ready.", goals="goal done.", plans=""):
    return parse(f"agent test {{ {beliefs} {goals} plan sequence for done {{ when ready. {body} }} {plans} }}")


def demo():
    program = parse(EXAMPLE.read_text(encoding="utf-8"))
    world = RouteWorld.from_json(EXAMPLE.with_suffix(".world.json").read_text(encoding="utf-8"))
    return Agent(program, world)


class SequenceSyntaxTests(unittest.TestCase):
    def test_multiple_operations_with_optional_local_requirements(self):
        plan = program_with("observe clear(a). require clear(a), unknown(clear(b)). act move(a,b).").plans[0]
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].requirements, ())
        self.assertEqual([str(guard) for guard in plan.steps[1].requirements], ["clear(a)", "unknown(clear(b))"])
        self.assertEqual(plan.operation, "observe")
        self.assertEqual(str(plan.argument), "clear(a)")

    def test_requirements_apply_only_to_the_following_operation(self):
        plan = program_with("require ready. observe clear(a). observe clear(b).").plans[0]
        self.assertEqual(len(plan.steps[0].requirements), 1)
        self.assertEqual(plan.steps[1].requirements, ())

    def test_empty_plans_dangling_requirements_and_late_hypotheses_rejected(self):
        for body in ("", "require ready.", "require . observe clear(a).",
                     "require ready. require ready. observe clear(a).",
                     "observe clear(a). suppose(clear(b)) { prove(clear(b)). } observe clear(b)."):
            with self.subTest(body=body), self.assertRaises(KGodelError):
                program_with(body)

    def test_step_variables_must_be_bound_at_selection(self):
        for body in ("observe clear(a). act move(a, X).",
                     "observe clear(a). require node(X). observe clear(a).",
                     "require unknown(clear(X)). observe clear(a)."):
            with self.subTest(body=body), self.assertRaisesRegex(KGodelError, "unbound variables"):
                parse(f"agent test {{ goal done. plan sequence(X) for done {{ when ready. {body} }} }}")

    def test_variables_in_all_steps_must_be_declared(self):
        with self.assertRaisesRegex(KGodelError, "declare exactly"):
            parse("agent test { goal done. plan sequence for done { when node(X). observe clear(a). observe clear(X). } }")

    def test_simulator_validates_later_operations_before_any_execution(self):
        world = RouteWorld("a", [], [])
        with self.assertRaisesRegex(KGodelError, "does not support"):
            Agent(program_with("observe clear(a). act launch(a)."), world)
        self.assertEqual(world.observation_calls, 0)


class IntentionTests(unittest.TestCase):
    def test_demo_releases_blocked_route_and_completes_an_alternative(self):
        result = demo().run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual([event["argument"] for event in result["events"]],
                         ["clear(bridge)", "clear(forest)", "move(start, forest)", "clear(goal)", "move(forest, goal)"])
        self.assertEqual([event["intention"] for event in result["events"]], [1, 2, 2, 2, 2])
        self.assertEqual([event["plan_step"] for event in result["events"]], [1, 1, 2, 3, 4])
        self.assertEqual([event["status"] for event in result["intention_events"]],
                         ["committed", "requirements_failed", "committed", "completed"])
        self.assertEqual(result["action_calls"], 2)
        self.assertEqual(result["observation_calls"], 3)
        self.assertIsNone(result["active_intention"])
        self.assertEqual(result["goal_proofs"]["at(goal)"]["source"], "simulator:step_5")
        self.assertIn("requirements_failed", format_trace(result))

    def test_every_pause_boundary_resumes_without_replaying_operations(self):
        expected = demo().run()
        for boundary in range(6):
            with self.subTest(boundary=boundary):
                agent = demo()
                paused = agent.run(max_steps=boundary)
                if 0 < boundary < 5:
                    self.assertIsNotNone(paused["active_intention"])
                self.assertEqual(agent.run(), expected)

    def test_step_limit_preserves_cursor_and_zero_budget_does_not_advance_it(self):
        agent = demo()
        result = agent.run(max_steps=3)
        self.assertEqual(result["active_intention"]["next_step"], 3)
        before = copy.deepcopy(agent.__dict__)
        self.assertEqual(agent.run(max_steps=0), result)
        self.assertEqual(agent.intention, before["intention"])
        self.assertEqual(agent.events, before["events"])
        self.assertEqual(agent.world.__dict__, before["world"].__dict__)
        self.assertIn("next plan step 3 of 4", format_trace(result))

    def test_continuation_preview_is_pure_and_matches_execution(self):
        agent = demo()
        agent.run(max_steps=2)
        before = copy.deepcopy((agent.knowledge.facts, agent.intention, agent.intention_events,
                                agent.events, agent.decisions, agent.attempts, agent.world.__dict__))
        preview = agent.deliberate(max_hypotheses=0)
        self.assertEqual(agent.deliberate(max_hypotheses=0), preview)
        self.assertEqual(preview["selected"]["argument"], "move(start, forest)")
        self.assertEqual(preview["selected"]["plan_step"], 2)
        self.assertEqual(preview["hypotheses_checked"], 0)
        self.assertEqual(before, (agent.knowledge.facts, agent.intention, agent.intention_events,
                                 agent.events, agent.decisions, agent.attempts, agent.world.__dict__))
        result = agent.run(max_steps=1, max_hypotheses=0)
        self.assertEqual(result["decisions"][-1], preview)

    def test_failed_requirement_preview_is_pure_and_matches_reselection(self):
        agent = demo()
        agent.run(max_steps=1)
        before = copy.deepcopy((agent.intention, agent.attempts, agent.intention_events))
        preview = agent.deliberate()
        self.assertEqual(preview["released_intention"]["status"], "requirements_failed")
        self.assertEqual(preview["selected"]["argument"], "clear(forest)")
        self.assertEqual((agent.intention, agent.attempts, agent.intention_events), before)
        self.assertIn("Required clear(bridge): false", format_decision(preview))
        self.assertEqual(agent.run(max_steps=1)["decisions"][-1], preview)

    def test_first_step_requires_accepted_evidence_not_an_assumption(self):
        program = program_with("suppose(clear(a)) { prove(clear(a)). } require clear(a). act move(a,b).",
                               plans="plan fallback for done { when ready. observe clear(b). }")
        report = deliberate(program, Knowledge(program.beliefs)).report
        self.assertEqual(report["candidates"][0]["status"], "requirements_failed")
        self.assertEqual(report["selected"]["plan"], "fallback")
        self.assertEqual(report["hypotheses_checked"], 0)

    def test_requirements_recompute_derived_support_after_revision(self):
        program = program_with("observe clear(b). require safe. act move(a,b).",
                               beliefs="belief ready. belief clear(b). rule safe :- clear(b).")
        result = Agent(program, RouteWorld("a", [["a", "b"]], ["b"])).run()
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(result["steps"], 1)
        self.assertEqual(result["action_calls"], 0)
        self.assertEqual(result["decisions"][-1]["released_intention"]["requirements"][0]["status"], "unknown")

    def test_negative_and_unknown_requirements_use_open_world_semantics(self):
        program = program_with("observe clear(b). require not clear(b), unknown(clear(c)). observe clear(a).")
        result = Agent(program, RouteWorld("a", [["a", "b"]], ["b"])).run()
        self.assertEqual(result["steps"], 2)
        evidence = result["events"][1]["because"]
        self.assertEqual(evidence[0]["conclusion"], "not clear(b)")
        self.assertEqual(evidence[1], {"unknown": "clear(c)"})

    def test_entry_guards_are_not_invariants_and_priorities_do_not_preempt(self):
        program = parse("""agent test {
            belief ready. goal done.
            plan sequence for done {
                when ready, unknown(clear(a)).
                observe clear(a).
                require clear(a).
                observe clear(b).
            }
            plan urgent for done priority 100 { when clear(a). observe clear(c). }
        }""")
        result = Agent(program, RouteWorld("a", [["a", "b"], ["a", "c"]], [])).run(max_steps=2)
        self.assertEqual([event["plan"] for event in result["events"]], ["sequence", "sequence"])

    def test_bindings_remain_fixed_between_steps(self):
        program = parse("""agent test {
            belief node(a). belief node(b). goal done.
            plan sequence(X) for done {
                when node(X). observe clear(X). require clear(X). observe clear(X).
            }
        }""")
        agent = Agent(program, RouteWorld("a", [["a", "b"]], []))
        agent.run(max_steps=1)
        agent.knowledge.observe(parse_query("not node(a)"), "test")
        result = agent.run(max_steps=1)
        self.assertEqual([event["bindings"] for event in result["events"]], [{"X": "a"}, {"X": "a"}])

    def test_changed_environment_evidence_cancels_next_step_on_resume(self):
        agent = demo()
        agent.run(max_steps=2)
        agent.knowledge.observe(parse_query("not clear(forest)"), "external_observation")
        result = agent.run()
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(result["action_calls"], 0)
        self.assertIsNone(result["active_intention"])

    def test_action_failure_releases_rest_of_sequence_and_uses_fallback(self):
        program = program_with("act move(a,b). observe clear(c).",
                               beliefs="belief ready. belief at(a). rule done :- clear(a).",
                               plans="plan fallback for done { when not clear(b). observe clear(a). }")
        result = Agent(program, RouteWorld("a", [["a", "b"], ["a", "c"]], ["b"])).run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["action_calls"], 1)
        self.assertFalse(any(event["argument"] == "clear(c)" for event in result["events"]))
        self.assertEqual(result["intention_events"][1]["status"], "operation_failed")
        self.assertEqual(result["events"][1]["plan"], "fallback")

    def test_observation_failure_abandons_sequence_without_evidence(self):
        result = Agent(program_with("observe clear(missing). act move(a,b)."), RouteWorld("a", [["a", "b"]], [])).run()
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(result["steps"], 1)
        self.assertEqual(result["action_calls"], 0)

    def test_completed_prefix_is_not_replayed_at_a_visited_belief_state(self):
        program = program_with("observe clear(a). observe clear(b).")
        agent = Agent(program, RouteWorld("a", [["a", "b"]], []))
        result = agent.run()
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(result["steps"], 2)
        self.assertEqual(agent.run()["steps"], 2)

    def test_requirements_failure_does_not_restart_prefix_under_revised_beliefs(self):
        program = program_with("observe clear(a). require missing. observe clear(b).")
        result = Agent(program, RouteWorld("a", [["a", "b"]], [])).run()
        self.assertEqual(result["steps"], 1)
        self.assertEqual(result["status"], "stuck")

    def test_goal_satisfaction_cancels_remaining_operations(self):
        program = program_with("observe clear(a). act move(a,b).",
                               beliefs="belief ready. rule done :- clear(a).")
        result = Agent(program, RouteWorld("a", [["a", "b"]], [])).run(max_steps=1)
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["action_calls"], 0)
        self.assertEqual(result["intention_events"][-1]["status"], "goal_satisfied")
        self.assertIsNone(result["active_intention"])

    def test_satisfied_intention_releases_while_other_goals_remain(self):
        program = program_with("observe clear(a). act move(a,b).",
                               beliefs="belief ready. rule done :- clear(a). rule other :- clear(b).",
                               goals="goal done. goal other.",
                               plans="plan second for other { when ready. observe clear(b). }")
        result = Agent(program, RouteWorld("a", [["a", "b"]], [])).run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual([event["plan"] for event in result["events"]], ["sequence", "second"])
        self.assertEqual(result["decisions"][1]["released_intention"]["status"], "goal_satisfied")

    def test_conflict_stops_before_next_action_and_retains_cursor(self):
        program = program_with("observe clear(a). act move(a,b).",
                               beliefs="belief ready. belief not safe. rule safe :- clear(a).")
        result = Agent(program, RouteWorld("a", [["a", "b"]], [])).run()
        self.assertEqual(result["status"], "reasoning_error")
        self.assertEqual(result["action_calls"], 0)
        self.assertEqual(result["active_intention"]["next_step"], 2)

    def test_budget_error_during_reselection_executes_no_fallback(self):
        agent = demo()
        agent.run(max_steps=1)
        preview = agent.deliberate(max_hypotheses=0)
        result = agent.run(max_hypotheses=0)
        self.assertEqual(result["status"], "reasoning_error")
        self.assertEqual(result["steps"], 1)
        self.assertIsNone(result["active_intention"])
        self.assertEqual(result["decisions"][-1], preview)

    def test_initial_preview_includes_sequence_without_running_future_requirements(self):
        agent = demo()
        report = agent.deliberate()
        self.assertEqual(len(report["selected"]["sequence"]), 4)
        self.assertEqual(report["selected"]["sequence"][1]["argument"], "move(start, bridge)")
        self.assertEqual(agent.world.observation_calls, 0)
        self.assertEqual(agent.inference().status(parse_query("clear(bridge)")), "unknown")

    def test_cli_trace_includes_intention_lifecycle_and_step_proofs(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "trace.json"
            with redirect_stdout(io.StringIO()):
                status = main(["run", str(EXAMPLE), "--trace-json", str(target)])
            result = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(status, 0)
            self.assertEqual(result["events"][2]["because"][-1]["source"], "simulator:step_2")
            self.assertEqual(len(result["intention_events"]), 4)


if __name__ == "__main__":
    unittest.main()

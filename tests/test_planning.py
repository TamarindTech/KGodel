from contextlib import redirect_stdout
import copy
import io
import json
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
EXAMPLE = ROOT / "examples" / "hypothesis_planning.kg"


def program_with(plans, beliefs="belief ready.", goals="goal done."):
    return parse(f"agent test {{ {beliefs} {goals} {plans} }}")


def decision(program, **limits):
    return deliberate(program, Knowledge(program.beliefs), **limits).report


def demo():
    program = parse(EXAMPLE.read_text(encoding="utf-8"))
    world = RouteWorld.from_json(EXAMPLE.with_suffix(".world.json").read_text(encoding="utf-8"))
    return Agent(program, world)


class PlanSyntaxTests(unittest.TestCase):
    def test_existing_plans_default_to_zero_priority_and_no_hypotheses(self):
        program = program_with("plan inspect for done { when ready. observe clear(a). }")
        self.assertEqual(program.plans[0].priority, 0)
        self.assertEqual(program.plans[0].hypotheses, ())

    def test_priority_and_grounded_hypothesis_templates(self):
        program = program_with("""
            plan inspect(X) for done priority 25 {
                when node(X).
                suppose(clear(X)) { prove(clear(X)). }
                observe clear(X).
            }
        """, "belief node(a).")
        selected = decision(program)["selected"]
        self.assertEqual(selected["priority"], 25)
        self.assertEqual(selected["bindings"], {"X": "a"})
        self.assertEqual(selected["hypotheses"]["results"][0]["assumptions"], ["clear(a)"])

    def test_hypothesis_variables_must_be_bound_outside_the_scope(self):
        for body in ("suppose(clear(X)) { prove(clear(X)). }",
                     "suppose(ready) { prove(clear(X)). }",
                     "suppose(ready) { suppose(clear(X)) { prove(clear(X)). } }"):
            with self.subTest(body=body), self.assertRaisesRegex(KGodelError, "unbound variables"):
                program_with(f"plan inspect(X) for done {{ when ready. {body} observe clear(a). }}")

    def test_target_variables_can_ground_hypotheses(self):
        program = program_with("""
            plan inspect(X) for checked(X) {
                when ready.
                suppose(clear(X)) { prove(clear(X)). }
                observe clear(X).
            }
        """, goals="goal checked(a).")
        self.assertEqual(decision(program)["selected"]["argument"], "clear(a)")

    def test_invalid_priority_rejected(self):
        for value in ("high", "-1", "1.5", "1000001", "9999999999999999999999999999"):
            with self.subTest(value=value), self.assertRaises(KGodelError):
                program_with(f"plan inspect for done priority {value} {{ when ready. observe clear(a). }}")

    def test_numeric_constants_are_still_unsupported(self):
        with self.assertRaises(KGodelError):
            program_with("", beliefs="belief cost(10).")

    def test_hypothesis_cannot_contain_an_operation(self):
        with self.assertRaises(KGodelError):
            program_with("""
                plan inspect for done {
                    when ready.
                    suppose(clear(a)) { act move(a, b). }
                    observe clear(a).
                }
            """)


class PlanSelectionTests(unittest.TestCase):
    def test_priority_beats_declaration_order(self):
        program = program_with("""
            plan low for done priority 1 { when ready. observe clear(a). }
            plan high for done priority 20 { when ready. observe clear(b). }
        """)
        self.assertEqual(decision(program)["selected"]["plan"], "high")

    def test_equal_priority_preserves_declaration_order(self):
        program = program_with("""
            plan first for done priority 20 { when ready. observe clear(a). }
            plan second for done priority 20 { when ready. observe clear(b). }
        """)
        self.assertEqual(decision(program)["selected"]["plan"], "first")

    def test_priority_applies_within_goal_order(self):
        program = program_with("""
            plan later for second priority 100 { when ready. observe clear(b). }
            plan earlier for first priority 1 { when ready. observe clear(a). }
        """, goals="goal first. goal second.")
        self.assertEqual(decision(program)["selected"]["plan"], "earlier")

    def test_unknown_and_false_hypotheses_skip_to_fallback(self):
        for statement in ("clear(b)", "not ready"):
            with self.subTest(statement=statement):
                program = program_with(f"""
                    plan speculative for done priority 20 {{
                        when ready.
                        suppose(clear(a)) {{ prove({statement}). }}
                        observe clear(a).
                    }}
                    plan fallback for done {{ when ready. observe clear(b). }}
                """)
                result = decision(program)
                self.assertEqual(result["candidates"][0]["status"], "unsupported")
                self.assertEqual(result["selected"]["plan"], "fallback")

    def test_inconsistent_hypothesis_skips_to_fallback(self):
        program = program_with("""
            plan speculative for done priority 20 {
                when ready.
                suppose(not ready) { prove(not ready). }
                observe clear(a).
            }
            plan fallback for done { when ready. observe clear(b). }
        """)
        result = decision(program)
        self.assertEqual(result["candidates"][0]["status"], "inconsistent")
        self.assertEqual(result["selected"]["plan"], "fallback")

    def test_ordinary_guards_cannot_borrow_hypothetical_evidence(self):
        program = program_with("""
            plan speculative for done {
                when clear(a).
                suppose(clear(a)) { prove(clear(a)). }
                act move(a, b).
            }
        """)
        result = decision(program)
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(result["candidates"], [])

    def test_multiple_blocks_are_independent_and_all_must_pass(self):
        program = program_with("""
            plan speculative for done {
                when ready.
                suppose(clear(a)) { prove(clear(a)). }
                suppose(clear(b)) { prove(clear(a)). }
                observe clear(a).
            }
        """)
        result = decision(program)
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(result["candidates"][0]["status"], "unsupported")

    def test_nested_hypotheses_can_use_outer_assumptions(self):
        program = program_with("""
            plan speculative for done {
                when ready.
                suppose(clear(a)) {
                    suppose(clear(b)) { prove(clear(a)). prove(clear(b)). }
                    prove(clear(a)).
                }
                observe clear(a).
            }
        """)
        result = decision(program)
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["hypotheses_checked"], 2)

    def test_all_proofs_in_a_block_must_be_true(self):
        program = program_with("""
            plan speculative for done {
                when ready.
                suppose(clear(a)) { prove(clear(a)). prove(clear(b)). }
                observe clear(a).
            }
        """)
        self.assertEqual(decision(program)["status"], "stuck")

    def test_hypothesis_budget_is_shared_across_candidates(self):
        agent = demo()
        result = agent.run(max_hypotheses=1)
        self.assertEqual(result["status"], "reasoning_error")
        self.assertEqual(result["steps"], 0)
        self.assertEqual(result["action_calls"], 0)
        self.assertEqual(result["observation_calls"], 0)
        candidates = result["decisions"][0]["candidates"]
        self.assertEqual(candidates[0]["status"], "unsupported")
        self.assertEqual(candidates[1]["status"], "error")
        self.assertIn("context limit", candidates[1]["hypotheses"]["results"][0]["error"])

    def test_zero_hypothesis_budget_allows_ordinary_plans(self):
        program = program_with("plan inspect for done { when ready. observe clear(a). }")
        self.assertEqual(decision(program, max_hypotheses=0)["status"], "selected")

    def test_budget_error_is_not_treated_as_a_failed_plan(self):
        program = program_with("""
            plan speculative for done priority 10 {
                when ready.
                suppose(clear(a)) { prove(clear(a)). }
                observe clear(a).
            }
            plan fallback for done { when ready. observe clear(b). }
        """)
        result = decision(program, max_hypotheses=0)
        self.assertEqual(result["status"], "reasoning_error")
        self.assertIsNone(result["selected"])
        self.assertEqual(len(result["candidates"]), 1)


class PlanningIntegrationTests(unittest.TestCase):
    def test_demo_observes_useful_routes_and_never_moves_into_blocked_bridge(self):
        agent = demo()
        result = agent.run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["steps"], 5)
        self.assertEqual(result["action_calls"], 2)
        self.assertEqual(result["observation_calls"], 3)
        self.assertEqual([event["argument"] for event in result["events"]],
                         ["clear(bridge)", "clear(forest)", "move(start, forest)",
                          "clear(goal)", "move(forest, goal)"])
        self.assertEqual(result["decisions"][0]["candidates"][0]["bindings"]["Y"], "alley")
        self.assertEqual(result["decisions"][0]["candidates"][0]["status"], "unsupported")
        self.assertEqual(result["goal_proofs"]["at(goal)"]["source"], "simulator:step_5")
        self.assertNotIn("clear(alley)", result["beliefs"])
        self.assertIn("not clear(bridge)", result["beliefs"])

    def test_hypothesis_does_not_become_an_observation(self):
        agent = demo()
        agent.run(max_steps=1)
        self.assertEqual(agent.inference().status(parse_query("clear(bridge)")), "false")
        self.assertEqual(agent.inference().status(parse_query("clear(alley)")), "unknown")
        self.assertTrue(all(not proof.source.startswith("assumption:")
                            for proof in agent.knowledge.facts.values()))

    def test_preview_is_pure_repeatable_and_matches_executed_selection(self):
        agent = demo()
        before = copy.deepcopy((agent.knowledge.facts, agent.events, agent.attempts, agent.decisions,
                                agent.world.__dict__))
        first = agent.deliberate()
        self.assertEqual(first, agent.deliberate())
        after = (agent.knowledge.facts, agent.events, agent.attempts, agent.decisions, agent.world.__dict__)
        self.assertEqual(before, after)
        result = agent.run(max_steps=1)
        self.assertEqual(result["decisions"][0], first)
        self.assertEqual(result["events"][0]["argument"], first["selected"]["argument"])

    def test_preview_uses_current_revised_knowledge(self):
        agent = demo()
        agent.run(max_steps=1)
        self.assertEqual(agent.deliberate()["selected"]["argument"], "clear(forest)")

    def test_hypothetical_goal_does_not_finish_the_agent(self):
        program = program_with("""
            plan speculative for done {
                when ready.
                suppose(done) { prove(done). }
                observe clear(a).
            }
        """)
        result = Agent(program, RouteWorld("a", [], [])).run(max_steps=1)
        self.assertEqual(result["status"], "step_limit")
        self.assertEqual(result["goals"]["done"], "unknown")

    def test_resume_keeps_decision_references_consistent(self):
        agent = demo()
        agent.run(max_steps=2)
        result = agent.run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual([event["decision"] for event in result["events"]], [1, 2, 3, 4, 5])

    def test_stuck_deliberation_retains_rejection_diagnostics(self):
        program = program_with("""
            plan speculative for done {
                when ready.
                suppose(not ready) { prove(not ready). }
                observe clear(a).
            }
        """)
        result = Agent(program, RouteWorld("a", [], [])).run()
        self.assertEqual(result["status"], "stuck")
        self.assertEqual(result["steps"], 0)
        self.assertIn("inconsistent", format_trace(result))

    def test_cli_deliberates_without_a_world_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "agent.kg"
            path.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
            target = Path(temporary) / "decision.json"
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(["deliberate", str(path), "--result-json", str(target)])
            self.assertEqual(status, 0)
            report = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(report["selected"]["argument"], "clear(bridge)")
            self.assertIn("unsupported", output.getvalue())

    def test_cli_preview_budget_error_returns_two(self):
        with redirect_stdout(io.StringIO()):
            status = main(["deliberate", str(EXAMPLE), "--max-hypotheses", "0"])
        self.assertEqual(status, 2)

    def test_preview_after_completion_is_achieved(self):
        agent = demo()
        agent.run()
        report = agent.deliberate()
        self.assertEqual(report["status"], "achieved")
        self.assertIsNone(report["selected"])
        self.assertIn("achieved", format_decision(report))


if __name__ == "__main__":
    unittest.main()

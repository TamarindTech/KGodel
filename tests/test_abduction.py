from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kgodel.__main__ import main
from kgodel.abduction import find_explanations, format_abduction
from kgodel.demos import load_demo
from kgodel.logic import Inference, Knowledge
from kgodel.model import KGodelError
from kgodel.parser import parse, parse_abduction, parse_query
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import dumps_session, loads_session, save_session
from kgodel.shell import ShellSession


ROOT = Path(__file__).resolve().parents[1]


def make_agent(contents):
    return Agent(parse("agent test { " + contents + " goal done. }"), RouteWorld("start", [], []))


def solutions(report):
    return [item["assumptions"] for item in report["solutions"]]


class AbductionTests(unittest.TestCase):
    def test_finds_subset_minimal_explanations_of_different_sizes(self):
        agent = make_agent("rule ready :- a. rule ready :- b, c.")
        report = agent.abduce("ready", ["c", "a", "b"])
        self.assertEqual(report["status"], "complete")
        self.assertEqual(solutions(report), [["a"], ["b", "c"]])
        self.assertTrue(report["search"]["exhaustive"])
        self.assertGreater(report["search"]["pruned"], 0)
        # Independently check each returned set and every proper subset.
        from itertools import combinations
        for solution in report["solutions"]:
            literals = tuple(parse_query(item) for item in solution["assumptions"])
            logic = Inference(agent.knowledge.assuming(literals, "check"), agent.program.effective_rules)
            self.assertEqual(logic.status(parse_query("ready")), "true")
            for size in range(len(literals)):
                for subset in combinations(literals, size):
                    knowledge = agent.knowledge.assuming(subset, "check") if subset else agent.knowledge.copy()
                    self.assertNotEqual(Inference(knowledge, agent.program.effective_rules).status(parse_query("ready")), "true")

    def test_initial_proof_returns_the_empty_explanation_without_searching(self):
        agent = make_agent("belief accepted. rule ready :- accepted.")
        report = agent.abduce("ready", ["unused"], max_contexts=0)
        self.assertEqual(solutions(report), [[]])
        self.assertEqual(report["base_status"], "true")
        self.assertEqual(report["search"]["evaluated"], 0)
        self.assertTrue(report["search"]["exhaustive"])
        self.assertEqual(report["solutions"][0]["assumptions_used"], [])

    def test_existing_derived_support_is_not_a_new_assumption(self):
        agent = make_agent("belief accepted. rule a :- accepted. rule ready :- a, b.")
        report = agent.abduce("ready", ["a", "accepted", "b"])
        self.assertEqual(solutions(report), [["b"]])
        self.assertEqual({item["literal"] for item in report["excluded"]}, {"a", "accepted"})
        self.assertTrue(all(item["reason"] == "already_supported" for item in report["excluded"]))

    def test_candidates_opposed_by_base_or_derived_evidence_are_excluded(self):
        agent = make_agent("belief blocked. belief not b. rule not a :- blocked. rule ready :- c.")
        report = agent.abduce("ready", ["a", "b", "c"])
        self.assertEqual(solutions(report), [["c"]])
        self.assertEqual([item["reason"] for item in report["excluded"]], ["contradicted", "contradicted"])
        self.assertEqual(report["excluded"][0]["proof"]["conclusion"], "not a")

    def test_opposed_query_cannot_be_repaired_with_additive_assumptions(self):
        agent = make_agent("belief blocked. rule not ready :- blocked. rule ready :- a.")
        report = agent.abduce("ready", ["a", "ready"])
        self.assertEqual(report["base_status"], "false")
        self.assertEqual(solutions(report), [])
        self.assertEqual(report["search"]["evaluated"], 0)
        self.assertIn("cannot replace", report["reason"])
        self.assertIn("Opposing evidence", format_abduction(report, explain=True))

    def test_negative_queries_and_negative_candidates_use_explicit_support(self):
        agent = make_agent("rule not ready :- not clear(bridge).")
        report = agent.abduce("not ready", ["not clear(bridge)", "clear(bridge)"])
        self.assertEqual(solutions(report), [["not clear(bridge)"]])
        self.assertEqual(report["solutions"][0]["proof"]["conclusion"], "not ready")

    def test_unrelated_conflict_rejects_a_hypothesis_even_when_goal_is_supported(self):
        agent = make_agent("belief not invalid. rule invalid :- a. rule ready :- a. rule ready :- b.")
        report = agent.abduce("ready", ["a", "b", "c"])
        self.assertEqual(solutions(report), [["b"]])
        self.assertEqual(report["conflicts"][0]["assumptions"], ["a"])
        self.assertIn("Knowledge conflict", report["conflicts"][0]["error"])
        self.assertGreater(report["search"]["pruned"], 0)

    def test_joint_conflicts_and_opposite_candidates_are_not_explanations(self):
        agent = make_agent("belief not invalid. rule invalid :- a, b. rule ready :- a, b.")
        report = agent.abduce("ready", ["a", "b", "not a"])
        self.assertEqual(solutions(report), [])
        self.assertEqual(report["status"], "complete")
        self.assertEqual({tuple(item["assumptions"]) for item in report["conflicts"]},
                         {("a", "b"), ("a", "not a")})

    def test_recursive_rules_derive_conditional_support(self):
        agent = make_agent("""
            belief edge(a, b). belief edge(b, c). belief edge(c, a).
            rule reachable(X) :- seed(X).
            rule reachable(Y) :- reachable(X), edge(X, Y).
        """)
        report = agent.abduce("reachable(c)", ["seed(a)", "seed(b)"])
        self.assertEqual(solutions(report), [["seed(a)"], ["seed(b)"]])
        for solution in report["solutions"]:
            self.assertEqual([item["literal"] for item in solution["assumptions_used"]], solution["assumptions"])

    def test_candidate_order_and_duplicates_do_not_change_results(self):
        agent = make_agent("rule ready :- a, b.")
        self.assertEqual(agent.abduce("ready", ["a", "b"]), agent.abduce("ready.", ["b.", "a", "a"]))
        report = agent.abduce("ready", ["a"] * 20)
        self.assertEqual(report["candidates"], ["a"])
        self.assertEqual(json.loads(json.dumps(report)), report)

    def test_no_candidates_and_no_explanation_do_not_establish_falsity(self):
        agent = make_agent("rule ready :- a.")
        report = agent.abduce("ready", [])
        self.assertEqual(report["base_status"], "unknown")
        self.assertEqual(report["status"], "complete")
        self.assertTrue(report["search"]["exhaustive"])
        self.assertIn("does not establish impossibility", format_abduction(report))

    def test_query_itself_can_only_be_assumed_when_explicitly_supplied(self):
        agent = make_agent("")
        self.assertEqual(solutions(agent.abduce("ready", ["irrelevant"])), [])
        self.assertEqual(solutions(agent.abduce("ready", ["ready"])), [["ready"]])

    def test_size_bound_reports_limited_coverage(self):
        agent = make_agent("rule ready :- a, b.")
        for bound in (0, 1):
            with self.subTest(bound=bound):
                report = agent.abduce("ready", ["a", "b"], max_assumptions=bound)
                self.assertEqual(report["status"], "complete")
                self.assertEqual(solutions(report), [])
                self.assertFalse(report["search"]["exhaustive"])
                self.assertEqual(report["search"]["complete_through_size"], bound)
                self.assertIn("outside the requested size bound", format_abduction(report))
        self.assertEqual(solutions(agent.abduce("ready", ["a", "b"], max_assumptions=2)), [["a", "b"]])

    def test_context_limit_preserves_valid_solutions_and_reports_partial_search(self):
        agent = make_agent("rule ready :- a. rule ready :- b.")
        report = agent.abduce("ready", ["a", "b"], max_contexts=1)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["stop_reason"], "context_limit")
        self.assertEqual(solutions(report), [["a"]])
        self.assertTrue(report["solutions"][0]["minimal"])
        self.assertFalse(report["search"]["exhaustive"])
        zero = agent.abduce("ready", ["a"], max_contexts=0)
        self.assertEqual(zero["status"], "partial")
        self.assertEqual(zero["search"]["evaluated"], 0)

    def test_solution_limit_is_partial_unless_all_remaining_sets_are_pruned(self):
        agent = make_agent("rule ready :- a. rule ready :- b.")
        report = agent.abduce("ready", ["a", "b"], max_solutions=1)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["stop_reason"], "solution_limit")
        self.assertEqual(solutions(report), [["a"]])
        self.assertEqual(agent.abduce("ready", ["a"], max_solutions=1)["status"], "complete")

    def test_hypothesis_inference_failure_stops_before_unproven_minimality(self):
        agent = make_agent("rule ready :- a. rule extra_one :- b. rule extra_two :- b. rule ready :- c.")
        report = agent.abduce("ready", ["a", "b", "c"], max_facts=2)
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["stop_reason"], "hypothesis_inference_error")
        self.assertEqual(report["unresolved_assumptions"], ["b"])
        self.assertEqual(report["search"]["evaluated"], 2)
        self.assertEqual(solutions(report), [["a"]])
        self.assertIn("fact limit", report["reason"])

    def test_base_conflict_and_base_inference_failure_are_not_negative_answers(self):
        agent = make_agent("belief yes. belief not ready. rule ready :- yes.")
        report = agent.abduce("ready", ["a"])
        self.assertEqual(report["status"], "inconsistent")
        self.assertEqual(report["base_status"], "unresolved")
        report = make_agent("belief yes. rule ready :- yes.").abduce("ready", [], max_work=0)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["stop_reason"], "base_inference_error")

    def test_invalid_limits_candidates_and_queries_are_rejected_before_search(self):
        agent = make_agent("")
        for option in ("max_assumptions", "max_contexts", "max_solutions", "max_facts", "max_work"):
            for value in (-1, True, 1.5):
                with self.subTest(option=option, value=value), self.assertRaises(KGodelError):
                    agent.abduce("ready", [], **{option: value})
        with self.assertRaises(KGodelError):
            agent.abduce("ready", [], max_solutions=0)
        for query, candidates in (("ready(X)", []), ("ready", ["candidate(X)"]),
                                  ("[missing ready]", []), ("ready", ["[missing ready]"]),
                                  ("ready", "candidate"), (None, []), ("ready", [None])):
            with self.subTest(query=query, candidates=candidates), self.assertRaises(KGodelError):
                agent.abduce(query, candidates)
        with self.assertRaisesRegex(KGodelError, "at most 16"):
            agent.abduce("ready", [f"p{i}" for i in range(17)])
        with self.assertRaises(KGodelError):
            find_explanations(agent.program, agent.knowledge, parse_query("ready"), "candidate")


class AbductionIntegrationTests(unittest.TestCase):
    def test_super_messages_preserve_nested_conditional_proofs(self):
        agent = load_demo("super-routes")
        report = agent.abduce("[cautious mayMoveFrom: start to: bridge]",
                              ["clear(forest)", "open(bridge)", "clear(bridge)"])
        self.assertEqual(solutions(report), [["clear(bridge)", "open(bridge)"]])
        solution = report["solutions"][0]
        self.assertIn("^ApprovedPolicy", json.dumps(solution["proof"]))
        self.assertIn("^RoutePolicy", json.dumps(solution["proof"]))
        self.assertEqual({item["literal"] for item in solution["assumptions_used"]},
                         {"clear(bridge)", "open(bridge)"})

    def test_public_message_candidates_follow_existing_message_rules(self):
        agent = make_agent("class Policy { method ready { a. } } object policy : Policy {} rule proceed :- [policy ready].")
        report = agent.abduce("proceed", ["[policy ready]"])
        self.assertEqual(solutions(report), [["[policy ready]"]])
        with self.assertRaisesRegex(KGodelError, "reserved"):
            agent.abduce("proceed", ["[policy ^Policy ready]"])

    def test_live_search_preserves_active_intention_trace_and_world(self):
        agent = load_demo("super-routes")
        agent.run(1)
        before = dumps_session(agent)
        session = ShellSession(agent)
        last = session.last_result
        with patch.object(RouteWorld, "act", side_effect=AssertionError("act")), \
                patch.object(RouteWorld, "observe", side_effect=AssertionError("observe")), \
                patch.object(Agent, "run", side_effect=AssertionError("run")):
            report = agent.abduce("[cautious mayMoveFrom: start to: forest]", ["clear(forest)"])
            self.assertEqual(solutions(report), [[]])
            output = session.execute(":abduce [cautious mayMoveFrom: start to: bridge] from (clear(bridge), open(bridge))")
            self.assertIn("assume clear(bridge), open(bridge)", output)
        self.assertEqual(dumps_session(agent), before)
        self.assertIs(session.last_result, last)
        self.assertEqual(agent.run(), loads_session(before).run())

    def test_new_observations_change_abduction_without_keeping_previous_assumptions(self):
        agent = load_demo("multistep-route")
        first = agent.abduce("clear(bridge)", ["clear(bridge)"])
        self.assertEqual(solutions(first), [["clear(bridge)"]])
        agent.run(1)
        second = agent.abduce("clear(bridge)", ["clear(bridge)"])
        self.assertEqual(second["base_status"], "false")
        self.assertEqual(solutions(second), [])
        self.assertIn("simulator:", json.dumps(second["base_proof"]))

    def test_request_parser_handles_messages_negation_quotes_and_empty_candidates(self):
        source = 'not [policy usable: "a, from (b)"] from (not clear("a, from (b)"), other).'
        goal, candidates = parse_abduction(source)
        self.assertTrue(goal.negative)
        self.assertEqual(goal.atom.args, ("a, from (b)",))
        self.assertEqual(len(candidates), 2)
        self.assertTrue(candidates[0].negative)
        self.assertEqual(parse_abduction("ready from ()")[1], ())
        for invalid in ("ready", "ready from a", "ready from (a,)", "ready from (). extra."):
            with self.subTest(invalid=invalid), self.assertRaises(KGodelError):
                parse_abduction(invalid)

    def test_shell_uses_its_context_limit_and_recovers_after_invalid_requests(self):
        session = ShellSession(make_agent("rule ready :- a."), max_hypotheses=0)
        self.assertIn("Abduction: partial", session.execute(":abduce ready from (a)"))
        for invalid in (":abduce", ":abduce ready", ":abduce ready from (a(X))"):
            with self.subTest(invalid=invalid), self.assertRaises(KGodelError):
                session.execute(invalid)
        self.assertIn("unknown", session.execute("ready"))
        self.assertIn(":abduce", session.execute(":help"))

    def test_cli_demo_and_request_file_export_the_same_report(self):
        query = "[cautious mayMoveFrom: start to: bridge]"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "report.json"
            with redirect_stdout(io.StringIO()) as rendered:
                self.assertEqual(main(["abduce", "--program", str(ROOT / "examples/super_routes.kg"),
                                       "--file", str(ROOT / "examples/route_abduction.kga"),
                                       "--result-json", str(output), "--explain"]), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report, load_demo("super-routes").abduce(query, ["open(bridge)", "clear(bridge)", "clear(forest)"]))
            self.assertIn("^RoutePolicy", rendered.getvalue())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["abduce", "--demo", "super-routes", query,
                                       "--assume", "open(bridge)", "--assume", "clear(bridge)"]), 0)

    def test_cli_resume_inspects_current_knowledge_without_writing_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            agent = load_demo("multistep-route")
            agent.run(1)
            save_session(agent, path)
            before = path.read_bytes()
            with patch.object(Agent, "run", side_effect=AssertionError("run")), redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["abduce", "--resume", str(path), "clear(bridge)", "--assume", "clear(bridge)"]), 1)
            self.assertIn("currently false", output.getvalue())
            self.assertEqual(path.read_bytes(), before)

    def test_cli_exit_codes_distinguish_incomplete_search_from_invalid_input(self):
        base = ["abduce", "--demo", "super-routes", "[cautious mayMoveFrom: start to: bridge]",
                "--assume", "clear(bridge)", "--assume", "open(bridge)"]
        for options, expected in [(["--max-contexts", "0"], 1), (["--max-assumptions", "1"], 1),
                                  (["--max-work", "0"], 2), (["--max-contexts", "-1"], 2)]:
            with self.subTest(options=options), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(base + options), expected)

    def test_cli_output_cannot_replace_any_input_even_through_a_hard_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            program, request, session = root / "agent.kg", root / "query.kga", root / "session.json"
            program.write_text("agent test { belief ready. goal done. }")
            request.write_text("ready from ()")
            save_session(load_demo(), session)
            cases = [(["--program", str(program), "--file", str(request)], program),
                     (["--program", str(program), "--file", str(request)], request),
                     (["--resume", str(session), "ready"], session)]
            for inputs, source in cases:
                before = source.read_bytes()
                with redirect_stderr(io.StringIO()) as output:
                    self.assertEqual(main(["abduce", *inputs, "--result-json", str(source)]), 2)
                self.assertIn("must not overwrite", output.getvalue())
                self.assertEqual(source.read_bytes(), before)
            alias = root / "alias.json"
            os.link(session, alias)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["abduce", "--resume", str(session), "ready", "--result-json", str(alias)]), 2)

    def test_cli_requires_an_unambiguous_source_and_request(self):
        for args in (["abduce", "ready"], ["abduce", "--demo", "super-routes"],
                     ["abduce", "--demo", "super-routes", "--file", "missing.kga", "--assume", "a"]):
            with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

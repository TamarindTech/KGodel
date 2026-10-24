from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from kgodel.__main__ import main
from kgodel.logic import Knowledge
from kgodel.model import KGodelError, KnowledgeConflict, ProveQuery, SupposeQuery
from kgodel.parser import parse, parse_queries, parse_query
from kgodel.querying import evaluate_queries, format_query_results
from kgodel.runtime import Agent, RouteWorld


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "blocked_route.kg"


class HypothesisTests(unittest.TestCase):
    def setUp(self):
        self.program = parse("""agent test {
            belief path(a, b).
            rule usable(X) :- clear(X).
            rule can_move(X, Y) :- path(X, Y), usable(Y).
        }""")
        self.knowledge = Knowledge(self.program.beliefs)

    def evaluate(self, source, **limits):
        return evaluate_queries(self.knowledge, self.program.rules, parse_queries(source), **limits)

    def test_unknown_true_unknown_and_parent_provenance_unchanged(self):
        before = dict(self.knowledge.facts)
        result = self.evaluate("""
            prove(can_move(a, b)).
            suppose(clear(b)) { prove(can_move(a, b)). }
            prove(can_move(a, b)).
        """)
        first, branch, last = result["results"]
        self.assertEqual(result["status"], "ok")
        self.assertEqual([first["status"], branch["results"][0]["status"], last["status"]],
                         ["unknown", "true", "unknown"])
        self.assertEqual(self.knowledge.facts, before)
        self.assertEqual(branch["results"][0]["assumptions_used"],
                         [{"scope": "hypothesis_1", "literal": "clear(b)"}])

    def test_nested_assumptions_discharge_at_their_own_boundary(self):
        result = self.evaluate("""
            suppose(clear(b)) {
                suppose(clear(c)) { prove(clear(b)). prove(clear(c)). }
                prove(clear(c)).
                prove(clear(b)).
            }
            prove(clear(b)).
        """)
        outer, after = result["results"]
        inner, after_inner, still_outer = outer["results"]
        self.assertEqual([q["status"] for q in inner["results"]], ["true", "true"])
        self.assertEqual(inner["results"][0]["assumptions_used"][0]["scope"], "hypothesis_1")
        self.assertEqual(inner["results"][1]["assumptions_used"][0]["scope"], "hypothesis_2")
        self.assertEqual([after_inner["status"], still_outer["status"], after["status"]],
                         ["unknown", "true", "unknown"])

    def test_sibling_scopes_do_not_share_assumptions(self):
        result = self.evaluate("""
            suppose(clear(b)) { prove(clear(b)). }
            suppose(clear(c)) { prove(clear(b)). }
        """)
        self.assertEqual(result["results"][1]["results"][0]["status"], "unknown")

    def test_negative_assumption_has_false_and_true_answers(self):
        result = self.evaluate("suppose(not clear(b)) { prove(clear(b)). prove(not clear(b)). }")
        answers = result["results"][0]["results"]
        self.assertEqual([answer["status"] for answer in answers], ["false", "true"])
        self.assertEqual(answers[0]["proof"]["conclusion"], "not clear(b)")
        self.assertEqual(answers[0]["assumptions_used"][0]["literal"], "not clear(b)")

    def test_variable_answers_are_scoped_and_explained(self):
        result = self.evaluate("suppose(clear(b), clear(c)) { prove(usable(X)). }")
        answer = result["results"][0]["results"][0]
        self.assertEqual(answer["status"], "answers")
        self.assertEqual([row["bindings"] for row in answer["answers"]], [{"X": "b"}, {"X": "c"}])
        self.assertEqual(answer["answers"][1]["assumptions_used"][0]["literal"], "clear(c)")

    def test_direct_conflict_returns_no_answers_and_leaves_parent_usable(self):
        before = dict(self.knowledge.facts)
        result = self.evaluate("""
            suppose(not path(a, b)) { prove(can_move(a, b)). }
            prove(path(a, b)).
        """)
        branch, after = result["results"]
        self.assertEqual(result["status"], "inconsistent")
        self.assertEqual(branch["status"], "inconsistent")
        self.assertEqual(branch["results"], [])
        self.assertEqual(after["status"], "true")
        self.assertEqual(self.knowledge.facts, before)

    def test_derived_conflict_is_detected(self):
        result = self.evaluate("suppose(clear(b), not usable(b)) { prove(clear(b)). }")
        self.assertEqual(result["status"], "inconsistent")
        self.assertIn("Knowledge conflict", result["results"][0]["error"])
        self.assertEqual(self.knowledge.fingerprint(), ("path(a, b)",))

    def test_nested_conflict_does_not_poison_outer_scope(self):
        result = self.evaluate("""
            suppose(clear(b)) {
                suppose(not clear(b)) { prove(clear(b)). }
                prove(clear(b)).
            }
        """)
        outer = result["results"][0]
        self.assertEqual(result["status"], "inconsistent")
        self.assertEqual(outer["status"], "evaluated")
        self.assertEqual(outer["results"][0]["status"], "inconsistent")
        self.assertEqual(outer["results"][1]["status"], "true")

    def test_conflicting_assumptions_in_one_scope_do_not_use_last_write_wins(self):
        for assumptions in ("clear(b), not clear(b)", "not clear(b), clear(b)"):
            with self.subTest(assumptions=assumptions):
                result = self.evaluate(f"suppose({assumptions}) {{ prove(clear(b)). }}")
                self.assertEqual(result["status"], "inconsistent")
                self.assertEqual(self.knowledge.fingerprint(), ("path(a, b)",))

    def test_redundant_assumption_preserves_existing_support(self):
        result = self.evaluate("suppose(path(a, b)) { prove(path(a, b)). }")
        answer = result["results"][0]["results"][0]
        self.assertEqual(answer["proof"]["source"], "program")
        self.assertEqual(answer["assumptions_used"], [])

    def test_proof_reports_only_assumptions_it_uses(self):
        result = self.evaluate("suppose(clear(b), unrelated(c)) { prove(can_move(a, b)). }")
        answer = result["results"][0]["results"][0]
        self.assertEqual(answer["assumptions_used"], [{"scope": "hypothesis_1", "literal": "clear(b)"}])

    def test_assumptions_expand_only_the_child_domain(self):
        result = self.evaluate("""
            suppose(clear(new_place)) { prove(usable(X)). }
            prove(usable(X)).
        """)
        branch, after = result["results"]
        self.assertEqual(branch["results"][0]["answers"][0]["bindings"], {"X": "new_place"})
        self.assertEqual(after["status"], "no_answers")

    def test_hypothesis_resource_error_is_not_inconsistency_or_false(self):
        knowledge = Knowledge()
        result = evaluate_queries(knowledge, self.program.rules,
                                  parse_queries("suppose(clear(b)) { prove(usable(b)). }"), max_work=0)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["results"][0]["results"], [])
        self.assertIn("work limit", result["results"][0]["error"])
        self.assertEqual(knowledge.fingerprint(), ())

    def test_scope_and_depth_limits_leave_parent_unchanged(self):
        source = "suppose(clear(b)) { suppose(clear(c)) { prove(clear(c)). } prove(clear(b)). }"
        for limits in ({"max_depth": 1}, {"max_contexts": 1}):
            with self.subTest(limits=limits):
                report = self.evaluate(source, **limits)
                self.assertEqual(report["status"], "error")
                self.assertEqual(report["results"][0]["results"][1]["status"], "true")
                self.assertEqual(self.knowledge.fingerprint(), ("path(a, b)",))

    def test_knowledge_fork_failure_is_atomic(self):
        with self.assertRaises(KnowledgeConflict):
            self.knowledge.assuming((parse_query("clear(b)"), parse_query("not path(a, b)")), "test")
        self.assertEqual(self.knowledge.fingerprint(), ("path(a, b)",))

    def test_api_rejects_nonground_and_empty_assumptions(self):
        for assumptions in ((), (parse_query("clear(X)"),)):
            with self.subTest(assumptions=assumptions), self.assertRaises(KGodelError):
                self.knowledge.assuming(assumptions, "test")


class QuerySyntaxTests(unittest.TestCase):
    def test_legacy_literal_and_explicit_prove(self):
        self.assertEqual(parse_queries("path(a, X)"), parse_queries("prove(path(a, X))."))

    def test_multiple_statements_with_comments_and_quoted_constants(self):
        queries = parse_queries('''% before\nprove(at("Room A")).
            suppose(clear("Room B")) { prove(clear("Room B")). } // after
        ''')
        self.assertIsInstance(queries[0], ProveQuery)
        self.assertIsInstance(queries[1], SupposeQuery)

    def test_invalid_requests_report_source_locations(self):
        for source in ("", "suppose() { prove(p). }", "suppose(p) { }",
                       "suppose(p(X)) { prove(p(X)). }", "suppose(p) { prove(p) }",
                       "suppose(p) { prove(p).", "prove(p) prove(q)",
                       "suppose(p) { act move(a, b). }", "suppose(p) { observe clear(b). }"):
            with self.subTest(source=source), self.assertRaisesRegex(KGodelError, "Line"):
                parse_queries(source)

    def test_parser_bounds_nesting(self):
        source = "suppose(p) { " * 17 + "prove(p)." + " }" * 17
        with self.assertRaisesRegex(KGodelError, "nesting limit"):
            parse_queries(source)


class HypothesisIntegrationTests(unittest.TestCase):
    def agent(self):
        program = parse(EXAMPLE.read_text(encoding="utf-8"))
        world = RouteWorld.from_json(EXAMPLE.with_suffix(".world.json").read_text(encoding="utf-8"))
        return Agent(program, world)

    def test_live_agent_queries_use_revised_beliefs_without_executing_actions(self):
        agent = self.agent()
        agent.run(max_steps=1)
        before = (dict(agent.knowledge.facts), list(agent.events), set(agent.attempts),
                  agent.world.position, agent.world.action_calls, agent.world.observation_calls)
        result = agent.query("""
            prove(clear(bridge)).
            suppose(clear(forest)) { prove(can_move(start, forest)). }
            prove(clear(forest)).
        """)
        self.assertEqual(result["results"][0]["status"], "false")
        self.assertEqual(result["results"][1]["results"][0]["status"], "true")
        self.assertEqual(result["results"][2]["status"], "unknown")
        after = (dict(agent.knowledge.facts), list(agent.events), set(agent.attempts),
                 agent.world.position, agent.world.action_calls, agent.world.observation_calls)
        self.assertEqual(after, before)

    def test_hypotheses_do_not_change_subsequent_agent_execution(self):
        explored = self.agent()
        explored.query("suppose(clear(forest)) { prove(can_move(start, forest)). }")
        self.assertEqual(explored.run(), self.agent().run())

    def test_query_file_generates_conditional_proofs_and_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "hypotheses.json"
            output = io.StringIO()
            with redirect_stdout(output):
                status = main(["explain", str(EXAMPLE), "--file",
                               str(ROOT / "examples" / "forest_hypothesis.kgq"),
                               "--result-json", str(target)])
            self.assertEqual(status, 0)
            self.assertIn("[assumption:hypothesis_1]", output.getvalue())
            report = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["results"][0]["status"], "unknown")
            self.assertEqual(report["results"][-1]["status"], "unknown")

    def test_inconsistent_query_exits_one_but_preserves_other_answers(self):
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["query", str(EXAMPLE), "--file",
                           str(ROOT / "examples" / "inconsistent_hypothesis.kgq")])
        self.assertEqual(status, 1)
        self.assertIn("inconsistent:", output.getvalue())
        self.assertIn("true: clear(bridge)", output.getvalue())

    def test_query_command_rejects_two_sources(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(["query", str(EXAMPLE), "clear(bridge)", "--file", "anything.kgq"])
        self.assertEqual(error.exception.code, 2)

    def test_brief_rendering_labels_assumption_dependencies(self):
        report = self.agent().query("suppose(clear(forest)) { prove(can_move(start, forest)). }")
        text = format_query_results(report)
        self.assertIn("Depends on clear(forest) [hypothesis_1]", text)
        self.assertIn("temporary assumptions discarded", text)


if __name__ == "__main__":
    unittest.main()

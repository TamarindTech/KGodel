from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from kgodel.__main__ import main
from kgodel.comparison import compare_agents
from kgodel.demos import DEMOS, load_demo
from kgodel.logic import Inference, Knowledge
from kgodel.model import Comparison, ExpressionQuery, KGodelError, Proof, SelfRef, SlotRef, Var
from kgodel.parser import parse, parse_condition, parse_queries, parse_query
from kgodel.querying import evaluate_queries
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import dumps_session, loads_session, program_source
from kgodel.shell import ShellSession


def evaluate(declarations, source, **limits):
    program = parse("agent test {" + declarations + "}")
    return evaluate_queries(Knowledge(program.beliefs), program.effective_rules, parse_queries(source), **limits)


def answer(declarations, source, **limits):
    return evaluate(declarations, source, **limits)["results"][0]


def rows(declarations, source):
    return [row["bindings"] for row in answer(declarations, source)["answers"]]


class ComparisonQueryTests(unittest.TestCase):
    def test_all_operators_have_ground_truth_and_opposing_proofs(self):
        for operator, cases in {
            "==": [("a", "a", True), ("a", "b", False)],
            r"\==": [("a", "a", False), ("a", "b", True)],
            "@<": [("a", "a", False), ("a", "b", True), ("b", "a", False)],
            "@=<": [("a", "a", True), ("a", "b", True), ("b", "a", False)],
            "@>": [("a", "a", False), ("a", "b", False), ("b", "a", True)],
            "@>=": [("a", "a", True), ("a", "b", False), ("b", "a", True)],
        }.items():
            for left, right, supported in cases:
                with self.subTest(operator=operator, left=left, right=right):
                    query = f"{left} {operator} {right}"
                    result = answer("", query)
                    self.assertEqual(result["status"], "true" if supported else "false")
                    proof = result["proof"]
                    conclusion = parse_condition(proof["conclusion"])
                    self.assertTrue(conclusion.holds())
                    self.assertEqual(proof["source"], "builtin:" + conclusion.operator)
                    self.assertEqual(proof["premises"], [])
                    self.assertEqual(result["assumptions_used"], [])

    def test_quoted_constants_keep_equality_and_lexical_order(self):
        for query in ("'alice' == alice", "'it''s' == \"it's\"", "'10' @< '2'", "'Z' @< 'a'", "'é' @> 'z'", "'' @< a"):
            with self.subTest(query=query):
                self.assertEqual(answer("", query)["status"], "true")

    def test_filter_does_not_add_bindings(self):
        self.assertEqual(rows("p(a). p(b).", "p(X), X == a"), [{"X": "a"}])
        self.assertEqual(rows("p(a). p(b).", r"p(X), X \== a"), [{"X": "b"}])

    def test_ordering_returns_distinct_unordered_pairs(self):
        self.assertEqual(rows("p(a). p(b). p(c).", "p(X), p(Y), X @< Y"),
                         [{"X": "a", "Y": "b"}, {"X": "a", "Y": "c"}, {"X": "b", "Y": "c"}])

    def test_filters_work_in_grouped_alternatives(self):
        self.assertEqual(rows("p(a). p(b). p(c).", "p(X), (X == a; X == c)"), [{"X": "a"}, {"X": "c"}])
        self.assertEqual(rows("p(a). p(b).", "p(X), (X == a; X == a)"), [{"X": "a"}])

    def test_unbound_variables_are_errors_not_false_or_assignments(self):
        for query in ("X == a", "X == X", r"X \== a", "X @< a", "X == a, p(X)", "p(X); X == a"):
            with self.subTest(query=query):
                report = evaluate("p(a).", query)
                self.assertEqual(report["status"], "error")
                self.assertIn("Unbound variable", report["results"][0]["error"])
                self.assertNotIn("answers", report["results"][0])

    def test_empty_join_does_not_evaluate_later_filter(self):
        self.assertEqual(answer("", "p(X), X == a")["status"], "no_answers")

    def test_partial_branch_bindings_are_checked_at_point_of_use(self):
        report = evaluate("p(a). q(b).", "(p(X); q(Y)), X == a")
        self.assertEqual(report["status"], "error")
        self.assertNotIn("answers", report["results"][0])

    def test_ground_compounds_keep_unknown_semantics(self):
        for query, status in (("a == a, missing", "unknown"), ("a == b, missing", "false"),
                              ("a == a; missing", "true"), ("a == b; missing", "unknown")):
            with self.subTest(query=query):
                self.assertEqual(answer("", query)["status"], status)

    def test_hypothetical_proof_keeps_only_fact_dependencies(self):
        report = evaluate("", r"suppose(p(a), p(b)) { p(X), X \== b. } p(X), X == a.")
        result = report["results"][0]["results"][0]["answers"][0]
        self.assertEqual(result["bindings"], {"X": "a"})
        self.assertEqual(result["assumptions_used"], [{"scope": "hypothesis_1", "literal": "p(a)"}])
        self.assertEqual(result["proof"]["premises"][1]["source"], r"builtin:\==")
        self.assertEqual(report["results"][1]["status"], "no_answers")

    def test_comparisons_consume_work_budget(self):
        for query in ("a == a", "a == b", "a == a; b == b"):
            with self.subTest(query=query):
                report = evaluate("", query, max_work=0)
                self.assertEqual(report["status"], "error")
                self.assertIn("work limit", report["results"][0]["error"])
        self.assertEqual(answer("", "a == a", max_work=1)["status"], "true")

    def test_query_syntax_roundtrip_and_legacy_single_literal_parser(self):
        for source in ("a==b", "prove(a @=< b)", r"?- p(X), X\==b."):
            request = parse_queries(source)[0]
            self.assertIsInstance(request, ExpressionQuery)
            self.assertEqual(parse_queries(str(request.expression))[0], request)
        with self.assertRaises(KGodelError):
            parse_query("a == b")

    def test_anonymous_and_unsupported_forms_are_rejected(self):
        for source in ("_ == a", r"a \== _", "not a == b", "a = b", r"a \= b", "a @<= b",
                       "a != b", "p(a) == p(b)", "a == b == c", "== a", "a ==", "1 == 1"):
            with self.subTest(source=source), self.assertRaises(KGodelError):
                parse_queries(source)

    def test_condition_limit_counts_comparisons(self):
        self.assertEqual(len(parse_queries(",".join(["a == a"] * 256))), 1)
        with self.assertRaisesRegex(KGodelError, "size exceeds"):
            parse_queries(",".join(["a == a"] * 257))


class ComparisonRuleAndMethodTests(unittest.TestCase):
    def test_rule_filters_exclude_self_matches_with_proof(self):
        source = r"parent(p, a). parent(p, b). sibling(X, Y) :- parent(P, X), parent(P, Y), X \== Y."
        self.assertEqual(rows(source, "sibling(X, Y)"), [{"X": "a", "Y": "b"}, {"X": "b", "Y": "a"}])
        result = answer(source, "sibling(a, b)")
        self.assertEqual(result["proof"]["premises"][-1]["conclusion"], r"a \== b")

    def test_rule_comparisons_follow_binding_literals_regardless_of_position(self):
        source = "p(a). p(b). chosen(X) :- X == b, p(X)."
        self.assertEqual(rows(source, "chosen(X)"), [{"X": "b"}])

    def test_filters_do_not_bind_rule_or_method_variables(self):
        for source in ("chosen(X) :- X == a.", "chosen(X) :- p(X), Y == a.",
                       "class C { method chosen: X { X == a. } }",
                       "class C { method chosen: X { p(X). Y == a. } }"):
            with self.subTest(source=source), self.assertRaisesRegex(KGodelError, "Comparison variables"):
                parse("agent test {" + source + "}")

    def test_constant_only_rules_and_negative_heads(self):
        source = "same :- a == a. not different :- a == a. absent :- a == b."
        self.assertEqual(answer(source, "same")["status"], "true")
        self.assertEqual(answer(source, "different")["status"], "false")
        self.assertEqual(answer(source, "absent")["status"], "unknown")

    def test_recursive_rules_and_belief_revision_recompute_support(self):
        program = parse(r"""agent test {
            edge(a, b). edge(b, c). edge(c, a).
            reaches(X, Y) :- edge(X, Y), X \== Y.
            reaches(X, Y) :- edge(X, Z), reaches(Z, Y), X \== Y.
        }""")
        knowledge = Knowledge(program.beliefs)
        before = Inference(knowledge, program.rules)
        self.assertEqual(before.status(parse_query("reaches(a, c)")), "true")
        self.assertEqual(before.status(parse_query("reaches(a, a)")), "unknown")
        knowledge.observe(parse_query("not edge(b, c)"), "test")
        self.assertEqual(Inference(knowledge, program.rules).status(parse_query("reaches(a, c)")), "unknown")

    def test_method_slots_self_super_and_inheritance(self):
        source = r"""
            class Catalog {
                slot excluded.
                method recommends: Book { available(Book). Book \== @excluded. }
                method named: Name { named(Name). self == Name. }
                method literalNames { 'self' \== self. 'super' == super. }
            }
            class Curated extends Catalog {
                method recommends: Book { [super recommends: Book]. Book @< z. }
            }
            object shelf : Curated { excluded = b. }
            available(a). available(b). available(z). named(shelf).
        """
        self.assertEqual(rows(source, "[shelf recommends: Book]"), [{"Book": "a"}])
        self.assertEqual(answer(source, "[shelf named: shelf]")["status"], "true")
        self.assertEqual(answer(source, "[shelf literalNames]")["status"], "true")
        proof = answer(source, "[shelf recommends: a]")["proof"]
        self.assertIn("^Catalog", json.dumps(proof))
        program = parse("agent test {" + source + "}")
        self.assertEqual(parse(program_source(program)), program)

    def test_comparisons_validate_slots_in_unused_classes(self):
        with self.assertRaisesRegex(KGodelError, "Unknown instance variable"):
            parse("agent test { class C { method ready { @missing == a. } } }")

    def test_comparisons_cannot_be_accepted_or_assumed_facts(self):
        for source in ("a == a.", "belief a == a.", "goal a == a.", "a == a :- ready."):
            with self.subTest(source=source), self.assertRaises(KGodelError):
                parse("agent test {" + source + "}")
        with self.assertRaises(KGodelError):
            parse_queries("suppose(a == a) { p. }")
        comparison = Comparison("a", "==", "a")
        for operation in (lambda: Knowledge((comparison,)), lambda: Knowledge().assuming((comparison,), "s"),
                          lambda: Knowledge().observe(comparison, "test")):
            with self.assertRaises(KGodelError):
                operation()

    def test_direct_api_rejects_unresolved_terms_and_unknown_operators(self):
        for term in (Var("X"), SlotRef("value"), SelfRef()):
            with self.subTest(term=term), self.assertRaises(KGodelError):
                Comparison(term, "==", "a").holds()
        with self.assertRaises(KGodelError):
            Comparison("a", "=", "a")
        with self.assertRaises(KGodelError):
            Comparison(Var("_"), "==", "a")


ROUTE = r"""agent route {
    at(start). path(start, start). path(start, goal). goal at(goal).
    route(X, Y) :- path(X, Y), X \== Y.
    plan travel(From, To) for at(To) {
        when From \== To, at(From), route(From, To), unknown(clear(To)).
        suppose(clear(To)) { clear(To), From \== To. }
        require From \== To.
        observe clear(To).
        require clear(To), From \== To.
        act move(From, To).
    }
}"""


class ComparisonPlanningAndSessionTests(unittest.TestCase):
    def make_agent(self, source=ROUTE):
        return Agent(parse(source), RouteWorld("start", [["start", "goal"]], []))

    def test_all_plan_comparisons_preserve_evidence_across_restart(self):
        agent = self.make_agent()
        before = dumps_session(agent)
        preview = agent.deliberate()
        self.assertEqual(preview["status"], "selected")
        self.assertEqual(dumps_session(agent), before)
        agent.run(1)
        saved = dumps_session(agent)
        self.assertEqual(json.loads(saved)["schema_version"], 5)
        self.assertIn("builtin:", saved)
        restored = loads_session(saved)
        self.assertEqual(restored.intention, agent.intention)
        self.assertEqual(restored.program, agent.program)
        self.assertEqual(restored.run(), agent.run())
        self.assertEqual(len(restored.events), 2)
        self.assertEqual(restored.world.position, "goal")

    def test_false_entry_comparison_prevents_selection(self):
        agent = self.make_agent(ROUTE.replace(r"when From \== To", "when From == To"))
        self.assertEqual(agent.run()["status"], "stuck")
        self.assertEqual(agent.world.observation_calls, 0)

    def test_false_first_requirement_prevents_execution(self):
        agent = self.make_agent(ROUTE.replace(r"require From \== To", "require From == To"))
        self.assertEqual(agent.deliberate()["candidates"][0]["status"], "requirements_failed")
        self.assertEqual(agent.run()["status"], "stuck")
        self.assertEqual(agent.world.observation_calls, 0)

    def test_false_later_requirement_releases_intention(self):
        agent = self.make_agent(ROUTE.replace(r"require clear(To), From \== To", "require clear(To), From == To"))
        self.assertEqual(agent.run()["status"], "stuck")
        self.assertEqual(agent.world.observation_calls, 1)
        self.assertEqual(agent.world.action_calls, 0)
        self.assertEqual(agent.intention_events[-1]["status"], "requirements_failed")

    def test_false_hypothesis_comparison_does_not_grant_clearance(self):
        agent = self.make_agent(ROUTE.replace(r"{ clear(To), From \== To. }", "{ clear(To), From == To. }"))
        self.assertEqual(agent.deliberate()["candidates"][0]["status"], "unsupported")
        self.assertEqual(agent.query("clear(goal)")["results"][0]["status"], "unknown")
        self.assertEqual(agent.world.observation_calls, 0)

    def test_unbound_comparison_plan_variables_are_rejected(self):
        for source in ("plan p(X) for done { when X == a. observe clear(a). }",
                       "plan p(X) for done { when ready. require X == a. observe clear(a). }"):
            with self.subTest(source=source), self.assertRaisesRegex(KGodelError, "unbound variables"):
                parse("agent test {" + source + "}")

    def test_schema_four_examples_remain_readable(self):
        for name in DEMOS:
            with self.subTest(name=name):
                agent = load_demo(name)
                agent.run(1)
                data = json.loads(dumps_session(agent))
                data["schema_version"] = 4
                self.assertEqual(loads_session(json.dumps(data)).run(), agent.run())

    def test_invalid_comparison_proofs_cannot_be_restored(self):
        agent = self.make_agent()
        agent.run(1)
        original = json.loads(dumps_session(agent))
        for change in ({"conclusion": "a == b"}, {"conclusion": "X == a"},
                       {"source": "program"}, {"premises": [{"conclusion": "p", "source": "program", "premises": []}]}):
            data = copy.deepcopy(original)
            pending = [data["intention"]]
            target = None
            while pending:
                item = pending.pop()
                if isinstance(item, dict):
                    if str(item.get("source", "")).startswith("builtin:"):
                        target = item
                        break
                    pending.extend(item.values())
                elif isinstance(item, list):
                    pending.extend(item)
            self.assertIsNotNone(target)
            target.update(change)
            with self.subTest(change=change), self.assertRaises(KGodelError):
                loads_session(json.dumps(data))

    def test_comparison_evidence_cannot_be_forged_as_accepted_belief(self):
        data = json.loads(dumps_session(self.make_agent()))
        data["beliefs"].append(Proof(Comparison("a", "==", "a"), "builtin:==").as_dict())
        with self.assertRaisesRegex(KGodelError, "accepted belief"):
            loads_session(json.dumps(data))

    def test_abduction_derives_filtered_rules_without_assuming_tests(self):
        agent = Agent(parse(r"agent a { chosen(X) :- p(X), X \== b. goal done. }"), RouteWorld("start", [], []))
        report = agent.abduce("chosen(a)", ["p(a)", "p(b)"])
        self.assertEqual(report["solutions"][0]["assumptions"], ["p(a)"])
        self.assertIn("builtin:", json.dumps(report["solutions"][0]["proof"]))
        for target, candidates in (("a == a", []), ("chosen(a)", ["a == a"])):
            with self.subTest(target=target, candidates=candidates), self.assertRaises(KGodelError):
                agent.abduce(target, candidates)

    def test_saved_state_comparison_keeps_computed_premises(self):
        before = self.make_agent()
        after = loads_session(dumps_session(before))
        after.run()
        result = compare_agents(before, after, queries=["route(start, goal)"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("builtin:", json.dumps(result["queries"][0]))

    def test_shell_inspection_keeps_state_pure(self):
        agent = self.make_agent()
        before = dumps_session(agent)
        rendered = ShellSession(agent).execute(r":explain path(start, To), To \== start")
        self.assertIn("To = goal", rendered)
        self.assertIn("builtin:", rendered)
        self.assertEqual(dumps_session(agent), before)

    def test_cli_comparison_and_unbound_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / "route.kg"
            program.write_text(ROUTE, encoding="utf-8")
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                self.assertEqual(main(["explain", str(program), r"path(start, To), To \== start"]), 0)
                self.assertEqual(main(["query", str(program), "To == goal"]), 2)
            self.assertIn("builtin:", output.getvalue())
            self.assertIn("Unbound variable", output.getvalue())


if __name__ == "__main__":
    unittest.main()

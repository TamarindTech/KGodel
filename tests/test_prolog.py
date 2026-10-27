from contextlib import redirect_stderr, redirect_stdout
import io
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from kgodel.__main__ import main
from kgodel.demos import DEMOS, load_demo
from kgodel.logic import Knowledge
from kgodel.model import ExpressionQuery, KGodelError, ProveQuery
from kgodel.parser import parse, parse_queries, parse_query
from kgodel.querying import evaluate_queries, format_query_results
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import dumps_session, loads_session, program_source
from kgodel.shell import ShellSession


ROOT = Path(__file__).resolve().parents[1]


def evaluate(declarations, query, **limits):
    program = parse("agent test { " + declarations + " }")
    return evaluate_queries(Knowledge(program.beliefs), program.effective_rules,
                            parse_queries(query), **limits)


def answer(declarations, query, **limits):
    return evaluate(declarations, query, **limits)["results"][0]


def bindings(declarations, query):
    return [row["bindings"] for row in answer(declarations, query)["answers"]]


class ComposedQueryTests(unittest.TestCase):
    def test_conjunction_joins_shared_variables(self):
        facts = "edge(a, b). edge(a, c). edge(b, d). edge(c, e)."
        self.assertEqual(bindings(facts, "?- edge(a, X), edge(X, Y)."),
                         [{"X": "b", "Y": "d"}, {"X": "c", "Y": "e"}])

    def test_conjunction_rejects_incompatible_bindings(self):
        self.assertEqual(bindings("p(a). q(b).", "p(X), q(X)"), [])

    def test_independent_variables_form_cartesian_product(self):
        self.assertEqual(bindings("p(a). p(b).", "p(X), p(Y)"),
                         [{"X": x, "Y": y} for x in ("a", "b") for y in ("a", "b")])

    def test_conjunction_binds_more_tightly_than_disjunction(self):
        facts = "p(a). q(b). q(c). r(c)."
        self.assertEqual(bindings(facts, "p(X); q(X), r(X)"), [{"X": "a"}, {"X": "c"}])
        self.assertEqual(bindings(facts, "(p(X); q(X)), r(X)"), [{"X": "c"}])

    def test_alternatives_do_not_leak_bindings(self):
        facts = "p(a). q(b). r(a). r(b)."
        self.assertEqual(bindings(facts, "(p(X); q(X)), r(X)"), [{"X": "a"}, {"X": "b"}])

    def test_alternative_with_different_variables_keeps_partial_bindings(self):
        self.assertEqual(bindings("p(a). q(b).", "p(X); q(Y)"), [{"X": "a"}, {"Y": "b"}])

    def test_duplicate_answers_keep_first_proof(self):
        result = answer("p(a). q(a).", "p(X); q(X); p(X)")
        self.assertEqual(len(result["answers"]), 1)
        self.assertEqual(result["answers"][0]["proof"]["premises"][0]["conclusion"], "p(a)")

    def test_ground_expressions_use_three_valued_truth_tables(self):
        order = {"false": 0, "unknown": 1, "true": 2}
        for left, right in itertools.product(order, repeat=2):
            facts = " ".join(("" if status == "unknown" else ("not " if status == "false" else "") + name + ".")
                             for status, name in ((left, "p"), (right, "q")))
            for operator, expected in ((",", min((left, right), key=order.get)),
                                       (";", max((left, right), key=order.get))):
                with self.subTest(left=left, right=right, operator=operator):
                    result = answer(facts, "p" + operator + "q")
                    self.assertEqual(result["status"], expected)
                    self.assertEqual(result["proof"] is None, expected == "unknown")
                    if expected == "false":
                        self.assertTrue(result["proof"]["conclusion"].startswith("not ("))

    def test_explicit_negative_literals_can_bind_variables(self):
        result = answer("not blocked(a). path(a). path(b).", "path(X), not blocked(X)")
        self.assertEqual(result["answers"][0]["bindings"], {"X": "a"})
        self.assertEqual(result["answers"][0]["proof"]["premises"][1]["conclusion"], "not blocked(a)")

    def test_scope_provenance_tracks_only_selected_support(self):
        report = evaluate("p(a).", """suppose(q(a), unused) {
            suppose(r(a)) { p(X), (q(X); r(X)). }
            p(a), q(a).
        } p(a), q(a).""")
        outer, after = report["results"]
        result = outer["results"][0]["results"][0]["answers"][0]
        self.assertEqual(result["assumptions_used"], [{"scope": "hypothesis_1", "literal": "q(a)"}])
        self.assertEqual(outer["results"][1]["status"], "true")
        self.assertEqual(after["status"], "unknown")

    def test_opposing_proof_preserves_assumption_dependencies(self):
        result = evaluate("p.", "suppose(not q) { p, q. }")["results"][0]["results"][0]
        self.assertEqual(result["status"], "false")
        self.assertEqual(result["assumptions_used"], [{"scope": "hypothesis_1", "literal": "not q"}])

    def test_query_prefix_prove_and_period_separation(self):
        self.assertEqual(parse_queries("?- p(X), q(X)."), parse_queries("prove(p(X), q(X))."))
        requests = parse_queries("?- p(a). ?- (q(a); r(a)).")
        self.assertIsInstance(requests[0], ProveQuery)
        self.assertIsInstance(requests[1], ExpressionQuery)

    def test_invalid_expression_diagnostics(self):
        for source in ("?-", "p,", ";p", "p;;q", "()", "(p;q", "p;q)", "prove()", "not (p;q)"):
            with self.subTest(source=source), self.assertRaises(KGodelError):
                parse_queries(source)

    def test_expression_limits_and_canonical_roundtrip(self):
        source = ",".join(["p"] * 256)
        parsed = parse_queries(source)
        self.assertEqual(parse_queries(str(parsed[0].expression)), parsed)
        for source in (source + ",p", "(" * 64 + "p" + ")" * 64):
            with self.subTest(source=source), self.assertRaises(KGodelError):
                parse_queries(source)
        source = "p"
        for _ in range(32):
            source = "(" + source + ",p)"
        parsed = parse_queries(source)
        self.assertEqual(parse_queries(str(parsed[0].expression)), parsed)
        with self.assertRaisesRegex(KGodelError, "expression depth"):
            parse_queries("(" + source + ",p)")

    def test_work_limit_is_an_error_not_missing_support(self):
        report = evaluate("p(a). p(b).", "(p(X); p(X)), p(Y)", max_work=2)
        self.assertEqual(report["status"], "error")
        self.assertIn("work limit", report["results"][0]["error"])


class PrologTermTests(unittest.TestCase):
    def test_anonymous_occurrences_match_independently(self):
        self.assertEqual(bindings("pair(a, b). pair(c, d).", "pair(_, _)"), [{}])
        self.assertEqual(bindings("p(a). q(b).", "p(_), q(_)"), [{}])

    def test_anonymous_projection_deduplicates_named_bindings(self):
        self.assertEqual(bindings("pair(a, b). pair(a, c).", "pair(X, _)"), [{"X": "a"}])

    def test_named_underscore_variables_share_bindings(self):
        facts = "pair(a, b). pair(c, c)."
        self.assertEqual(bindings(facts, "pair(_Value, _Value)"), [{"_Value": "c"}])

    def test_anonymous_rule_body_and_recursive_shorthand(self):
        declarations = """parent(a, b). parent(b, c). parent(c, d).
            ancestor(X, Y) :- parent(X, Y).
            ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
            has_child(X) :- parent(X, _).
            connected :- parent(_, _).
        """
        self.assertEqual(bindings(declarations, "ancestor(a, Y), has_child(Y)"),
                         [{"Y": "b"}, {"Y": "c"}])
        self.assertEqual(answer(declarations, "connected")["status"], "true")

    def test_explicit_and_shorthand_declarations_are_equivalent(self):
        shorthand = "p(a). q(X) :- p(X). not r(a). not s(X) :- q(X)."
        explicit = "belief p(a). rule q(X) :- p(X). belief not r(a). rule not s(X) :- q(X)."
        self.assertEqual(parse("agent test {" + shorthand + "}"), parse("agent test {" + explicit + "}"))
        mixed = parse("agent test { p(a). rule q(X) :- p(X). r(X) :- q(X). }")
        self.assertEqual([rule.name for rule in mixed.rules], ["rule_1", "rule_2"])

    def test_shorthand_keeps_fact_groundness_and_rule_safety(self):
        for declaration in ("p(X).", "p(_).", "p(X) :- q(Y).", "p(_) :- q(a).", "rule p(_) :- q(_)."):
            with self.subTest(declaration=declaration), self.assertRaises(KGodelError):
                parse("agent test {" + declaration + "}")

    def test_single_quoted_constants_and_escapes(self):
        query = parse_query(r'''value('Mary Jane', 'it''s', 'it\'s', 'line\nnext', 'a\\b', 'မြန်မာ', '').''')
        self.assertEqual(query.atom.args, ("Mary Jane", "it's", "it's", "line\nnext", "a\\b", "မြန်မာ", ""))
        self.assertEqual(parse_query(str(query)), query)
        self.assertEqual(answer("p('a').", 'p("a")')["status"], "true")

    def test_bad_quoted_constants_report_errors(self):
        for source in ("p('missing)", r"p('bad\z')", "'predicate'(a)"):
            with self.subTest(source=source), self.assertRaises(KGodelError):
                parse_query(source)

    def test_quoted_underscore_is_a_constant(self):
        self.assertEqual(answer("p('_').", 'p("_")')["status"], "true")
        self.assertEqual(bindings("p('_').", "p(_Name)"), [{"_Name": "_"}])

    def test_anonymous_cannot_be_grounded_into_effects(self):
        with self.assertRaisesRegex(KGodelError, "Anonymous variables"):
            parse_query("p(_)").ground({"_": "a"})

    def test_anonymous_no_answers_does_not_claim_falsity(self):
        report = evaluate("not p(a).", "p(_)")
        self.assertEqual(report["results"][0]["status"], "no_answers")
        self.assertIn("does not establish explicit falsity", format_query_results(report))
        self.assertIn("true (no named bindings)", format_query_results(evaluate("p(a).", "p(_)")))


class PrologIntegrationTests(unittest.TestCase):
    def make_agent(self, declarations):
        return Agent(parse("agent test {" + declarations + " goal done. }"), RouteWorld("start", [], []))

    def test_anonymous_methods_receivers_and_named_parameters(self):
        agent = self.make_agent("""
            class Relation {
                method has: _X { pair(_X, _). }
                method any { pair(_, _). }
            }
            object one : Relation {} object two : Relation {}
            pair(a, b).
        """)
        result = agent.query("[_ has: X], [_ any]")["results"][0]
        self.assertEqual([row["bindings"] for row in result["answers"]], [{"X": "a"}])
        self.assertEqual(parse(program_source(agent.program)), agent.program)

    def test_every_message_branch_is_validated(self):
        agent = self.make_agent("class Flag { method yes { ready. } } object flag : Flag {} ready.")
        for query in ("ready; [missing yes]", "ready; [flag missing]", "[flag yes], [missing yes]"):
            with self.subTest(query=query), self.assertRaises(KGodelError):
                agent.query(query)

    def test_quoted_self_and_super_stay_literal_in_methods(self):
        program = parse("""agent test {
            class Flag { method ready { label('self', 'super'). } }
            object flag : Flag {} label('self', 'super').
        }""")
        self.assertEqual(parse(program_source(program)), program)
        report = evaluate_queries(Knowledge(program.beliefs), program.effective_rules, parse_queries("[flag ready]"))
        self.assertEqual(report["results"][0]["status"], "true")

    def test_anonymous_disallowed_in_ground_or_effect_contexts(self):
        bad = ["belief p(_).", "goal p(_).", "class C { method p: _ { q(_). } }",
               "plan p(_) for done { when ready. observe clear(a). }",
               "plan p for at(_) { when ready. observe clear(a). }",
               "plan p for done { when ready. observe clear(_). }",
               "plan p for done { when unknown(p(_)). observe clear(a). }",
               "plan p for done { when ready. require p(_). observe clear(a). }",
               "plan p for done { when ready. suppose(p(a)) { p(_). } observe clear(a). }"]
        for source in bad:
            with self.subTest(source=source), self.assertRaises(KGodelError):
                parse("agent test {" + source + "}")
        with self.assertRaises(KGodelError):
            parse_queries("suppose(p(_)) { p(a). }")

    def test_plan_hypothesis_join_and_alternative_survive_checkpoint(self):
        program = parse("""agent route {
            at(start). path(start, goal). label(route, accepted).
            goal at(goal).
            plan travel(_From, _To) for at(_To) {
                when at(_From), path(_From, _To), label(_, _).
                suppose(clear(_To)) { prove(path(_From, _To), (clear(_To); open(_To))). }
                observe clear(_To).
                require clear(_To).
                act move(_From, _To).
            }
        }""")
        agent = Agent(program, RouteWorld("start", [["start", "goal"]], []))
        before = dumps_session(agent)
        self.assertEqual(agent.query("?- at(X), path(X, Y); open(Y).")["status"], "ok")
        self.assertEqual(dumps_session(agent), before)
        agent.run(1)
        self.assertIsNotNone(agent.intention)
        self.assertNotIn("_", agent.intention.candidate.bindings)
        saved = dumps_session(agent)
        self.assertEqual(json.loads(saved)["schema_version"], 5)
        restored = loads_session(saved)
        self.assertEqual(restored.program, program)
        self.assertEqual(restored.decisions, agent.decisions)
        self.assertEqual(restored.run(), agent.run())
        self.assertEqual(restored.world.position, "goal")
        self.assertEqual(len(restored.events), 2)

    def test_schema_three_sessions_still_resume(self):
        for name in DEMOS:
            with self.subTest(demo=name):
                agent = load_demo(name)
                agent.run(1)
                data = json.loads(dumps_session(agent))
                data["schema_version"] = 3
                self.assertEqual(loads_session(json.dumps(data)).run(), agent.run())

    def test_shell_queries_explanations_and_abduction_boundary(self):
        shell = ShellSession(load_demo("super-routes"))
        output = shell.execute(":explain ?- path(start, X), path(X, goal).")
        self.assertIn("X = forest", output)
        self.assertIn("query:and", output)
        self.assertIn("true (no named bindings)", shell.execute("?- path(_, _)."))
        agent = self.make_agent("p('Mary Jane').")
        self.assertEqual(agent.abduce("p('Mary Jane')", [])["status"], "complete")
        for query in ("p(_)", "p(a); p(b)"):
            with self.subTest(query=query), self.assertRaises(KGodelError):
                agent.abduce(query, [])

    def test_example_cli_query_file_and_json_proofs(self):
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "answers.json"
            output, errors = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                result = main(["explain", str(ROOT / "examples/prolog_family.kg"),
                               "--file", str(ROOT / "examples/prolog_family.kgq"),
                               "--result-json", str(result_path)])
            self.assertEqual(result, 0, errors.getvalue())
            report = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "ok")
            self.assertIn("query:and", output.getvalue())
            self.assertIn("true (no named bindings)", output.getvalue())


if __name__ == "__main__":
    unittest.main()

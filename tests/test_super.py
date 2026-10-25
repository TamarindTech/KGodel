from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from kgodel.__main__ import main
from kgodel.comparison import compare_agents
from kgodel.demos import load_demo
from kgodel.logic import Inference, Knowledge
from kgodel.model import Atom, KGodelError, KnowledgeConflict, Literal, SuperRef, Var, match
from kgodel.objects import ObjectSpace
from kgodel.parser import parse, parse_query
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import dumps_session, loads_session, program_source
from kgodel.shell import ShellSession


ROOT = Path(__file__).resolve().parents[1]


def make_agent(contents):
    return Agent(parse("agent test { " + contents + " goal done. }"), RouteWorld("start", [], []))


def answer(agent, source):
    return agent.query(source)["results"][0]


POLICY = """
    class Base { method allowed: X { offered(X). } }
    class Restricted extends Base {
        method allowed: X { [super allowed: X]. approved(X). }
    }
    object policy : Restricted {}
    belief offered(forest). belief offered(bridge). belief approved(forest).
"""


class SuperDispatchTests(unittest.TestCase):
    def test_override_reuses_parent_without_exposing_parent_answers(self):
        agent = make_agent(POLICY)
        self.assertEqual(answer(agent, "[policy allowed: forest]")["status"], "true")
        self.assertEqual(answer(agent, "[policy allowed: bridge]")["status"], "unknown")
        rows = answer(agent, "[Receiver allowed: Place]")["answers"]
        self.assertEqual([row["bindings"] for row in rows], [{"Place": "forest", "Receiver": "policy"}])
        proof = rows[0]["proof"]
        self.assertEqual(proof["source"], "method:Restricted>>allowed:@policy#1")
        self.assertEqual(proof["premises"][0]["conclusion"], "[policy ^Base allowed: forest]")
        self.assertEqual(proof["premises"][0]["source"], "method:Base>>allowed:@policy#1")

    def test_lookup_starts_above_defining_class_when_method_is_inherited(self):
        agent = make_agent("""
            class Root { method ready { rooted. } }
            class Middle extends Root { method ready { [super ready]. checked. } }
            class Leaf extends Middle {}
            object leaf : Leaf {} belief rooted. belief checked.
        """)
        result = answer(agent, "[leaf ready]")
        self.assertEqual(result["status"], "true")
        self.assertEqual(result["proof"]["premises"][0]["conclusion"], "[leaf ^Root ready]")

    def test_parent_self_send_still_dispatches_to_leaf_override(self):
        agent = make_agent("""
            class Root {
                method ready { [self approved]. }
                method approved { unavailable. }
            }
            class Middle extends Root { method ready { [super ready]. checked. } }
            class Leaf extends Middle { method approved { accepted. } }
            object leaf : Leaf {} belief accepted. belief checked.
        """)
        result = answer(agent, "[leaf ready]")
        self.assertEqual(result["status"], "true")
        nested = result["proof"]["premises"][0]["premises"][0]
        self.assertEqual(nested["conclusion"], "[leaf approved]")
        self.assertIn("method:Leaf>>approved", nested["source"])

    def test_nested_super_sends_and_skipped_parent_definitions(self):
        agent = make_agent("""
            class Root { method ready { rooted. } }
            class Gap extends Root {}
            class Middle extends Gap { method ready { [super ready]. checked. } }
            class Leaf extends Middle { method ready { [super ready]. accepted. } }
            object leaf : Leaf {} belief rooted. belief checked. belief accepted.
        """)
        result = answer(agent, "[leaf ready]")
        self.assertEqual(result["status"], "true")
        middle = result["proof"]["premises"][0]
        self.assertEqual(middle["conclusion"], "[leaf ^Middle ready]")
        self.assertEqual(middle["premises"][0]["conclusion"], "[leaf ^Gap ready]")
        self.assertIn("method:Root>>ready", middle["premises"][0]["source"])

    def test_different_selector_slots_and_concrete_self_use_original_instance(self):
        agent = make_agent("""
            class Base {
                slot label.
                method named: X { name(self, @label, X). }
            }
            class Child extends Base { method ready: X { [super named: X]. } }
            object one : Child { label = first. }
            object two : Child { label = second. }
            belief name(one, first, a). belief name(two, second, b).
        """)
        rows = answer(agent, "[Receiver ready: Value]")["answers"]
        self.assertEqual([r["bindings"] for r in rows],
                         [{"Value": "a", "Receiver": "one"}, {"Value": "b", "Receiver": "two"}])

    def test_parent_alternative_clauses_and_local_variable_scopes(self):
        agent = make_agent("""
            class Base {
                method link: X { edge(X, Local). allowed(Local). }
                method link: X { fallback(X). }
            }
            class Child extends Base {
                method ready: Local { [super link: Local]. }
            }
            object policy : Child {}
            belief edge(a, b). belief allowed(b). belief fallback(c).
        """)
        rows = answer(agent, "[policy ready: X]")["answers"]
        self.assertEqual([r["bindings"] for r in rows], [{"X": "a"}, {"X": "c"}])

    def test_negative_super_support_is_explicit_and_separate_from_override(self):
        agent = make_agent("""
            class Base { method not allowed: X { blocked(X). } }
            class Child extends Base {
                method allowed: X { exception(X). }
                method rejected: X { not [super allowed: X]. }
            }
            object policy : Child {} belief blocked(bridge). belief exception(bridge).
        """)
        self.assertEqual(answer(agent, "[policy allowed: bridge]")["status"], "true")
        result = answer(agent, "[policy rejected: bridge]")
        self.assertEqual(result["status"], "true")
        self.assertEqual(result["proof"]["premises"][0]["conclusion"], "not [policy ^Base allowed: bridge]")

    def test_negative_override_can_reuse_negative_parent_clause(self):
        agent = make_agent("""
            class Base { method not ready { blocked. } }
            class Child extends Base { method not ready { not [super ready]. } }
            object policy : Child {} belief blocked.
        """)
        self.assertEqual(answer(agent, "[policy ready]")["status"], "false")

    def test_both_parent_polarities_still_report_a_knowledge_conflict(self):
        agent = make_agent("""
            class Base { method ready { yes. } method not ready { no. } }
            class Child extends Base { method ready { [super ready]. } }
            object policy : Child {} belief yes. belief no.
        """)
        with self.assertRaises(KnowledgeConflict):
            agent.query("[policy ready]")

    def test_public_evidence_cannot_supply_missing_super_support(self):
        agent = make_agent("""
            class Base { method ready { missing. } }
            class Child extends Base { method checked { [super ready]. } }
            object policy : Child {} belief [policy ready].
        """)
        self.assertEqual(answer(agent, "[policy ready]")["status"], "true")
        self.assertEqual(answer(agent, "[policy checked]")["status"], "unknown")

    def test_recursive_self_sends_through_super_reach_a_fixed_point(self):
        agent = make_agent("""
            class Base {
                method reaches: X { seed(X). }
                method reaches: X { [self reaches: Y]. edge(Y, X). }
            }
            class Child extends Base { method reaches: X { [super reaches: X]. approved(X). } }
            object policy : Child {}
            belief seed(a). belief edge(a, b). belief edge(b, c). belief edge(c, a).
            belief approved(a). belief approved(b).
        """)
        rows = answer(agent, "[policy reaches: X]")["answers"]
        self.assertEqual([r["bindings"] for r in rows], [{"X": "a"}, {"X": "b"}])
        with self.assertRaisesRegex(KGodelError, "fact limit"):
            agent.query("[policy reaches: a]", max_facts=7)
        with self.assertRaisesRegex(KGodelError, "work limit"):
            agent.query("[policy reaches: a]", max_work=0)

    def test_unreferenced_parent_methods_do_not_introduce_conflicts(self):
        agent = make_agent("""
            class Base { method ready { yes. } method not ready { no. } }
            class Child extends Base { method ready { yes. } }
            object policy : Child {} belief yes. belief no.
        """)
        self.assertEqual(answer(agent, "[policy ready]")["status"], "true")
        self.assertEqual(len(agent.program.effective_rules), 1)

    def test_invalid_super_sends_are_rejected_even_in_unused_classes(self):
        for source, error in [
            ("class Root { method ready { [super ready]. } }", "requires a superclass"),
            ("class Base {} class Child extends Base { method ready { [super absent]. } }",
             "does not understand"),
        ]:
            with self.subTest(source=source), self.assertRaisesRegex(KGodelError, error):
                make_agent(source)

    def test_private_lookup_namespace_cannot_be_written_in_source_or_queries(self):
        for source in ("[policy ^Base allowed: forest]", "not [policy ^Base allowed: forest]"):
            with self.assertRaisesRegex(KGodelError, "reserved for stored proofs"):
                parse_query(source)
            with self.assertRaisesRegex(KGodelError, "reserved for stored proofs"):
                make_agent(POLICY + "belief " + source + ".")
        public = Atom("allowed:", (Var("X"),), "policy")
        scoped = Atom("allowed:", ("forest",), "policy", "Base")
        self.assertIsNone(match(public, scoped))
        self.assertIsNone(match(scoped, Atom("allowed:", ("forest",), "policy")))
        with self.assertRaisesRegex(KGodelError, "reserved"):
            ObjectSpace(make_agent(POLICY).program).validate_atom(scoped)
        with self.assertRaises(KGodelError):
            Atom("ready", (), SuperRef()).ground({})
        logic = Inference(Knowledge((Literal(scoped),)), ())
        self.assertEqual(list(logic.solve((Literal(public),))), [])

    def test_compiler_deduplicates_repeated_super_targets_and_applies_rule_limit(self):
        program = make_agent("""
            class Base { method ready { accepted. } }
            class Child extends Base {
                method first { [super ready]. [super ready]. }
                method second { [super ready]. }
            }
            object policy : Child {} belief accepted.
        """).program
        private = [rule for rule in program.effective_rules if rule.head.atom.lookup_class]
        self.assertEqual(len(private), 1)
        # A distinct private parent clause counts toward the same expansion cap.
        instances = " ".join(f"object p{i} : Child {{}}" for i in range(5001))
        with self.assertRaisesRegex(KGodelError, "method rule limit"):
            make_agent("class Base { method ready { yes. } } "
                       "class Child extends Base { method ready { [super ready]. } } " + instances)


class SuperIntegrationTests(unittest.TestCase):
    def test_hypotheses_preserve_parent_assumptions_without_mutation(self):
        agent = make_agent(POLICY)
        before = dumps_session(agent)
        with patch.object(RouteWorld, "act", side_effect=AssertionError("act")), \
                patch.object(RouteWorld, "observe", side_effect=AssertionError("observe")):
            result = agent.query("suppose(offered(meadow), approved(meadow)) { prove([policy allowed: meadow]). }")
            query = result["results"][0]["results"][0]
            self.assertEqual(query["status"], "true")
            self.assertEqual({a["literal"] for a in query["assumptions_used"]},
                             {"offered(meadow)", "approved(meadow)"})
        self.assertEqual(before, dumps_session(agent))
        self.assertEqual(answer(agent, "[policy allowed: meadow]")["status"], "unknown")

    def test_super_demo_pauses_resumes_and_preserves_parent_proofs(self):
        agent = load_demo("super-routes")
        agent.run(1)
        self.assertIsNotNone(agent.intention)
        serialized = dumps_session(agent)
        self.assertEqual(json.loads(serialized)["schema_version"], 4)
        self.assertIn("^RoutePolicy", serialized)
        restored = loads_session(serialized)
        self.assertEqual(restored.program, agent.program)
        self.assertEqual(restored.intention, agent.intention)
        self.assertEqual(restored.run(), agent.run())
        self.assertEqual(agent.world.position, "goal")
        self.assertEqual(len(agent.events), 4)
        self.assertNotIn("bridge", " ".join(event["argument"] for event in agent.events))

    def test_schema_two_objects_and_literal_super_receivers_keep_their_meaning(self):
        legacy = """agent legacy {
            class Flag { method ready { known. } }
            class Wrapper { method ready { [super ready]. named(super). } }
            object super : Flag {} object wrapper : Wrapper {}
            belief known. belief named(super). goal done.
        }"""
        data = json.loads(dumps_session(load_demo("object-routes")))
        data.update(schema_version=2, kgodel_version="0.8.0", program=legacy)
        data["beliefs"] = [dict(conclusion="known", source="program", premises=[]),
                           dict(conclusion="named(super)", source="program", premises=[])]
        restored = loads_session(json.dumps(data))
        self.assertEqual(answer(restored, "[wrapper ready]")["status"], "true")
        self.assertIn('["super" ready]', program_source(restored.program))
        self.assertEqual(loads_session(dumps_session(restored)).program, restored.program)
        for name in ("object-routes", "multistep-route"):
            old = json.loads(dumps_session(load_demo(name)))
            old.update(schema_version=2, kgodel_version="0.8.0")
            self.assertEqual(loads_session(json.dumps(old)).run()["status"], "achieved")

    def test_super_string_constants_remain_available_and_source_round_trips(self):
        agent = make_agent('''
            class Flag { method ready { named(super). } }
            class Wrapper { method ready { ["super" ready]. named("super"). } }
            object super : Flag {} object wrapper : Wrapper {} belief named(super).
        ''')
        self.assertEqual(answer(agent, "[super ready]")["status"], "true")
        self.assertEqual(answer(agent, "[wrapper ready]")["status"], "true")
        self.assertEqual(parse(program_source(agent.program)), agent.program)
        self.assertEqual(parse(program_source(load_demo("super-routes").program)), load_demo("super-routes").program)

    def test_private_support_cannot_be_restored_as_accepted_belief(self):
        data = json.loads(dumps_session(make_agent(POLICY)))
        data["beliefs"].append(dict(conclusion="[policy ^Base allowed: bridge]", source="program", premises=[]))
        with self.assertRaisesRegex(KGodelError, "cannot be an accepted belief"):
            loads_session(json.dumps(data))

    def test_comparison_tracks_public_answers_with_nested_super_proofs(self):
        before = make_agent(POLICY)
        after = make_agent(POLICY + "belief approved(bridge).")
        report = compare_agents(before, after, queries=["[policy allowed: bridge]"])
        self.assertEqual(report["queries"][0]["before"]["status"], "unknown")
        self.assertEqual(report["queries"][0]["after"]["status"], "true")
        changes = report["consequences"]["changes"]
        self.assertTrue(any(row["literal"] == "[policy allowed: bridge]" for row in changes))
        self.assertTrue(all("^Base" not in row["literal"] for row in changes))

    def test_cli_and_shell_explain_super_and_execute_demo(self):
        path = str(ROOT / "examples/super_routes.kg")
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["explain", path, "[cautious candidateFrom: start to: forest]"]), 0)
        self.assertIn("^RoutePolicy", output.getvalue())
        self.assertIn("method:ApprovedPolicy", output.getvalue())
        session = ShellSession(load_demo("super-routes"))
        self.assertIn("^ApprovedPolicy", session.execute(":explain [cautious candidateFrom: start to: forest]"))
        self.assertIn("Result: achieved", session.execute(":run"))


if __name__ == "__main__":
    unittest.main()

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kgodel.__main__ import main
from kgodel.comparison import compare_agents
from kgodel.demos import load_demo
from kgodel.logic import Inference, Knowledge
from kgodel.model import Atom, KGodelError, Literal, Var, match
from kgodel.objects import ObjectSpace
from kgodel.parser import parse, parse_query
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import dumps_session, load_session, loads_session, program_source, save_session
from kgodel.shell import ShellSession


ROOT = Path(__file__).resolve().parents[1]


def make_agent(contents):
    return Agent(parse("agent test { " + contents + " goal done. }"), RouteWorld("start", [], []))


def answer(agent, source):
    return agent.query(source)["results"][0]


class MessageTests(unittest.TestCase):
    def test_unary_keyword_negative_and_variable_messages_round_trip(self):
        for source in ("[route clear]", "not [route clear]", "[Route availableFrom: From to: To]",
                       '["self" near: "a b" via: "x\\\\y"]'):
            with self.subTest(source=source):
                literal = parse_query(source)
                self.assertEqual(parse_query(str(literal)), literal)
        message = parse_query("[Route availableFrom: From to: To]").atom
        self.assertEqual(message.variables, {"Route", "From", "To"})
        self.assertEqual(str(message.ground({"Route": "cautious", "From": "start", "To": "forest"})),
                         "[cautious availableFrom: start to: forest]")

    def test_receiver_matching_preserves_variable_consistency_and_predicate_separation(self):
        pattern = parse_query("[Receiver named: Receiver]").atom
        self.assertEqual(match(pattern, parse_query("[one named: one]").atom), {"Receiver": "one"})
        self.assertIsNone(match(pattern, parse_query("[one named: two]").atom))
        self.assertIsNone(match(Atom("ready"), Atom("ready", (), "one")))
        self.assertIsNone(match(Atom("ready", (), "one"), Atom("ready")))
        program = parse("""agent test {
            class Flag { method ready { evidence. } } object one : Flag {}
            belief ready. goal done.
        }""")
        logic = Inference(Knowledge(program.beliefs), program.effective_rules)
        self.assertEqual(logic.status(parse_query("[one ready]")), "unknown")

    def test_slots_are_distinct_per_instance(self):
        agent = make_agent("""
            class Location { slot place. method clear { clear(@place). } }
            object bridge : Location { place = bridge. }
            object forest : Location { place = forest. }
            belief not clear(bridge). belief clear(forest).
        """)
        self.assertEqual(answer(agent, "[bridge clear]")["status"], "unknown")
        self.assertEqual(answer(agent, "[forest clear]")["status"], "true")
        rows = answer(agent, "[Object clear]")["answers"]
        self.assertEqual([row["bindings"] for row in rows], [{"Object": "forest"}])

    def test_explicit_negative_method_provides_opposing_proof(self):
        agent = make_agent("""
            class Location {
                slot place.
                method clear { clear(@place). }
                method not clear { not clear(@place). }
            }
            object bridge : Location { place = bridge. }
            belief not clear(bridge).
        """)
        result = answer(agent, "[bridge clear]")
        self.assertEqual(result["status"], "false")
        self.assertEqual(result["proof"]["conclusion"], "not [bridge clear]")
        self.assertIn("method:Location>>clear@bridge", result["proof"]["source"])

    def test_inherited_self_send_dispatches_to_child_override(self):
        agent = load_demo("object-routes")
        result = agent.query("""suppose(clear(bridge)) {
            prove([relaxed mayMoveFrom: start to: bridge]).
            prove([cautious mayMoveFrom: start to: bridge]).
        }""")["results"][0]["results"]
        self.assertEqual([item["status"] for item in result], ["true", "unknown"])
        forest = agent.query("suppose(clear(forest)) { prove([cautious mayMoveFrom: start to: forest]). }")
        proof = forest["results"][0]["results"][0]["proof"]
        self.assertIn("RoutePolicy>>mayMoveFrom:to:@cautious", proof["source"])
        self.assertIn("ApprovedPolicy>>candidateFrom:to:@cautious", proof["premises"][0]["source"])

    def test_override_replaces_all_parent_clauses_for_a_selector(self):
        agent = make_agent("""
            class Parent { method ready { yes. } method not ready { no. } }
            class Child extends Parent { method ready { other. } }
            object parent : Parent {} object child : Child {}
            belief no.
        """)
        self.assertEqual(answer(agent, "[parent ready]")["status"], "false")
        self.assertEqual(answer(agent, "[child ready]")["status"], "unknown")

    def test_multiple_method_clauses_and_local_variables_are_logical_alternatives(self):
        agent = make_agent("""
            class Map {
                method reaches: To { path(start, To). }
                method reaches: To { path(start, Middle). path(Middle, To). }
            }
            object map : Map {}
            belief path(start, forest). belief path(forest, goal).
        """)
        rows = answer(agent, "[map reaches: To]")["answers"]
        self.assertEqual({row["bindings"]["To"] for row in rows}, {"forest", "goal"})

    def test_recursive_message_methods_reach_a_finite_fixed_point(self):
        agent = make_agent("""
            class Map {
                method reachesFrom: X to: Y { path(X, Y). }
                method reachesFrom: X to: Y { path(X, Z). [self reachesFrom: Z to: Y]. }
                method loop { [self loop]. }
            }
            object map : Map {}
            belief path(start, forest). belief path(forest, start). belief path(forest, goal).
        """)
        self.assertEqual(answer(agent, "[map reachesFrom: start to: goal]")["status"], "true")
        self.assertEqual(answer(agent, "[map loop]")["status"], "unknown")

    def test_composition_self_values_and_quoted_self_constants(self):
        agent = make_agent('''
            class Flag { method ready { enabled(self). } }
            class Wrapper {
                slot delegate.
                method ready { [@delegate ready]. }
                method literalSelf { label("self"). }
            }
            object flag : Flag {} object wrapper : Wrapper { delegate = flag. }
            belief enabled(flag). belief label("self").
        ''')
        self.assertEqual(answer(agent, "[wrapper ready]")["status"], "true")
        self.assertEqual(answer(agent, "[wrapper literalSelf]")["status"], "true")
        self.assertEqual(parse(program_source(agent.program)), agent.program)

    def test_grandparent_methods_and_slots_survive_inheritance(self):
        agent = make_agent("""
            class Root { slot place. method present { at(@place). } }
            class Middle extends Root {}
            class Leaf extends Middle { method ready { [self present]. } }
            object leaf : Leaf { place = start. } belief at(start).
        """)
        self.assertEqual(answer(agent, "[leaf ready]")["status"], "true")
        description = ObjectSpace(agent.program).describe()["classes"][-1]
        self.assertEqual(description["slots"], ["place"])
        self.assertEqual(description["methods"][0]["defined_in"], "Root")

    def test_ordinary_rules_can_consume_and_produce_message_evidence(self):
        agent = make_agent("""
            class Flag { method ready { evidence. } } object flag : Flag {}
            belief accepted. rule [flag ready] :- accepted.
            rule can_continue :- [flag ready].
        """)
        result = answer(agent, "can_continue")
        self.assertEqual(result["status"], "true")
        self.assertEqual(result["proof"]["premises"][0]["source"], "rule_1")

    def test_queries_hypotheses_send_and_object_inspection_are_pure(self):
        agent = load_demo("object-routes")
        before = dumps_session(agent)
        with patch.object(RouteWorld, "act", side_effect=AssertionError("act")), \
                patch.object(RouteWorld, "observe", side_effect=AssertionError("observe")):
            self.assertEqual(agent.send("cautious", "candidateFrom:to:", "start", "forest")["results"][0]["status"], "true")
            result = agent.query("suppose(clear(forest)) { prove([cautious mayMoveFrom: start to: forest]). }")
            self.assertEqual(result["results"][0]["results"][0]["assumptions_used"][0]["literal"], "clear(forest)")
            self.assertIn("ApprovedPolicy", ShellSession(agent).execute(":objects"))
        self.assertEqual(dumps_session(agent), before)

    def test_missing_receiver_or_selector_reports_a_message_error(self):
        agent = load_demo("object-routes")
        for query in ("[missing finished]", "[cautious absent]", "[Receiver absent]"):
            with self.subTest(query=query), self.assertRaises(KGodelError):
                agent.query(query)
        for arguments in (("missing", "finished"), ("cautious", "absent"),
                          ("cautious", "candidateFrom:to:", "start"), ("cautious", "finished", "extra"),
                          ("cautious", "bad-selector"), ("cautious", "candidateFrom:to:", "start", 3)):
            with self.subTest(arguments=arguments), self.assertRaises(KGodelError):
                agent.send(*arguments)

    def test_variable_receivers_and_arguments_return_distinct_bindings(self):
        agent = load_demo("object-routes")
        rows = answer(agent, "[Receiver candidateFrom: start to: Place]")["answers"]
        actual = {(row["bindings"]["Receiver"], row["bindings"]["Place"]) for row in rows}
        self.assertEqual(actual, {("relaxed", "bridge"), ("relaxed", "forest"), ("cautious", "forest")})

    def test_method_inference_obeys_existing_fact_and_work_budgets(self):
        agent = load_demo("object-routes")
        with self.assertRaisesRegex(KGodelError, "work limit"):
            agent.send("cautious", "finished", max_work=0)
        with self.assertRaisesRegex(KGodelError, "fact limit"):
            agent.query("[cautious finished]", max_facts=0)

    def test_message_atoms_cannot_be_executed_as_simulator_predicates(self):
        world = RouteWorld("start", [["start", "goal"]], [])
        with self.assertRaises(KGodelError):
            world.act(Atom("move", ("start", "goal"), "receiver"))
        with self.assertRaises(KGodelError):
            world.observe(Atom("clear", ("goal",), "receiver"))
        self.assertEqual((world.position, world.action_calls, world.observation_calls), ("start", 0, 0))


class ObjectValidationTests(unittest.TestCase):
    def test_malformed_or_ambiguous_declarations_are_rejected(self):
        invalid = [
            "class Lower {} class Lower {}", "class lower {}", "class Child extends Missing {}",
            "class A extends B {} class B extends A {}", "class A { slot x. slot x. }",
            "class A { slot x. } class B extends A { slot x. }", "object one : Missing {}",
            "class A {} object one : A {} object one : A {}",
            "class A { slot x. } object one : A {}",
            "class A {} object one : A { extra = value. }",
            "class A { slot x. } object one : A { x = one. x = two. }",
            "class A { slot x. } object one : A { x = Value. }",
            "class A { method ready {} }",
            "class A { method choose: X { ready. } }",
            "class A { method choose: X with: X { ready(X). } }",
            "class A { method choose: constant { ready. } }",
            "class A { method ready { known(@missing). } }",
            "class A { method ready { [self absent]. } } object one : A {}",
            "class A { method ready { [missing ready]. } } object one : A {}",
            "class A {} object one : A {} belief [one ready].",
            "belief at(@place).", "goal [missing ready].",
            "class A { method ready { observe clear(a). } }",
            "class A { method ready { known. } } object one : A {} "
            "plan bad for done { when known. act [one ready]. }",
        ]
        for source in invalid:
            with self.subTest(source=source), self.assertRaises(KGodelError):
                parse("agent test { " + source + " }")

    def test_unused_classes_are_validated_and_parent_cannot_access_child_slots(self):
        with self.assertRaisesRegex(KGodelError, "Unknown instance variable"):
            parse("""agent test {
                class Parent { method ready { known(@childSlot). } }
                class Child extends Parent { slot childSlot. }
            }""")

    def test_inheritance_and_instantiation_have_explicit_limits(self):
        chain = ["class C0 {}"] + [f"class C{i} extends C{i - 1} {{}}" for i in range(1, 65)]
        with self.assertRaisesRegex(KGodelError, "depth exceeds"):
            parse("agent test { " + " ".join(chain) + " }")
        declarations = "class Flag { method ready { known. } } "
        declarations += " ".join(f"object flag{i} : Flag {{}}" for i in range(10001))
        with self.assertRaisesRegex(KGodelError, "method rule limit"):
            parse("agent test { " + declarations + " }")


class ObjectIntegrationTests(unittest.TestCase):
    def test_object_demo_uses_messages_in_goal_guards_hypotheses_and_requirements(self):
        agent = load_demo("object-routes")
        result = agent.run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["steps"], 4)
        self.assertEqual(result["world_position"], "goal")
        self.assertEqual(result["goals"], {"[cautious finished]": "true"})
        self.assertIn("method:RoutePolicy>>finished@cautious", result["goal_proofs"]["[cautious finished]"]["source"])
        self.assertNotIn("bridge", " ".join(event["argument"] for event in result["events"]))

    def test_receiver_variable_is_bound_from_a_plan_target(self):
        source = (ROOT / "examples/object_routes.kg").read_text()
        source = source.replace("plan inspect_and_move(From, To) for [cautious finished]",
                                "plan inspect_and_move(Policy, From, To) for [Policy finished]")
        source = source.replace("when [cautious candidateFrom:", "when [Policy candidateFrom:")
        agent = Agent(parse(source), load_demo("object-routes").world)
        result = agent.run()
        self.assertEqual(result["status"], "achieved")
        self.assertEqual(result["events"][0]["bindings"]["Policy"], "cautious")

    def test_current_schema_preserves_objects_proofs_and_unfinished_intentions(self):
        agent = load_demo("object-routes")
        agent.run(1)
        serialized = dumps_session(agent)
        self.assertEqual(json.loads(serialized)["schema_version"], 4)
        restored = loads_session(serialized)
        self.assertEqual(restored.program, agent.program)
        self.assertEqual(restored.intention, agent.intention)
        self.assertEqual(restored.run(), agent.run())
        self.assertEqual(parse(program_source(restored.program)), restored.program)

    def test_schema_one_still_loads_but_cannot_contain_object_programs(self):
        old = json.loads(dumps_session(load_demo()))
        old.update(schema_version=1, kgodel_version="0.7.0")
        self.assertEqual(loads_session(json.dumps(old)).run()["status"], "achieved")
        bad = json.loads(dumps_session(load_demo("object-routes")))
        bad["schema_version"] = 1
        with self.assertRaisesRegex(KGodelError, "schema 2"):
            loads_session(json.dumps(bad))

    def test_legacy_self_constant_keeps_its_checkpoint_fingerprint(self):
        agent = make_agent("""
            belief named(self).
            plan inspect for done { when named(self). observe clear(start). }
        """)
        agent.run(1)
        self.assertIn("named(self)", agent.knowledge.fingerprint())
        old = json.loads(dumps_session(agent))
        old.update(schema_version=1, kgodel_version="0.7.0")
        restored = loads_session(json.dumps(old))
        self.assertEqual(restored.attempts, agent.attempts)
        self.assertEqual(restored.run(), agent.run())

    def test_comparison_detects_configuration_and_method_changes(self):
        before = load_demo("object-routes")
        source = program_source(before.program).replace("permission = reviewed", "permission = pending")
        after = Agent(parse(source), load_demo("object-routes").world)
        report = compare_agents(before, after, queries=["[cautious candidateFrom: start to: forest]"])
        self.assertEqual(report["program"]["changed_sections"], ["objects"])
        self.assertEqual(report["queries"][0]["before"]["status"], "true")
        self.assertEqual(report["queries"][0]["after"]["status"], "unknown")
        source = program_source(before.program).replace("approved(To, @permission)", "reviewed(To, @permission)")
        after = Agent(parse(source), load_demo("object-routes").world)
        self.assertEqual(compare_agents(before, after)["program"]["changed_sections"], ["classes"])

    def test_cli_inspection_query_and_missing_message_diagnostics(self):
        path = str(ROOT / "examples/object_routes.kg")
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["objects", path]), 0)
        self.assertIn("Class ApprovedPolicy extends RoutePolicy", output.getvalue())
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["explain", path, "[cautious candidateFrom: start to: forest]"]), 0)
        self.assertIn("method:ApprovedPolicy", output.getvalue())
        with redirect_stderr(io.StringIO()) as output:
            self.assertEqual(main(["query", path, "[cautious unknownMessage]"]), 2)
        self.assertIn("does not understand", output.getvalue())

    def test_shell_reopens_objects_and_compares_message_goal_progress(self):
        session = ShellSession(load_demo("object-routes"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "objects.json"
            session.execute(":step")
            save_session(session.agent, path)
            session = ShellSession(load_session(path))
            self.assertIn("Object cautious : ApprovedPolicy", session.execute(":objects"))
            self.assertIn("true: [cautious mayMoveFrom: start to: forest]",
                          session.execute("[cautious mayMoveFrom: start to: forest]."))
            self.assertIn("Result: achieved", session.execute(":run"))
            self.assertIn("[cautious finished]: unknown -> true", session.execute(f':compare "{path}"'))
            with self.assertRaises(KGodelError):
                session.execute(":objects extra")


if __name__ == "__main__":
    unittest.main()

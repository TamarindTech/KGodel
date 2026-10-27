"""Run the documented tutorial scenarios and check local Markdown link targets.

Usage from the checkout: python tools/verify_tutorials.py
Only the standard library is required. Generated outputs use a temporary folder.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "tutorials"


def check_links():
    documents = [*sorted(ROOT.glob("*.md")), EXAMPLES / "README.md",
                 *sorted((ROOT / "docs").rglob("*.md")),
                 *sorted((ROOT / "kgodel/templates").rglob("*.md"))]
    checked = 0
    for document in documents:
        contents = document.read_text(encoding="utf-8")
        for target in re.findall(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", contents):
            url = urlsplit(target.strip("<>"))
            if url.scheme or url.netloc or not url.path:
                continue
            path = document.parent / unquote(url.path)
            if not path.exists():
                raise AssertionError(f"Broken local link in {document.relative_to(ROOT)}: {target}")
            checked += 1
    return checked


def verify():
    links = check_links()
    commands = 0
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONIOENCODING"] = "utf-8"

    def python(*args, input=None, expected=0):
        nonlocal commands
        commands += 1
        process = subprocess.run([sys.executable, *map(str, args)], cwd=ROOT, env=environment,
                                 input=input, capture_output=True, text=True, encoding="utf-8", timeout=60)
        if process.returncode != expected:
            raise AssertionError(f"Unexpected exit {process.returncode}, expected {expected}: {args}\n"
                                 f"{process.stdout}\n{process.stderr}")
        return process.stdout

    def cli(*args, **kwargs):
        return python("-m", "kgodel", *args, **kwargs)

    with tempfile.TemporaryDirectory(prefix="kgodel-tutorials-") as directory:
        outputs = Path(directory)

        def report(*args, expected=0, execution=False):
            target = outputs / f"report-{commands}.json"
            flag = "--trace-json" if execution else "--result-json"
            cli(*args, flag, target, expected=expected)
            return json.loads(target.read_text(encoding="utf-8"))

        def query(program, source):
            return report("query", program, source)["results"][0]

        def changed_program(name, addition):
            original = (EXAMPLES / name).read_text(encoding="utf-8")
            body, ending = original.rsplit("}", 1)
            target = outputs / name
            target.write_text(body + addition + "\n}" + ending, encoding="utf-8")
            return target

        def changed_world(name, blocked):
            data = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
            data["blocked"] = blocked
            target = outputs / name
            target.write_text(json.dumps(data), encoding="utf-8")
            return target

        library = EXAMPLES / "library.kg"
        policies = EXAMPLES / "policies.kg"
        first = EXAMPLES / "first_route.kg"
        delivery = EXAMPLES / "delivery.kg"
        for program in (library, policies, first, delivery):
            assert "Valid: agent" in cli("check", program)
        assert cli("--version").strip() == "KGodel 0.13.0a1"
        assert "super-routes" in cli("demo", "--list")

        # Lessons 1 and 2: bindings, explicit opposition, unknown, and recursion.
        rows = report("explain", library, "--file", EXAMPLES / "library.kgq")["results"]
        assert [row["status"] for row in rows] == ["answers", "false", "unknown", "answers", "answers"]
        assert rows[0]["answers"][0]["bindings"] == {"Book": "Logic for Agents"}
        assert {row["bindings"]["Book"] for row in rows[3]["answers"]} == {"Logic for Agents", "Small Worlds"}
        assert rows[4]["answers"][0]["bindings"] == {}
        assert len(query(library, "likes(Person, Topic), topic(Book, Topic)")["answers"]) == 3
        assert [row["bindings"] for row in query(library, "likes(Person, _)")["answers"]] == [
            {"Person": "alice"}, {"Person": "bob"}]
        family = query(ROOT / "examples/prolog_family.kg", "ancestor(alice, Descendant)")
        assert {row["bindings"]["Descendant"] for row in family["answers"]} == {"bob", "carol", "Mary Jane", "david", "emma"}
        exercise = changed_program("library.kg", """
            unavailable_interest(Person, Book) :- likes(Person, Topic), topic(Book, Topic), not available(Book).
        """)
        assert query(exercise, "unavailable_interest(Person, Book)")["answers"][0]["bindings"] == {
            "Person": "alice", "Book": "Small Worlds"}
        transcript = cli("shell", "--demo", "multistep-route",
                         input=":status\n:preview\n:step\n:explain not clear(bridge)\n:quit\n")
        assert "true: not clear(bridge)" in transcript

        # Lesson 3: assumptions leave the parent unchanged; excluded candidates and bounds.
        rows = report("explain", library, "--file", EXAMPLES / "library_hypotheses.kgq")["results"]
        assert rows[0]["status"] == rows[2]["status"] == "unknown"
        conditional = rows[1]["results"][0]["answers"][0]
        assert conditional["bindings"] == {"Book": "Field Notes"}
        assert conditional["assumptions_used"] == [{"scope": "hypothesis_1", "literal": 'available("Field Notes")'}]
        conflict = report("query", library, "suppose(available('Small Worlds')) { recommended(alice, 'Small Worlds'). }", expected=1)
        assert conflict["status"] == "inconsistent"
        abduction = report("abduce", "--program", library, "--file", EXAMPLES / "library_abduction.kga", "--explain")
        assert [row["assumptions"] for row in abduction["solutions"]] == [['available("Field Notes")']]
        assert {row["reason"] for row in abduction["excluded"]} == {"already_supported", "contradicted"}
        partial = report("abduce", "--program", library, "--file", EXAMPLES / "library_abduction.kga", "--max-contexts", "0", expected=1)
        assert partial["status"] == "partial"
        baseline = report("abduce", "--program", library, "recommended(alice, 'Logic for Agents')")
        assert baseline["solutions"][0]["assumptions"] == []

        # Lesson 4: dynamic self dispatch and parent proof support.
        assert "CuratedCatalog" in cli("objects", policies)
        assert query(policies, "[general recommends: 'Small Worlds']")["status"] == "true"
        assert query(policies, "[curated recommends: 'Small Worlds']")["status"] == "unknown"
        proof = report("explain", policies, "[curated recommends: 'Logic for Agents']")["results"][0]
        assert proof["status"] == "true" and "^Catalog" in json.dumps(proof["proof"])
        assert len(query(policies, "[Shelf recommends: Book], available(Book)")["answers"]) == 3
        featured = changed_program("policies.kg", "featured('Small Worlds').")
        assert len(query(featured, "[curated recommends: Book]")["answers"]) == 2

        # Lessons 5 and 6: real observations, interruption, restart, and comparison.
        preview = report("deliberate", first)
        assert preview["selected"]["argument"] == "clear(goal)"
        before, after = outputs / "before.json", outputs / "after.json"
        paused = report("run", first, "--max-steps", "1", "--checkpoint", before, expected=1, execution=True)
        assert paused["status"] == "step_limit" and paused["steps"] == 1
        saved = before.read_bytes()
        data = json.loads(saved)
        assert data["schema_version"] == 5 and data["intention"] is not None
        transcript = cli("shell", "--resume", before, input=":status\n:explain clear(goal)\n:preview\n:quit\n")
        assert "true: clear(goal)" in transcript and "move(start, goal)" in transcript
        finished = report("resume", before, "--checkpoint", after, execution=True)
        assert finished["status"] == "achieved" and finished["steps"] == 2
        assert before.read_bytes() == saved
        assert report("resume", before, execution=True) == finished
        assert report("run", first, execution=True) == finished
        comparison = report("compare", before, after, "--query", "at(goal)", "--explain")
        assert comparison["history"]["operations"]["common_prefix"] == 1
        assert comparison["world"]["position"]["before"] == "start"
        assert comparison["world"]["position"]["after"] == "goal"
        blocked = changed_world("first_route.world.json", ["goal"])
        stuck = report("run", first, "--world", blocked, expected=1, execution=True)
        assert stuck["status"] == "stuck" and stuck["steps"] == 1
        known = changed_program("first_route.kg", """clear(goal).
            plan move_known_clear(From, To) for at(To) {
                when at(From), path(From, To), clear(To). act move(From, To).
            }
        """)
        result = report("run", known, "--world", EXAMPLES / "first_route.world.json", execution=True)
        assert result["status"] == "achieved" and result["steps"] == 1

        # Lesson 7: execute the actual Python lesson blocks and integration module.
        source = (ROOT / "docs/tutorials/07-python-api.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```python\n(.*?)```", source, flags=re.DOTALL)
        assert len(blocks) == 3
        assert "Logic for Agents" in python("-c", "\n".join(blocks))
        transcript = python("-m", "examples.tutorials.inspect_agent", outputs / "python")
        assert "Before execution: 0 observations, 0 actions" in transcript
        assert "Resumed: achieved after 4 total operations" in transcript
        assert "Comparison: ok changed: True" in transcript
        script = (EXAMPLES / "inspect_agent.py").read_text(encoding="utf-8")
        exercise = script.replace("agent.run(max_steps=1)",
                                  'agent.run(max_steps=2)\n    assert agent.world.position == "forest"\n    assert agent.intention is None')
        exercise += "\nmain(Path(" + repr(str(outputs / "python-exercise")) + "))\n"
        # Keep __file__ anchored to the example so its resource paths still work.
        python("-c", "exec(" + repr(exercise) + ", {'__name__': 'tutorial_exercise', '__file__': "
               + repr(str(EXAMPLES / "inspect_agent.py")) + "})")

        # Lesson 8: complete the capstone and test the alternative-world exercise.
        assert query(delivery, "[courier candidateFrom: depot to: forest]")["status"] == "true"
        assert query(delivery, "[courier candidateFrom: depot to: bridge]")["status"] == "unknown"
        abduction = report("abduce", "--program", delivery, "[courier mayMoveFrom: depot to: bridge]",
                           "--assume", "clear(bridge)", "--assume", "open(bridge)")
        assert abduction["solutions"][0]["assumptions"] == ["clear(bridge)", "open(bridge)"]
        assert report("deliberate", delivery)["selected"]["argument"] == "clear(forest)"
        paused_path, done_path = outputs / "delivery-paused.json", outputs / "delivery-done.json"
        report("run", delivery, "--max-steps", "1", "--checkpoint", paused_path, expected=1, execution=True)
        complete = report("resume", paused_path, "--checkpoint", done_path, execution=True)
        assert complete["status"] == "achieved" and complete["steps"] == 4
        assert complete == report("run", delivery, execution=True)
        assert report("compare", paused_path, done_path, "--query", "[courier finished]")["changed"]
        blocked = changed_world("delivery.world.json", ["bridge", "forest"])
        stuck_path = outputs / "delivery-stuck.json"
        stuck = report("run", delivery, "--world", blocked, "--checkpoint", stuck_path, expected=1, execution=True)
        assert stuck["status"] == "stuck" and stuck["steps"] == 1
        transcript = cli("shell", "--resume", stuck_path, input="\n".join([
            ":explain not clear(forest)",
            ":abduce [courier mayMoveFrom: depot to: forest] from (clear(forest))", ":quit", ""]))
        assert "true: not clear(forest)" in transcript
        assert "contradicted by current evidence" in transcript
        known = changed_program("delivery.kg", "clear(forest).")
        result = report("run", known, "--world", EXAMPLES / "delivery.world.json", execution=True)
        assert result["status"] == "achieved" and result["steps"] == 3

        # Lesson 9: computed comparisons, distinct pairs, methods, and scoped evidence.
        comparisons = EXAMPLES / "comparisons.kg"
        assert "Valid: agent" in cli("check", comparisons)
        results = report("explain", comparisons, "--file", EXAMPLES / "comparisons.kgq")["results"]
        assert [item["status"] for item in results] == ["answers", "answers", "answers", "false", "true", "evaluated"]
        assert [item["bindings"] for item in results[0]["answers"]] == [
            {"First": "bob", "Second": "carol"}, {"First": "bob", "Second": "david"},
            {"First": "carol", "Second": "david"}]
        assert "builtin:" in json.dumps(results[0]["answers"][0]["proof"])
        assert [item["bindings"] for item in results[1]["answers"]] == [{"Child": "bob"}, {"Child": "david"}]
        assert [item["bindings"] for item in results[2]["answers"]] == [{"Child": "carol"}, {"Child": "david"}]
        temporary = results[5]["results"][0]["answers"]
        assert [item["bindings"] for item in temporary] == [{"Other": "david"}, {"Other": "emma"}]
        assert temporary[0]["assumptions_used"] == []
        assert temporary[1]["assumptions_used"] == [{"scope": "hypothesis_1", "literal": "parent(alice, emma)"}]
        assert len(query(comparisons, "sibling(First, Second)")["answers"]) == 6
        assert query(comparisons, "sibling(bob, bob)")["status"] == "unknown"
        assert report("query", comparisons, "Child == bob", expected=2)["status"] == "error"
        later = changed_program("comparisons.kg", "later_child(Child) :- parent(alice, Child), Child @>= carol.")
        assert [item["bindings"] for item in query(later, "later_child(Child)")["answers"]] == [
            {"Child": "carol"}, {"Child": "david"}]

    print(f"Tutorials verified: {commands} successful command checks; {links} local Markdown link targets checked.")


if __name__ == "__main__":
    verify()

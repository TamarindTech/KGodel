# 7. Use KGodel from Python

Prerequisites: basic Python and [lessons 2–6](README.md). KGodel has no third-party runtime dependencies. Use the interpreter in which you installed it, or start Python from the repository root.

## Evaluate a knowledge base without a world

This complete example can be entered in Python or saved as a script run from the repository root:

```python
from pathlib import Path
from kgodel.logic import Knowledge
from kgodel.objects import ObjectSpace
from kgodel.parser import parse, parse_queries
from kgodel.querying import evaluate_queries, format_query_results

program = parse(Path("examples/tutorials/library.kg").read_text(encoding="utf-8"))
queries = parse_queries("?- recommended(alice, Book), topic(Book, logic).")
ObjectSpace(program).validate_queries(queries)
report = evaluate_queries(Knowledge(program.beliefs), program.effective_rules, queries)
print(format_query_results(report, explain=True))
```

Use `effective_rules` to include compiled logical methods as well as ordinary rules. Explicit query validation checks object receivers and selectors; `Agent.query` and the CLI already do this for you. `evaluate_queries` does not require goals or a simulator and does not mutate the supplied knowledge.

`parse_query` parses one literal, while `parse_queries` parses query composition and temporary contexts. They are not interchangeable. Comparisons and abduction targets remain single ground literals.

## Read structured results

A normal request returns a report with an overall `status` and a `results` list. A single variable query has `answers`; a ground query has a truth `status`. Each answer includes its bindings, proof, and assumption dependencies. Check the overall and per-request statuses before reading success-only fields:

```python
if report["status"] == "ok":
    result = report["results"][0]
    if result["status"] == "answers":
        for answer in result["answers"]:
            print(answer["bindings"]["Book"])
    elif result["status"] == "no_answers":
        print("No supported bindings")
else:
    print(format_query_results(report))
```

For this known request the result prints `Logic for Agents`. Arbitrary `suppose` requests can contain nested `results`; their outer entries describe contexts rather than direct answers. A report's successful evaluation does not mean every ground question is true.

## Inspect an agent without advancing it

```python
from kgodel.demos import load_demo

agent = load_demo("super-routes")
report = agent.query("?- [cautious candidateFrom: start to: Place].")
message = agent.send("cautious", "candidateFrom:to:", "start", "forest")
preview = agent.deliberate()
explanations = agent.abduce(
    "[cautious mayMoveFrom: start to: bridge]",
    ["clear(bridge)", "open(bridge)"],
    max_assumptions=2,
)
assert agent.world.action_calls == 0
assert agent.world.observation_calls == 0
```

`send` accepts a receiver, selector, and ground string arguments; selector colons correspond to arguments. `query` supports variables and compositions. `deliberate` previews the next decision; `abduce` searches the explicit candidates. All four are pure inspections of the current agent.

An `Agent` requires at least one goal and a compatible `RouteWorld`. For custom source, construct it with `Agent(parse(source), RouteWorld.from_json(world_json))`. A method cannot call Python functions or modify the environment.

## Run the complete integration example

```powershell
python -m examples.tutorials.inspect_agent output/tutorial-python
```

Run this command from the repository root: `examples` is checkout content, not part of the installed wheel. The [script](../../examples/tutorials/inspect_agent.py) loads the delivery capstone, queries candidate routes, searches for bridge assumptions, performs one observation, saves a checkpoint, reloads it, finishes the journey, and compares the two states.

Expected output, apart from platform-specific path separators:

```text
Candidates: [{'Place': 'forest'}]
Missing assumptions: ['clear(bridge)', 'open(bridge)']
Before execution: 0 observations, 0 actions
Resumed: achieved after 4 total operations
Comparison: ok changed: True
Files: output/tutorial-python
```

Two checkpoints are written into that folder. `save_session` creates the parent directory. `load_session` does not replay operations; only the subsequent `run()` advances the restored agent. Comparing two separately loaded agents avoids accidentally comparing a mutated object with itself.

## Handle failures at the right layer

Parsing, invalid object messages, unsupported simulator operations, and some initial inference failures raise `KGodelError`. File access can raise `OSError`. Scoped query failures and bounded searches may instead return an error, inconsistent, or partial report. `run()` reports achieved, stuck, step_limit, or reasoning_error; inspect its status before treating the result as successful.

`agent.query(..., max_work=..., max_facts=...)` sets query inference limits. Abduction exposes separate search limits. `run(max_steps=N)` limits further operations; the returned step count is cumulative. These APIs are experimental and may evolve, so keep interpreter and documentation versions aligned.

## Exercise

Change the script to pause after two operations. Predict the position and what should happen after resume.

<details>
<summary>Worked answer</summary>

Use `agent.run(max_steps=2)`. The agent has inspected and entered `forest`; the first intention has finished. Resuming selects the next journey segment, observes `camp`, and moves there. The total remains four operations. You can verify the pause with `agent.world.position` and `agent.intention`.

</details>

[← Sessions](06-sessions-and-comparison.md) · [Course index](README.md) · [Next: the delivery capstone →](08-delivery-capstone.md)

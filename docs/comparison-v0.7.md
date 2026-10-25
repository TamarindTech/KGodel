# KGodel 0.7: comparing agent states

Versioned reference: comparison semantics remain current. KGodel 0.11 also compares logical object messages and loads checkpoint schemas 1–4. See the [current comparison tutorial](tutorials/06-sessions-and-comparison.md) and [command reference](reference.md).

Comparison makes the effects of evidence and execution inspectable across two states. It operates on saved checkpoints or Python `Agent` instances, and never runs plans, performs observations, moves the simulator, or changes either agent.

## A belief that loses its support

The original blocked-route experiment begins with an outdated belief that the bridge is clear. Save the initial state, attempt the crossing, and compare:

```powershell
python -m kgodel demo blocked-route --max-steps 0 --checkpoint before.json
python -m kgodel resume before.json --max-steps 1 --checkpoint after.json
python -m kgodel compare before.json after.json --query "can_move(start, bridge)" --explain
```

The first two commands return 1 because the goal remains unfinished. The comparison returns 0 when reasoning completes. Its report includes:

```text
Revised clear(bridge) -> not clear(bridge) [simulator:step_1]
can_move(start, bridge): true -> unknown
```

The action supplies negative evidence about the bridge. That retracts the previous positive belief and invalidates the movement proof. The program has no rule deriving `not can_move(start, bridge)`, so the conclusion becomes unknown. Asking `--query "clear(bridge)"` instead shows `true -> false`, with the negative observation as the opposing proof.

## Commands and API

```powershell
python -m kgodel compare before.json after.json --query "at(goal)" --query "not clear(bridge)" --result-json comparison.json
python -m kgodel compare before.json after.json --max-facts 10000 --max-work 200000
```

`--query` accepts a ground signed literal. It does not evaluate a `suppose` block, bind variables, or interpret a `prove(...)` query wrapper. A predicate literally named `prove` remains a normal predicate. Duplicate literal requests are collapsed in first-request order. `--explain` prints the supporting or opposing proof trees; JSON always includes those trees.

From the shell, `:compare PATH` compares the saved checkpoint on the left with the current live agent on the right. Save a baseline with `:checkpoint baseline.json`, execute some operations, then use `:compare baseline.json`. Inspection leaves the last execution record unchanged.

```python
from kgodel.comparison import compare_agents, format_comparison
from kgodel.sessions import load_session

before = load_session("before.json")
after = load_session("after.json")
report = compare_agents(before, after, queries=["at(goal)"])
print(format_comparison(report, explain=True))
```

The API accepts a sequence of query strings, not a single query string. Its report is a detached, JSON-compatible dictionary; editing returned records does not edit either agent. This version supports the built-in route simulator. Compare between execution calls; concurrent mutation is outside the API contract.

## What the report means

| Section | Meaning |
| --- | --- |
| `program` | Agent names and changed declaration sections. Program equality preserves declaration order. |
| `beliefs` | Added and removed base facts, opposing-sign revisions, and changed evidence for unchanged literals. Each entry includes its proof. |
| `consequences` | Changed truth status or proof for atoms derived on at least one side. Each atom is displayed as a positive query, even if a rule derives its negative sign. |
| `goals` | Support for the union of declared goals, plus whether each side declares that goal. |
| `queries` | Support and proofs for the requested ground literals. |
| `world` | Position, directed edges, known nodes, blocked locations, and cumulative action/observation counters. |
| `intention` | Current plan, goal, fixed bindings, identifier, and next step on each side. Changed selection evidence or attempt context also counts as a changed intention. |
| `history` | Equal prefixes, differing suffixes, and counts for operations, decisions, and intention events. Operation and intention-event tails are included. |
| `attempts` | Added and removed retry-suppression records. |
| `last_outcome` | Last run's status and reason; this may differ from current goal support if a Python caller revised beliefs afterward. |
| `next_intention_id` | The next identifier the runtime will allocate. |

`changed` describes stored agent state, including histories, attempts, and evidence. It can be true even when goal truth values stay unchanged. Inference diagnostics and supplied query choices do not themselves count as state changes. A zero-operation run can change the last recorded outcome without changing any belief or world position.

For each logical comparison, `true` includes a supporting proof, `false` includes a proof of the opposite literal, and `unknown` has no proof. `truth_changed` compares these three statuses; `evidence_changed` compares the complete chosen proof trees, including premise sources. If a first proof disappears and an alternative keeps the conclusion true, only the evidence changes. As elsewhere in KGodel, the inference engine records one deterministic proof per supported literal, not all possible proofs.

Base revisions are listed once in `revised`, rather than repeated as additions and removals. Reobserving the same literal can change its source without changing truth. Derived changes are recomputed from each state's current accepted beliefs and its own program, so stale conclusions are not carried over from historical traces.

## Separate scenarios and history

The two inputs may come from different programs or worlds. Program and world differences are shown explicitly. History relations are `equal`, `after_extends_before`, `before_extends_after`, or `diverged`; these labels describe structural equality of recorded prefixes. They do not prove that two files share an ancestor, or that a particular world change caused a particular decision. Independently running a deterministic experiment can produce matching records.

The names “before” and “after” specify comparison direction, not verified chronology. Reversing the arguments reverses additions, removals, and history tails. Intention identifiers are local to each agent, so the same identifier in two independent scenarios does not establish shared identity.

## Limits, failures, and compatibility

Each side gets a fresh inference budget: 10000 facts and 200000 work units by default. `--max-facts` and `--max-work` accept nonnegative integers; the shell uses the defaults. Checkpoint loading validates stored structure without running a separate inference pass. The limits govern fixed-point inference, not the length of the rendered report.

If either side hits a conflict or limit, comparison returns `status: "partial"`. Base beliefs, world state, histories, and intentions remain available. Logical answers on the failed side are `unresolved` with no proof, `truth_changed` and `evidence_changed` are null, and the derived-conclusion comparison is marked unavailable. A partially computed closure is never presented as a completed result. An identical pair of states can therefore have `changed: false` and `status: "partial"`.

Exit codes are 0 for complete reasoning, 1 for a partial report, and 2 for invalid queries, checkpoint formats, limits, or file errors. Differences alone do not cause a nonzero exit. A requested JSON report is written for complete and partial comparisons.

Both input files remain read-only. The CLI rejects a result path that resolves to either checkpoint or is a hard link to one. An explicitly named existing result file is replaced. Comparisons are reports, not resumable checkpoints. Checkpoint schema 1 is unchanged, including compatibility with files written by KGodel 0.6.

# KGodel 0.10: find missing assumptions

Versioned reference: these abduction semantics remain current in KGodel 0.12. Targets and candidate assumptions are still single ground literals; composed queries belong to the query API. See the [hypothesis and abduction tutorial](tutorials/03-hypotheses-and-abduction.md) and [command reference](reference.md).

Abduction asks: **which hypothetical assumptions would make this conclusion provable?** KGodel searches an explicit, finite set of candidates, checks each proposed explanation for consistency, and returns a conditional proof. It does not change accepted beliefs or perform observations and actions.

This extends the existing `suppose` feature. With `suppose`, you choose a whole assumption set and ask what follows. With `abduce`, you supply possible assumptions and KGodel finds the minimal combinations that support a particular query.

## Try it in the shell

```powershell
python -m kgodel shell --demo super-routes
```

```text
:abduce [cautious mayMoveFrom: start to: bridge] from (open(bridge), clear(bridge), clear(forest))
[cautious mayMoveFrom: start to: bridge].
:run
```

The explanation requires `clear(bridge)` and `open(bridge)`. `clear(forest)` is irrelevant. The proof traces through `RoutePolicy`, `ApprovedPolicy`, and `OpenRoutePolicy`, marking the two hypothetical premises. The following ordinary query is still unknown: an explanation has not turned those assumptions into evidence. Running the agent follows its declared plans and the observed forest route.

The shell prints proofs and uses the session's `--max-hypotheses` value as its abduction context budget (64 by default). Its other defaults are the same as the CLI. Use the CLI or Python API for custom search limits.

## Command line

Inspect initial program beliefs without loading a world:

```powershell
python -m kgodel abduce --program examples/super_routes.kg --file examples/route_abduction.kga --explain
```

The request file contains `GOAL from (CANDIDATE, ...)`, with an optional final period. It supports signed literals, object messages, quoted constants, comments, and an empty candidate list. Each goal and candidate must be ground: variables and nested `suppose` blocks are not accepted here.

For an installed demo, provide a query and repeat `--assume`:

```powershell
python -m kgodel abduce --demo super-routes "[cautious mayMoveFrom: start to: bridge]" --assume "clear(bridge)" --assume "open(bridge)" --result-json abduction.json
```

To inspect a saved agent's current beliefs, use `--resume SESSION` instead of `--demo` or `--program`. This loads the checkpoint without advancing execution. The original checkpoint and request files are read-only; an output path that aliases an input is rejected. Explicitly named result files are replaced.

`--file` includes both the query and candidates, so it cannot be combined with a positional query or `--assume`. `--explain` includes full proofs in the text output; JSON always includes them.

## What minimal means

An explanation is **subset-minimal**: removing any of its assumptions makes it cease to support the query. This is different from returning only explanations with the fewest assumptions.

For example:

```text
rule ready :- a.
rule ready :- b, c.
```

With candidates `a`, `b`, and `c`, both `{a}` and `{b, c}` are minimal explanations. `{a, b}` is not minimal because `{a}` already suffices. Explanations are returned in increasing size, with deterministic literal ordering within each size. Duplicate candidates are removed. This is a logical ordering, not a probability, confidence, cost, or recommendation ranking.

Each candidate must be supplied explicitly. KGodel does not invent possible facts, replace contradictory evidence, or generate an action plan. Supplying the query itself as a candidate deliberately permits the direct explanation "assume the query." Public message candidates are allowed under the same rules as ordinary hypothetical message assumptions; compiler-only superclass annotations cannot be supplied.

## Evidence and consistency

- If the query is already true, the result contains the empty explanation and the current proof.
- If its explicit opposite is supported, additive assumptions cannot consistently make it true. The report includes the opposing proof.
- Candidates already supported by base or derived evidence are excluded as unnecessary. Candidates whose opposites are supported are excluded as contradictory, with proofs.
- Every remaining candidate combination is checked against the complete inference closure. A conflict anywhere in that closure rejects the combination, even if it also supports the requested query.
- Explicit negative candidates work normally. Failure to prove a statement does not create its negation.

Accepted beliefs, their sources, the current intention, operation history, and simulator counters remain unchanged. Repeating the search after a real observation uses the new evidence. Explanations are not stored in checkpoints; save the result JSON if you want to preserve a search report. Checkpoint schema 3 is unchanged, and older supported sessions still load.

## Search bounds and incomplete results

| Option | Default | Meaning |
| --- | --- | --- |
| Candidate cap | 16 distinct literals | Fixed cap on the supplied search space |
| `--max-assumptions` | 3 | Largest candidate combination considered |
| `--max-contexts` | 256 | Maximum hypothetical combinations evaluated, excluding initial inference |
| `--max-solutions` | 20 | Maximum returned explanations; must be positive |
| `--max-facts` | 10000 | Fact limit independently for initial inference and each hypothesis |
| `--max-work` | 200000 | Inference work limit independently for initial inference and each hypothesis |

Other numeric limits accept nonnegative integers. A zero context budget can still return an already-supported query's empty explanation. A zero assumption bound considers only that empty case.

The report status has these meanings:

- `complete`: every combination within the requested size bound was resolved or safely pruned. `search.exhaustive` is true when the result also covers the entire eligible candidate space, or initial evidence settles the query. If false, larger combinations were outside the search. Completeness says nothing about facts you did not supply as candidates.
- `partial`: a context or solution limit stopped the search, or inference could not resolve a hypothetical combination. Previously returned explanations remain proven and subset-minimal. Missing explanations remain unknown.
- `inconsistent`: the initial knowledge has a derived conflict, so there is no consistent starting context.
- `error`: initial inference exceeded a resource limit or otherwise failed.

Search considers combinations in increasing size. It prunes supersets of known explanations and inconsistent combinations. If a hypothetical inference cannot finish, search stops rather than skipping that combination: skipping a smaller unresolved set could make a later minimality claim unreliable.

JSON includes candidates, exclusions and their proofs, conditional solutions, conflicting combinations, requested limits, evaluated/pruned counts, completed search sizes, and the reason for stopping. An inference failure also identifies the unresolved assumptions.

CLI exit codes are 0 for a complete search containing an explanation; 1 for partial search or a complete search with no explanation; and 2 for invalid input, initial inconsistency, or initial inference failure. An empty result never establishes general impossibility.

## Python API

```python
from kgodel.demos import load_demo

agent = load_demo("super-routes")
report = agent.abduce(
    "[cautious mayMoveFrom: start to: bridge]",
    ["open(bridge)", "clear(bridge)", "clear(forest)"],
    max_assumptions=2,
    max_contexts=32,
)
assert report["solutions"][0]["assumptions"] == ["clear(bridge)", "open(bridge)"]
assert agent.world.action_calls == 0
```

`Agent.abduce` accepts a ground query string and a list or tuple of candidate strings. Its keyword limits match the CLI names with underscores. The lower-level `find_explanations(program, knowledge, query, candidates, **limits)` in `kgodel.abduction` accepts parsed literals and works without a simulator. `format_abduction(report, explain=True)` renders the report.

The feature takes inspiration from [abductive logic programming](https://www.doc.ic.ac.uk/~rak/papers/abdsurv.pdf). KGodel's implementation is deliberately bounded search over its existing signed, function-free logic; it does not implement a full abductive language, integrity-constraint syntax, probabilistic diagnosis, or counterfactual belief replacement.

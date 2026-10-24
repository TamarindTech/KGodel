# KGodel 0.4: multi-step intentions

Version 0.4 extends the [0.3 planning specification](language-v0.3.md) with ordered operations, per-step requirements, and an in-memory commitment called an **intention**. Existing single-operation programs keep their behavior. Inference, explicit negation, hypothesis isolation, and goal ordering are unchanged.

## Syntax

```text
plan inspect_and_move(X, Y) for at(Y) priority 20 {
    when at(X), path(X, Y), unknown(clear(Y)).
    suppose(clear(Y)) {
        prove(can_move(X, Y)).
    }
    observe clear(Y).
    require at(X), path(X, Y), clear(Y).
    act move(X, Y).
}
```

The rule for `can_move` must be declared by the program. The plan body consists of:

1. One nonempty `when` conjunction, as before.
2. Zero or more `suppose` applicability blocks, as before.
3. One or more `act` or `observe` operations, each optionally preceded by one nonempty `require` conjunction.

Every operation and `require` conjunction ends with a period. `require` supports ordinary signed literals and `unknown(...)`, using the same syntax as `when`. A requirement belongs only to the immediately following operation. A dangling requirement, repeated `require` before an operation, empty sequence, or hypothesis inserted after the sequence starts is a source error.

All variables used anywhere in the plan must be declared as parameters. The target match and ordinary signed `when` guards must bind every variable used by any operation, requirement, unknown guard, or hypothetical check. A `require` clause cannot introduce variables or select new bindings. Bindings stay fixed for the entire intention. Observations update beliefs but do not return new variable bindings.

## Entry conditions and step requirements

`when` and `suppose` qualify a new commitment. They are evaluated only when selecting it. In particular, `unknown(clear(Y))` can become false after an observation without canceling the plan. A successful hypothetical check is not rerun after every operation and never supplies accepted evidence to a requirement.

Before the first operation, the selector also tests that operation's requirements against accepted knowledge. An unsupported first-step requirement produces a `requirements_failed` candidate; selection proceeds to other candidates. This check precedes hypothetical evaluation. Requirements on later operations are deferred until those operations are next.

Before every continuation, the runtime rebuilds inference from current base beliefs. A signed requirement must have status `true`. An `unknown(p)` requirement succeeds only when neither `p` nor `not p` has support. Explicit falsity and lack of evidence both fail a signed requirement. Derived support is recomputed, so a conclusion lost through belief revision cannot authorize a later step.

An operation without a `require` clause has no additional step conditions. KGodel does not infer action preconditions or treat entry guards as invariants. Authors must repeat conditions that need to hold before later operations. A requirement establishes current belief support, not objective truth: the world may still reject the operation and return corrective evidence.

## Commitment and reconsideration

Selection preserves the existing goal, priority, declaration, and binding order. Once selected, the agent commits to the sequence and fixed bindings. At most one intention is active. Newly applicable plans, even with higher priority or an earlier goal, do not preempt a continuing intention.

Each cycle executes at most one operation. The agent then accepts the returned observations and advances the cursor after success. Before the next operation:

- If the intention's goal is supported, discard its remaining operations and consider other unsatisfied goals.
- If the next step's requirements are unsupported, release the intention and select again against the revised knowledge.
- If the preceding operation failed, the intention has already been released; select again. Observations returned by a failed operation are still accepted.
- If all operations succeeded, the intention has completed. This alone does not establish its goal; the next cycle checks current knowledge.
- If reasoning fails or reaches a resource limit, stop with `reasoning_error`. Do not interpret the error as a false requirement or execute a fallback. An existing intention is retained unless it was already released before a later selection error.

An observation can succeed while reporting a negative literal. For example, observing a blocked bridge succeeds as an observation and returns `not clear(bridge)`; the following `require clear(bridge)` then releases the intention. This differs from an observation operation failing to return evidence.

Releasing an intention does not undo completed operations or retract their observations. Requirement checks and reconsideration consume no operation steps. An actual failed action or observation does consume a step.

## Retry suppression and resumption

Single-operation plans retain the 0.3 attempt key: signed base-belief fingerprint, goal, plan name, and fixed bindings at selection.

For a multi-step plan, the runtime additionally records this same instance at every belief state visited immediately before and after its operations, and when it is released. It cannot immediately restart its successful prefix at one of those states. The active intention bypasses selection and advances its own cursor, so these attempt records do not block continuation. After unrelated evidence creates a previously unvisited belief set, selecting that plan instance again is allowed. This is state-based loop suppression, not a permanent ban on retries or an exactly-once guarantee.

`agent.run(max_steps=N)` permits at most N further operations in that call; report counters and histories are cumulative for the session. If the budget ends midway through a sequence, the next `run` call on the **same Agent object** resumes at the next unfinished step. It rechecks current knowledge first. A zero budget performs no operations or selections; it can still recognize already-supported goals and release their intentions.

The cursor and attempt history are in memory only. There is no checkpoint loader, process-restart recovery, transactional rollback, concurrency, or durable external-tool execution in this version. Starting another CLI process starts a new agent and world from the source files. Saved trace JSON is a record, not a resumable checkpoint.

## Previews and records

`python -m kgodel deliberate PROGRAM` previews an initial selection without loading a world. Its structured candidate records add:

- `plan_step` and `total_steps`: one-based current step and sequence length.
- `sequence`: all grounded operations and their declared requirements; future requirements are not evaluated yet.
- `requirements`: current-step checks with the literal's truth `status` and a separate `supported` boolean. For `unknown(...)`, `status` is the underlying positive atom's truth status.
- `intention`: the existing intention ID for continuation, or null for a new selection.

`agent.deliberate()` also considers the live intention. It previews continuation, or a `released_intention` diagnostic followed by selection of a replacement. It neither releases nor commits an intention, records an attempt, changes histories or beliefs, nor invokes the world. Repeated previews at the same state are deterministic. Continuing an already-selected plan uses zero hypothetical contexts; a replacement selection gets its normal per-decision budget.

Runtime reports retain `decisions` and add:

- `active_intention`: ID, goal, plan, fixed bindings, next step, and total steps; null when none remains.
- `intention_events`: `committed`, `requirements_failed`, `operation_failed`, `goal_satisfied`, and `completed` records. IDs are monotonic within one agent session. `after_step` is the cumulative number of actual operations already performed. `next_step` identifies the pending/interrupted step, or null after completion. On operation failure it identifies the failed operation.
- Per-operation events include `intention`, `plan_step`, and `total_steps` alongside the existing decision reference and observation record.

The first operation's `because` evidence includes entry guards and its own requirements. A continuation's `because` contains fresh proofs for that step's requirements only. Entry and hypothetical evidence remains in the original selection decision; it is not relabeled as current evidence. The Python AST now stores `Plan.steps` as a tuple of `PlanStep` values. `Plan.operation` and `Plan.argument` remain read-only convenience properties for its first step; callers constructing the AST directly must supply `steps`.

## Worked experiment

```powershell
python -m kgodel check examples/multistep_route.kg
python -m kgodel deliberate examples/multistep_route.kg
python -m kgodel run examples/multistep_route.kg
```

The [program](../examples/multistep_route.kg) commits to a four-operation journey: inspect the intermediate destination, move there, inspect the goal, move to it. The bridge's hypothetical route qualifies, but its real observation reports a blockage. The movement requirement fails, releasing intention 1 without a movement attempt. Intention 2 uses the forest and completes all four operations. Total: three observations, two successful movements, and two commitments.

See the [readable trace](../output/multistep-route.trace.txt) and [structured trace](../output/multistep-route.trace.json).

To pause and continue in Python:

```python
from pathlib import Path
from kgodel.parser import parse
from kgodel.runtime import Agent, RouteWorld

source = Path("examples/multistep_route.kg")
agent = Agent(parse(source.read_text(encoding="utf-8")),
              RouteWorld.from_json(source.with_suffix(".world.json").read_text(encoding="utf-8")))
paused = agent.run(max_steps=3)
assert paused["active_intention"]["next_step"] == 3
preview = agent.deliberate()  # observe clear(goal), without performing it
finished = agent.run()
assert finished["status"] == "achieved"
assert finished["steps"] == 5
```

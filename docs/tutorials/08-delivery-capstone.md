# 8. Build an inspectable delivery agent

Prerequisites: lessons 2–6; Python is optional. You will combine a policy hierarchy, an explicit goal, hypothetical checks, real observations, saved progress, and missing-assumption search.

The complete source is [delivery.kg](../../examples/tutorials/delivery.kg), with [delivery.world.json](../../examples/tutorials/delivery.world.json). It is a route-simulator exercise: "delivery" means reaching `camp`, not calling a real delivery service.

## 1. Inspect the design

There are two possible routes: `depot → bridge → camp` and `depot → forest → camp`. The simulator knows the bridge is blocked. The agent's initial beliefs know paths and policy approval, but have no clearance evidence. Only the forest and camp have evidence that they are open.

The policy classes add conditions in layers:

| Class | Candidate condition |
| --- | --- |
| `RoutePolicy` | The agent is at the origin and knows a path to the destination |
| `ApprovedPolicy` | Parent condition plus `approved(To)` |
| `OpenPolicy` | Parent condition plus `open(To)` |

The `courier` instance uses `OpenPolicy` with `destination = camp`. Its inherited `mayMoveFrom:to:` sends through `self`, so all subclass restrictions apply, and also requires `clear(To)`. Its `finished` method checks the configured destination against position evidence.

```powershell
python -m kgodel check examples/tutorials/delivery.kg
python -m kgodel objects examples/tutorials/delivery.kg
python -m kgodel explain examples/tutorials/delivery.kg "[courier candidateFrom: depot to: forest]"
python -m kgodel query examples/tutorials/delivery.kg "[courier candidateFrom: depot to: bridge]"
```

The forest candidate is true; the bridge candidate is unknown because `open(bridge)` is missing. These commands read the program, not simulator reality. They do not discover the physical bridge blockage.

## 2. Explain what the bridge would need

```powershell
python -m kgodel abduce --program examples/tutorials/delivery.kg "[courier mayMoveFrom: depot to: bridge]" --assume "clear(bridge)" --assume "open(bridge)" --explain
```

The minimal explanation contains both assumptions. This is useful for identifying missing logical support. It does not certify that the bridge is safe: the simulator's actual blockage is not available to the pure query. Even a consistent hypothesis can be wrong about the world.

## 3. Qualify a plan hypothetically

The main plan contains:

```text
when [courier candidateFrom: From to: To], unknown(clear(To)).
suppose(clear(To)) { [courier mayMoveFrom: From to: To], open(To). }
observe clear(To).
require [courier mayMoveFrom: From to: To].
act move(From, To).
```

The hypothetical check asks whether successful clearance evidence would support the intended move. All plan variables are already bound. Its composed query must be true for the plan to qualify. Then the temporary clearance assumption is discarded, an actual observation is made, and the next operation is checked against accepted evidence.

This separation is central: a hypothetical proof qualifies a declared plan; it does not supply the observation needed to execute the move. The additional `move_known_clear` plan covers a destination whose clearance is already known.

```powershell
python -m kgodel deliberate examples/tutorials/delivery.kg
```

The next operation is `observe clear(forest)`. The preview shows the supporting policy proof and conditional assumption, with no action effects.

## 4. Execute and preserve progress

```powershell
python -m kgodel run examples/tutorials/delivery.kg --max-steps 1 --checkpoint output/tutorial-delivery/paused.json
python -m kgodel resume output/tutorial-delivery/paused.json --checkpoint output/tutorial-delivery/finished.json --trace-text output/tutorial-delivery/journey.txt
python -m kgodel compare output/tutorial-delivery/paused.json output/tutorial-delivery/finished.json --query "[courier finished]" --explain
```

The first invocation intentionally exits 1. The completed journey performs exactly four operations:

1. Observe clearance of the forest.
2. Move from depot to forest.
3. Observe clearance of camp.
4. Move from forest to camp.

The final position is `camp` and `[courier finished]` is true. The comparison shows unknown becoming true with movement evidence. The bridge is never visited. Because it is not observed, its clearance remains unknown in the accepted beliefs even though the simulator knows it is blocked.

## 5. Change the world, then explain the result

Copy the world to `output/tutorial-delivery/blocked-forest.world.json` and set `blocked` to `["bridge", "forest"]`. Leave the program unchanged, and run:

```powershell
python -m kgodel run examples/tutorials/delivery.kg --world output/tutorial-delivery/blocked-forest.world.json --checkpoint output/tutorial-delivery/stuck.json
```

The agent observes the forest blockage and becomes stuck at `depot` after one operation. Its move requirement is not supported. The bridge still lacks `open(bridge)`, so no declared plan can use it. The simulator does not invent new permission evidence.

Inspect the saved state:

```powershell
python -m kgodel shell --resume output/tutorial-delivery/stuck.json
```

```text
:explain not clear(forest)
:abduce [courier mayMoveFrom: depot to: forest] from (clear(forest))
:quit
```

The explanation for negative clearance cites the observation. The abductive candidate `clear(forest)` is excluded because it conflicts with that accepted evidence. Additive abduction cannot undo the observation.

## Exercise

In a copy of the original program, add `clear(forest).` to the initial facts. Use the original unblocked-forest world. Predict which plan executes first and the new total operation count.

<details>
<summary>Worked answer</summary>

The inspection plan cannot start for forest because its unknown guard fails. `move_known_clear` is selected and moves there directly. The agent then observes camp and moves into it: three operations total. A lower priority applicable plan is considered when a higher priority plan is inapplicable. Existing intentions are not preempted simply because another plan has a higher priority.

</details>

You now have an experiment in which a policy explains eligibility, a hypothesis exposes conditional support, actual evidence controls execution, and checkpoints preserve the reasoning history. Use the [command reference](../reference.md) and [feature guides](../README.md) when adapting it to your own research questions.

[← Python API](07-python-api.md) · [Course index](README.md) · [Documentation home](../README.md)

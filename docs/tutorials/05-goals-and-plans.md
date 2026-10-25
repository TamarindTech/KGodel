# 5. Goals, plans, and observations

Prerequisite: [facts and queries](02-logic-and-queries.md). This lesson turns a knowledge base into an agent that follows a declared plan. Use [first_route.kg](../../examples/tutorials/first_route.kg) and its [world file](../../examples/tutorials/first_route.world.json).

## Separate knowledge from the world

The program begins with `at(start).`, `path(start, goal).`, and `goal at(goal).`. The first two are beliefs; the goal is a condition the agent wants to support. The world file separately describes the simulated position, directed edges, and blocked locations:

```json
{
  "position": "start",
  "edges": [["start", "goal"]],
  "blocked": []
}
```

Writing `path(start, goal)` does not create a simulator edge. Likewise, an unblocked location in the world is not automatically known to be clear. The agent must observe it or receive an action outcome. This separation lets you study incomplete or outdated beliefs.

## Read the plan

The complete program has this plan inside its agent:

```text
plan inspect_and_move(From, To) for at(To) {
    when at(From), path(From, To), unknown(clear(To)).
    observe clear(To).
    require clear(To).
    act move(From, To).
}
```

1. The `for` target matches the goal, binding `To = goal`.
2. Signed entry guards find `From = start`. `unknown(clear(To))` checks that neither polarity is supported.
3. The agent commits to the plan with those fixed bindings, creating an intention.
4. `observe` obtains evidence about the destination.
5. `require` checks current evidence immediately before the following operation.
6. `act` requests a move. The outcome supplies new evidence about position.

`unknown(...)` is allowed in plan guards and requirements; it is not a general query operator. To ask about unknown support outside a plan, query the literal and inspect its status.

## Preview and step

```powershell
python -m kgodel deliberate examples/tutorials/first_route.kg
python -m kgodel shell examples/tutorials/first_route.kg
```

The preview selects an observation. Inside the shell:

```text
:preview
:step
:status
:explain clear(goal)
:preview
:step
:explain at(goal)
:quit
```

After the first step, the world position is still `start`. `clear(goal)` is true, and the active intention is waiting to perform its second operation. After the second step, the result is achieved and the position is `goal`. The completed run has one observation and one action. `at(start)` has been replaced by explicit negative evidence about the old position.

Entry guards are checked when choosing a new intention. They are not invariants: `unknown(clear(goal))` naturally stops holding after observation, but the active intention continues because its next requirement is satisfied. To impose a condition on a later operation, write `require` immediately before that operation.

## Observe a blocked path

Save this alternative world as `output/tutorial-blocked.world.json`, creating the `output` folder if needed:

```json
{
  "position": "start",
  "edges": [["start", "goal"]],
  "blocked": ["goal"]
}
```

```powershell
python -m kgodel run examples/tutorials/first_route.kg --world output/tutorial-blocked.world.json
```

The observation records `not clear(goal)`. The movement requirement fails; the agent releases the intention and becomes stuck at `start` after one observation and zero actions. Exit code 1 is expected. It does not repeatedly inspect the same blocked goal because the entry condition is no longer unknown.

`stuck` means no declared applicable untried plan was found in the current state. It is not a proof that no possible strategy exists.

## Choose among plans

Plans can have integer priorities from 0 through 1,000,000; higher priorities are considered first. Defaults are 0. New selections consider goals in declaration order, then plan priority, declaration order, and deterministic bindings. An existing intention keeps its commitment unless it completes, fails, loses a requirement, or its goal becomes satisfied.

The bundled `multistep-route` example has a blocked bridge and a usable forest route. `python -m kgodel demo multistep-route` performs five operations: inspect the bridge, inspect the forest, move to the forest, inspect the goal, and move to the goal. Its trace shows why the first intention was abandoned.

## Exercise

If a copy of the simple program starts with `clear(goal).`, its only plan cannot start because clearance is already known. Add a second plan that moves when clearance is known.

<details>
<summary>Worked answer</summary>

```text
plan move_known_clear(From, To) for at(To) {
    when at(From), path(From, To), clear(To).
    act move(From, To).
}
```

With `clear(goal).` added to the initial beliefs and the unblocked world, this plan reaches the goal in one action. In an actually blocked world, the attempted action can fail and revise the stale clearance belief. Logical support and simulator reality are distinct.

</details>

The runtime currently implements only `observe clear(Location)` and `act move(From, To)`. A logical predicate with another name does not automatically become an executable tool.

[← Objects](04-objects-and-messages.md) · [Course index](README.md) · [Next: persistence and comparison →](06-sessions-and-comparison.md)

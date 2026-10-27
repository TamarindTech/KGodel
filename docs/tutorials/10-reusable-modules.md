# 10. Build an agent from reusable modules

Prerequisites: [objects](04-objects-and-messages.md), [plans](05-goals-and-plans.md), and [comparisons](09-term-comparisons.md). This lesson needs KGodel **0.14.0a1**. It creates its own examples and works after a wheel installation without a checkout.

## Create and inspect a modular project

```sh
python -m kgodel init my-modular-agent --template modular
python -m kgodel imports my-modular-agent/agent.kg
python -m kgodel check my-modular-agent/agent.kg
```

The destination must be new. The starter contains an entry agent, a world, queries, a README, and three libraries:

| File | Responsibility |
| --- | --- |
| `agent.kg` | Selects the courier object, starting belief, and goal |
| `geography.kg` | Route facts, approved destinations, and recursive reachability |
| `policies.kg` | Base route policy and a subclass that requires approval |
| `travel.kg` | A reusable observe/check/move plan |

The dependency report lists four source files. The entry includes geography and travel; travel includes policies; policies also includes geography. Geography loads once. Includes are relative to their containing file, so the project can move as one directory.

Inspect [the starter's entry](../../kgodel/templates/modular/agent.kg) and [travel module](../../kgodel/templates/modular/travel.kg). The entry has one `agent` declaration, while each library has one `module`. A library cannot silently add a goal. All declarations otherwise share one namespace, so use distinct class, object, plan, and module names.

## Trace a decision through the libraries

```sh
python -m kgodel explain my-modular-agent/agent.kg --file my-modular-agent/queries.kgq
python -m kgodel deliberate my-modular-agent/agent.kg
```

The courier's candidate query returns `forest`. The base policy supplies the path; the subclass adds `approved(forest)`. Moving there is initially unknown because `clear(forest)` has not been observed. A temporary hypothesis can support the move, but the accepted knowledge remains unchanged afterward.

The reusable plan chooses to inspect the forest. Its `From \== To` condition excludes self-moves, and its requirement checks the policy again before moving. Module composition preserves the same proof and belief-revision behavior as a single-file program.

## Pause and resume the combined program

```sh
python -m kgodel run my-modular-agent/agent.kg --max-steps 1 --checkpoint paused.session.json
python -m kgodel resume paused.session.json --checkpoint done.session.json
python -m kgodel compare paused.session.json done.session.json --query "at(goal)" --explain
```

The first command observes the forest and pauses with exit code 1 because its goal is unfinished. Resume completes the trip in four total operations, including the earlier observation. The comparison shows `at(goal)` changing from unknown to true.

The checkpoint embeds the combined program. Moving the original project or editing one of its modules does not change this saved session. New CLI calls on `agent.kg` read the edited files; `resume` reads the saved program. Keep the distinction in mind when comparing experiments.

For a record of which sources you loaded:

```sh
python -m kgodel imports my-modular-agent/agent.kg --result-json dependencies.json
```

The JSON includes relative source paths and content hashes. Keep it alongside a trace if you need source provenance; it is not a resumable checkpoint or a signed release manifest.

## Exercise

Remove `approved(forest).` from a copy of geography and start a fresh run. Predict the result before running it. Would resuming the previously saved checkpoint use this change?

<details>
<summary>Worked answer</summary>

The fresh agent is stuck before performing any operation: neither the bridge nor the forest is an approved next destination. `resume paused.session.json` still uses the original embedded program and reaches the goal. Restore the approval fact to let fresh runs proceed again.

</details>

For path rules, limits, source errors, and `parse_file` / `load_project`, read the [module reference](../modules-v0.14.md).

[← Comparisons](09-term-comparisons.md) · [Course index](README.md) · [Documentation home](../README.md)

# 6. Save, resume, and compare

Prerequisite: [goals and plans](05-goals-and-plans.md). You will pause after observing a location, resume without repeating that observation, and inspect the difference between the two states.

## Save a deliberate pause

```powershell
python -m kgodel run examples/tutorials/first_route.kg --max-steps 1 --checkpoint output/tutorial-session/before.json --trace-json output/tutorial-session/before.trace.json
```

The invocation exits 1 because the goal is unfinished. The position is still `start`, clearance is known, and an intention is waiting at the movement operation. Parent directories for named outputs are created automatically.

Two different files were written:

| File | Purpose |
| --- | --- |
| `before.json` | A checkpoint containing the program, beliefs, proofs, world, histories, and intention cursor |
| `before.trace.json` | An execution report for inspection; not a resumable session |

The `schema_version` field of a new checkpoint is 5. KGodel 0.12 also reads schemas 1–4. The program and world are embedded, so reopening a checkpoint needs no original source files. Hand-editing checkpoints is unsupported.

## Inspect before continuing

```powershell
python -m kgodel shell --resume output/tutorial-session/before.json
```

Inside the shell:

```text
:status
:explain clear(goal)
:preview
:quit
```

Opening the shell and inspecting state performs no operations. The preview describes the pending move. This shell does not automatically overwrite its input checkpoint on exit.

## Resume into a new checkpoint

```powershell
python -m kgodel resume output/tutorial-session/before.json --checkpoint output/tutorial-session/after.json --trace-json output/tutorial-session/after.trace.json
python -m kgodel compare output/tutorial-session/before.json output/tutorial-session/after.json --query "at(goal)" --explain --result-json output/tutorial-session/comparison.json
```

The resumed run achieves the goal. Its cumulative trace contains two operations, not three: the saved observation is not replayed. The original `before.json` remains unchanged because the output uses a different path.

The comparison includes:

- Position changing from `start` to `goal`.
- `at(goal)` changing from unknown to true, with the action's evidence.
- The old position belief being revised.
- The active intention becoming absent.
- One shared operation in the history prefix, followed by the new movement.

Comparison itself does not execute actions. A complete comparison exits 0 even when state differs; `changed` is data, not an error. The JSON report includes proofs without requiring the terminal `--explain` option.

## Preserve checkpoints intentionally

To update the same saved session, explicitly pass it as `--checkpoint` while resuming. To keep an audit trail, use a new name. A normal `resume` without a checkpoint output changes only the in-memory agent for that process.

In the shell, `:checkpoint PATH` saves resumable state; `:save PATH` exports a trace. `:compare PATH` compares a saved baseline with the current live agent. There is no autosave. File paths with spaces can be quoted.

## Exercise

What happens if you resume `before.json` twice, writing `after.json` and `after-again.json` separately? Do the two processes share the same moving agent?

<details>
<summary>Worked answer</summary>

Each load creates an independent agent and world at the saved position. Each performs the pending move once. The two final states match, while the original checkpoint remains at the pause. Checkpoints describe local experiment state, not a shared external service or a record that an operation may never be performed in another simulation.

</details>

The [session reference](../sessions-v0.6.md) describes atomic writes and validation. The [comparison reference](../comparison-v0.7.md) explains proof changes, divergent histories, and partial reports when reasoning exceeds a limit.

[← Goals and plans](05-goals-and-plans.md) · [Course index](README.md) · [Next: the Python API →](07-python-api.md)

# KGodel 0.6: saved sessions

Historical format note: the schema-1 description below records version 0.6. KGodel 0.12 writes schema 5 and reads schemas 1–5, preserving objects, superclass proofs, and composed plan hypotheses. Loading/writing guarantees and APIs below still apply. See the [current persistence tutorial](tutorials/06-sessions-and-comparison.md) and [usage guide](using-kgodel.md).

A checkpoint is a snapshot of one agent and its local route simulator between execution calls. It can be opened in another process, without the original program or world files. Loading restores data and does not invoke `act`, `observe`, or `Agent.run`.

## Command-line use

```powershell
python -m kgodel demo --max-steps 3 --checkpoint journey.session.json
python -m kgodel shell --resume journey.session.json
```

The demo pauses after observing the bridge, inspecting the forest, and moving into the forest. In the reopened shell, `:status` reports the active plan's next step, `:trace` shows the prior operations, and `:preview` checks the next operation against the restored beliefs. `:run` continues with the observation of the goal location and the final movement.

For a noninteractive continuation:

```powershell
python -m kgodel resume journey.session.json --checkpoint finished.session.json --trace-json finished.trace.json
```

`--checkpoint` is available on `demo`, `run`, and `resume`. It saves after a run returns, including an unfinished, stuck, or reasoning-error result. A completed goal returns exit code 0; an unfinished run returns 1; input or file errors return 2. The checkpoint is still written when a run returns 1. No checkpoint is written if an input error prevents the run.

The shell command `:checkpoint PATH` also works before the first operation. Paths with spaces may be quoted. `:save` continues to export the last trace; a trace does not contain enough execution state to restart.

## Python API

```python
from kgodel.demos import load_demo
from kgodel.sessions import load_session, save_session

agent = load_demo("multistep-route")
agent.run(max_steps=3)
save_session(agent, "journey.session.json")

restored = load_session("journey.session.json")
print(restored.execution_record())  # Earlier cumulative trace; no operations.
print(restored.deliberate())        # Preview continuation; no operations.
result = restored.run(max_steps=50)
assert result["status"] == "achieved"
assert result["steps"] == 5
```

`dumps_session(agent)` returns JSON text; `loads_session(text)` returns a new independent `Agent`. `Agent.execution_record()` returns `None` before any run, otherwise a cumulative record using the last run's status and current state. It does not release an intention or record a decision. The shell exposes this record immediately after restoration.

Only the exact built-in `RouteWorld` class is supported. Custom adapters and subclasses are rejected rather than converted into a different environment. API-created programs must round-trip through the KGodel parser without changing their model, including generated rule names. Save between completed `run` calls, not from another thread while execution is in progress.

## Preserved state

| State | Restoration behavior |
| --- | --- |
| Program | Embedded canonical KGodel source, with original declaration order and logic. Source formatting and comments are not preserved. |
| Base beliefs | Signed facts with their evidence sources and proof premises. Derived conclusions are recomputed when reasoning resumes. |
| World | Current position, directed edges, blocked locations, known nodes, and operation counters. |
| Attempts | Previously tried goal/plan/binding instances indexed by belief state, preserving retry suppression. |
| Active intention | Goal, plan, fixed bindings, original selection evidence, attempt key, identifier, and next unfinished step. |
| History | Decisions, operations, revisions, and intention lifecycle events, with cumulative numbering. |
| Last outcome | Last run status and reason, including reasoning errors that remain available for diagnosis. |

Loading does not rerun plan entry guards or hypothetical checks to choose a replacement commitment. The next execution cycle uses the normal intention rules: check current requirements, release a failed continuation, or stop if the goal is supported. Loading or saving alone does not release an intention, even if its goal has become supported.

Operation and hypothesis budgets are per invocation and are **not stored**. A new `resume` defaults to 50 further operations and 64 hypothetical contexts per decision; shell queries use the new shell's configured budget. The checkpoint contains no interactive query transcript or temporary hypothetical contexts. Stored decision records can still contain the hypothetical evidence that supported past decisions.

## Format and validation

The format is UTF-8 JSON with `format: "kgodel-session"`, an integer `schema_version`, and informational `kgodel_version`. Version 0.6 wrote schema 1; current KGodel 0.12 writes schema 5 and reads schemas 1–5. Compatibility is decided by schema version. There is no automatic migration from unsupported schemas, and traces from earlier versions are not checkpoints.

Loading checks the embedded program, field types, ground beliefs, plan bindings, attempt keys, cursor bounds, operation references, intention lifecycle, and simulator counters. It rejects duplicate JSON keys, nonstandard numeric constants, invalid encoding, and files larger than 32 MiB. Proof nesting is bounded at 128. Failures produce `KGodelError`; filesystem failures use `OSError` and are reported cleanly by the CLI and shell.

Contradictory stored base beliefs are rejected. A contradiction derived from otherwise consistent base beliefs can be retained after a reasoning-error run, so `:beliefs` and `:trace` remain available. Restoration does not repair conflicts or reinterpret failed reasoning as success.

These files are experiment state, not authenticated evidence. Structural validation does not prove that a file's observations occurred. Hand-editing checkpoints is unsupported; edit program and world inputs to start a new experiment.

## Write and restart guarantees

Saving first builds and validates the complete snapshot. It writes a temporary file in the destination directory, flushes it, and atomically replaces the destination. A failed validation or replacement preserves the earlier file. This protects against partial JSON replacing a valid checkpoint; it is not a transaction spanning simulator execution and storage, nor a guarantee against every filesystem or power failure.

There is no autosave. `resume` leaves its input unchanged unless an output option names that file. To update it explicitly, use `--checkpoint` with the input path. Reopening the same older checkpoint deliberately branches the experiment from that earlier state.

Persistence currently concerns local simulation only. It does not provide crash recovery during a running operation or exactly-once execution of external actions. No external-tool adapter, network operation, or LLM integration is introduced by this version.

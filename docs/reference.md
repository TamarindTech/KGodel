# KGodel 0.14 developer preview command reference

[Documentation home](README.md) · [Tutorial course](tutorials/README.md) · [Troubleshooting](troubleshooting.md)

Use `python -m kgodel COMMAND ...`, or `kgodel COMMAND ...` when the installed console script is on PATH. `python -m kgodel --help` lists commands; append `--help` to any command for its accepted flags. File paths resolve from the current directory.

## Commands

| Command | Input | Behavior |
| --- | --- | --- |
| `init DIRECTORY [--template route\|logic\|modular]` | New directory with an existing parent | Create an editable starter, queries, and README; refuse existing destinations |
| `doctor [--json]` | Current Python environment | Inspect installation metadata and run a bundled simulation in memory |
| `imports PROGRAM [--result-json PATH]` | Entry `.kg` agent | Link and structurally validate local modules; report dependency paths, hashes, and sizes without inference |
| `check PROGRAM` | `.kg` program | Parse, validate, and compute initial logical closure |
| `query PROGRAM QUERY` | A query expression, optionally `?-` or `prove(...)` | Inspect initial knowledge, returning statuses or bindings |
| `explain PROGRAM QUERY` | Same as query | Include supporting/opposing proof trees |
| `objects PROGRAM` | `.kg` program | Inspect classes, inherited methods, instances, and slots |
| `deliberate PROGRAM` | Program with goals/plans | Preview selection from initial beliefs without loading a world |
| `run PROGRAM` | Program with a goal and compatible world | Start a fresh simulated agent and execute declared operations |
| `demo [NAME]` | Bundled experiment | Start a fresh packaged agent/world; default `multistep-route` |
| `shell PROGRAM` | Program/world | Open an interactive agent without advancing it |
| `shell --demo NAME` | Bundled experiment | Open an interactive packaged agent |
| `shell --resume SESSION` | Checkpoint | Inspect or continue saved state interactively |
| `resume SESSION` | Checkpoint | Execute further operations from saved state |
| `compare BEFORE AFTER` | Two checkpoints | Compare accepted/derived knowledge, proofs, intentions, histories, and world |
| `abduce --program PROGRAM QUERY` | Program and ground target | Find explanations from explicit candidate assumptions |
| `abduce --demo NAME QUERY` | Bundled initial state | Same search without executing the demo |
| `abduce --resume SESSION QUERY` | Saved current state | Same search without advancing or rewriting the checkpoint |

The five bundled names are `blocked-route`, `hypothesis-planning`, `multistep-route`, `object-routes`, and `super-routes`. `demo --list` lists them without execution.

`check`, `query`, `explain`, `objects`, and program-based `abduce` can use a pure knowledge base without goals or a world. Preview validates logical applicability, not the physical feasibility of an operation. `run` and the shell require a goal and a world whose simulator supports the program's operations.

## Input and output options

Command-line exports must use distinct paths and cannot overwrite input files, including aliases. `resume SESSION --checkpoint SESSION` is the explicit exception for continuing and replacing the same checkpoint. These checks run before agent execution. `doctor --json` prints diagnostics to stdout and writes no files; `init` writes only into a newly created folder.

All program-file commands resolve local includes with bounded loading (64 files, depth 16, 1 MiB per file, 8 MiB total). Export protection includes every loaded module. Read [module semantics](modules-v0.14.md) for relative paths, shared names, errors, and Python overrides. Query files are requests, not includable libraries.

- `query` and `explain` accept either a query argument or `--file REQUESTS.kgq`. Use `--result-json PATH` to save structured answers, proofs, and dependencies.
- `deliberate` accepts `--max-hypotheses N` and `--result-json PATH`.
- `run` and file-based `shell` accept `--world WORLD.json`. Otherwise `agent.kg` uses the sibling `agent.world.json`. Bundled and resumed sources cannot be given a replacement world.
- `run`, `demo`, and `resume` accept `--max-steps N` (default 50 further operations), `--max-hypotheses N` (default 64 contexts per decision), `--trace-json PATH`, `--trace-text PATH`, and `--checkpoint PATH`.
- `compare` accepts repeatable `--query "GROUND_LITERAL"`, `--explain`, `--result-json PATH`, `--max-facts N` (default 10000), and `--max-work N` (default 200000 per side).
- `abduce` accepts repeatable `--assume "GROUND_LITERAL"`, or `--file REQUEST.kga` instead of a query and candidates. It also accepts `--explain`, `--result-json PATH`, `--max-assumptions N` (default 3), `--max-contexts N` (256), `--max-solutions N` (20), `--max-facts N` (10000), and `--max-work N` (200000 per closure). At most 16 distinct candidates are accepted.
- `shell` accepts `--max-hypotheses N` (default 64 per query request or decision).

Named outputs can replace an existing file. Use separate output names for sources, worlds, traces, and checkpoints. Comparison and abduction explicitly reject result outputs that alias their inputs. New saves use checkpoint schema 5; older schemas 1–4 remain readable. Trace JSON is a report and cannot be resumed.

The plain `query`/`explain` CLI does not expose inference-budget flags; use `Agent.query` or `evaluate_queries` in Python to customize those limits. See [the Python tutorial](tutorials/07-python-api.md).

## Shell commands

At the `kgodel>` prompt, enter one complete request per line. Bare requests and `:query EXPRESSION` inspect current beliefs. `:explain EXPRESSION` also prints proofs. A temporary context must fit on that line, for example `suppose(clear(goal)) { clear(goal). }`.

| Request | Effect |
| --- | --- |
| `:preview` | Preview the next operation, continuation, or reconsideration |
| `:step [N]` | Perform at most N further operations; default 1 |
| `:run [N]` | Perform at most N further operations; default 50 |
| `:status` | Inspect goals, counters, and active intention |
| `:beliefs` | Inspect accepted base facts and sources |
| `:objects` | Inspect logical classes and instances |
| `:trace` | Show the last cumulative execution report |
| `:save PATH` | Write that report as JSON |
| `:checkpoint PATH` | Write resumable state, even before the first operation |
| `:compare PATH` | Compare a saved baseline with this live agent |
| `:abduce TARGET from (A, B)` | Search explicit assumptions with conditional proofs |
| `:help` / `:quit` | Show help / end the session |

Only `:step` and `:run` advance the simulator. Save commands write files without advancing it. Shell inspection is pure, although `:step 0` is a run call that may record status or release an already-satisfied intention. Sessions do not autosave. A fresh session needs a run record before `:trace` or `:save`; `:checkpoint` does not.

## Exit codes and report statuses

| Command family | Exit 0 | Exit 1 | Exit 2 |
| --- | --- | --- | --- |
| `init` | Project created | — | Existing destination, invalid arguments, or file error |
| `imports` | Sources linked and structurally valid | — | Input, source-limit, module, or file error |
| `doctor` | Installation and demo checks passed | Missing/different installed metadata | Demo or diagnostic failure |
| `check`, `objects` | Valid input | — | Input, file, or initial reasoning error |
| `query`, `explain` | Request evaluated, including false/unknown/no matches | Inconsistent hypothetical context | Input or inference error |
| `deliberate` | Selected or already achieved | Stuck | Input or reasoning error |
| `run`, `demo`, `resume` | Goals achieved | Unfinished, stuck, step limit, or a reported runtime reasoning error | Setup/input/file error |
| `compare` | Both sides resolved, changed or unchanged | Partial reasoning | Input/file error |
| `abduce` | Complete bounded search with at least one explanation | Partial search or complete search with no explanation | Input, baseline inconsistency, or initial inference error |

The shell normally exits 0 on `:quit` or end-of-input regardless of whether its goal was achieved; Ctrl+C exits 130. An argument-parser error also exits 2. Inspect JSON report statuses to distinguish logical answers from operational success. A `true` answer means supported by this knowledge; it does not certify external reality.

Ground query statuses are `true`, `false`, and `unknown`. Variable results are `answers` or `no_answers`. Execution results include `achieved`, `stuck`, `step_limit`, and `reasoning_error`. A partial abductive result is not an impossibility proof. Hypothesis conflicts stay isolated from accepted beliefs.

## Term comparison conditions

Ground term filters are `==`, `\==`, `@<`, `@=<`, `@>`, and `@>=`. They work in query expressions, rule/method bodies, plan guards, and requirements. Bind query variables in earlier literals; comparisons never assign values. They are distinct from the `compare` command, which compares agent snapshots. See [term comparison semantics](comparisons-v0.12.md).

## File formats

| Extension or content | Purpose |
| --- | --- |
| `.kg` | One entry `agent` or included `module`; facts/rules, optional objects and plans |
| `.kgq` | Period-separated queries and `suppose` blocks |
| `.kga` | One `GROUND_TARGET from (CANDIDATE, ...)` request |
| `.world.json` | Exactly `position`, directed `edges`, and `blocked` fields for the route simulator |
| Checkpoint JSON | `format: "kgodel-session"`, schema version, program, world, evidence, and progress |
| Trace/result JSON | Inspection output from execution, queries, abduction, or comparison |

Extensions help organize files but do not make arbitrary JSON interchangeable. Save text as UTF-8. Commands reading programs/worlds accept a UTF-8 byte-order mark.

# Using KGodel 0.14 developer preview

[Documentation home](README.md) · [Step-by-step tutorials](tutorials/README.md) · [Command reference](reference.md) · [Troubleshooting](troubleshooting.md)

KGodel has two entry points: `python -m kgodel` and, after installation, the `kgodel` console command. Both call the same interpreter and accept the same arguments. Python 3.10 or newer is required.

## Installation

For downloadable wheels, the offline kit, and creating a first project with `init`, see [the product preview guide](product-preview.md). The following commands install a source checkout. Run `python -m kgodel doctor` after installation to check the interpreter, package version, and bundled demo.

Use `init my-agent --template modular` to create a reusable multi-file agent. `imports my-agent/agent.kg` displays its sources; all program-file commands load the same includes. The [module guide](modules-v0.14.md) covers file limits and Python's `parse_file` / `load_project`. The existing `parse(source)` function remains a pure text parser.

Open a terminal in the repository root, which contains `pyproject.toml` and the `kgodel/` directory:

```powershell
python -m pip install .
python -m kgodel --version
python -m kgodel demo
```

This installs a copy of the current checkout. For development, use `python -m pip install -e .` instead: the installed module then reads this checkout, so later source edits are immediately available. Do not move or delete an editable checkout while you rely on its installation. After changing packaging metadata, reinstall it.

The package uses the standard [Python project metadata and console-script configuration](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/). It has no third-party runtime dependencies. Installation builds with setuptools; pip may download that build dependency. The [bundled data](https://setuptools.pypa.io/en/latest/userguide/datafiles.html) is included in the wheel, and the demos read it through [Python package resources](https://docs.python.org/3/library/importlib.resources.html).

KGodel is not published to PyPI. Install this checkout or a wheel you build from it, rather than assuming `pip install kgodel` identifies this project.

### A separate environment on Windows

These commands keep the development installation inside the project and do not require PowerShell script activation:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m kgodel demo
.\.venv\Scripts\python.exe -m kgodel shell --demo multistep-route
```

To run from a different directory, use the absolute path to that environment's Python, or activate the environment in your terminal. On macOS/Linux, the equivalent interpreter is `.venv/bin/python`.

### Troubleshooting module discovery

`No module named kgodel` means the selected Python cannot find this package. Check:

```powershell
python -c "import sys; print(sys.executable)"
python -m pip show kgodel
```

Use that same `python` to install the checkout. You can install by its full path from any folder, for example `python -m pip install "C:\path\to\KGodel"`. If that Python cannot write its normal installation directory, use a virtual environment, or a user installation with `python -m pip install --user "C:\path\to\KGodel"` outside a virtual environment.

Without installation, commands work only where Python can find the source package, normally the repository root. The `run`, `check`, `query`, `explain`, `deliberate`, and file-based `shell` commands also resolve user-supplied relative file paths against your current directory. Installing the module does not make a relative path such as `examples/multistep_route.kg` exist everywhere. Use a full program path or a bundled demo.

If `python -m kgodel` works but `kgodel` is not recognized, the console script's directory is not on PATH. The module command works without changing PATH.

## Bundled demos

```powershell
python -m kgodel demo --list
python -m kgodel demo blocked-route
python -m kgodel demo hypothesis-planning
python -m kgodel demo multistep-route
python -m kgodel demo object-routes
python -m kgodel demo super-routes
```

`demo` without a name uses `multistep-route`. Each invocation creates a fresh agent and world from packaged resources, independent of your working directory. The editable examples in the repository remain available for experimenting with source and world files.

Demos accept the existing run options:

```powershell
python -m kgodel demo --max-steps 3 --trace-json paused.trace.json
python -m kgodel demo --max-hypotheses 64 --trace-text journey.txt
```

Exit statuses match `run`: 0 for achieved goals, 1 for a completed invocation that did not achieve all goals, and 2 for input or file errors. A step limit is not proof of goal impossibility. `demo --list` is read-only and cannot be combined with a demo name or output files. Output paths are relative to your current directory unless absolute. Both `demo` and `run` also accept `--checkpoint PATH` to save a resumable session.

## Interactive sessions

```powershell
python -m kgodel shell --demo multistep-route
python -m kgodel shell examples/multistep_route.kg
python -m kgodel shell --resume session.json
```

Supply exactly one source: a program file, `--demo NAME`, or `--resume SESSION`. File-based sessions accept `--world PATH`; otherwise the companion `.world.json` file is loaded. `--world` cannot override a bundled demo or saved session. `--max-hypotheses N` sets the context budget for each query request or plan-selection decision, defaulting to 64.

Every request occupies one line. A hypothetical request can contain nested scopes and multiple proofs on that same line. Language predicates are entered normally; shell commands begin with `:` so predicates such as `run` remain usable as queries.

| Request | Behavior |
| --- | --- |
| `clear(forest).` | Query the current accepted beliefs. |
| `suppose(clear(goal)) { prove(clear(goal)). }` | Explore a temporary context without changing the agent. |
| `:query EXPRESSION` | Explicit form of a bare query. |
| `:explain EXPRESSION` | Include supporting proofs and assumption dependencies. |
| `:abduce GOAL from (A, B)` | Find minimal hypothetical assumptions with conditional proofs. |
| `:preview` | Preview the next operation, continuation, or reconsideration. |
| `:step [N]` | Execute at most N more operations, default 1. |
| `:run [N]` | Execute at most N more operations, default 50. |
| `:status` | Show current goal support, operation counts, and the intention cursor. |
| `:beliefs` | Show accepted base beliefs and their evidence sources. |
| `:objects` | Inspect classes, inherited methods, objects, and instance-variable values. |
| `:trace` | Show the last cumulative execution record. |
| `:save PATH` | Export that record as JSON. Paths containing spaces may be quoted. |
| `:checkpoint PATH` | Save a resumable agent and world, even before the first operation. |
| `:compare PATH` | Compare the named checkpoint with the live agent, without advancing it. |
| `:help` | Show the command reference. |
| `:quit` | Exit the session. |

Only `:step` and `:run` advance the simulator. Queries, previews, status, beliefs, and trace inspection do not change the agent. `:save` writes the named file, creating parent directories and replacing an existing file at that path. It does not advance the agent. A run record must exist before `:trace` or `:save`; use `:step` or `:run` first.

Operation budgets must be nonnegative integers. `:step 0` records a status check without performing operations. As with the Python API, a zero-budget run may release an intention whose goal is already supported. Budgets limit further operations, while trace counters remain cumulative across the session.

Invalid input prints a diagnostic and leaves the session open. If reasoning finds a contradiction, no further operation executes; `:beliefs` and `:trace` still help inspect the conflict. This shell does not provide arbitrary belief editing or conflict repair. An inconsistent hypothesis remains isolated from accepted beliefs.

`:quit` and end-of-input exit with code 0. Ctrl+C exits with code 130. Normal shell exit does not imply all agent goals were achieved; inspect `:status` or the last run result for that. On Windows, terminal end-of-input is usually Ctrl+Z followed by Enter; on macOS/Linux it is Ctrl+D.

Use `:checkpoint PATH` before exiting to save progress. It preserves the program, beliefs and proof sources, simulator state, intention cursor, attempt history, and cumulative execution records. It writes the named file without advancing the agent, replacing an existing checkpoint atomically. A resumed shell makes the previous execution record available to `:trace` and `:save` immediately.

## Continue a saved session

```powershell
python -m kgodel demo --max-steps 3 --checkpoint session.json
python -m kgodel resume session.json --checkpoint session.json --trace-json completed.trace.json
```

The pause command returns 1 because the goal is unfinished. `resume` loads the checkpoint and executes up to 50 further operations by default; use `--max-steps N` and `--max-hypotheses N` to set new budgets. Counters and history remain cumulative. All execution options accepted by `run` also work with `resume`.

`resume` leaves the input checkpoint unchanged unless you explicitly name it as an output. Use `--checkpoint session.json` to replace it with the new state, or choose a different path to retain the earlier state. For inspection before continuing, use `shell --resume session.json`; opening the shell performs no operations. Sessions do not autosave on exit.

Checkpoints are self-contained and need no original `.kg` or world file. A saved trace from `:save` or `--trace-json` cannot be resumed. Invalid, truncated, oversized, and unsupported checkpoint formats produce a diagnostic. Intention continuation follows the 0.4 semantics; current saves also preserve objects, superclass messages, and composed plan queries. Persistence currently supports only the built-in local route simulator. See [the session format and Python API](sessions-v0.6.md) for guarantees and [the persistence tutorial](tutorials/06-sessions-and-comparison.md) for a complete walkthrough.

## Compare evidence and progress

```powershell
python -m kgodel demo --max-steps 3 --checkpoint before.json
python -m kgodel resume before.json --checkpoint after.json
python -m kgodel compare before.json after.json --query "at(goal)" --explain --result-json comparison.json
```

The report compares base beliefs, derived conclusions, goal support, active intentions, histories, and the simulated world. `--query` accepts a ground literal and can be repeated, including an explicit negative literal such as `not clear(bridge)`. `--explain` prints proof trees for goals, requested queries, and changed derived conclusions. The JSON report contains those proofs even without `--explain`.

In the shell, `:compare PATH` uses the checkpoint as the baseline and the current agent as the comparison target. Paths containing spaces may be quoted. It uses the default inference budgets, leaves the live agent and its last trace unchanged, and saves no files. Use the command-line form for custom budgets, extra queries, or JSON export.

Comparison exits with 0 when both sides finish reasoning, whether or not state differs; 1 when a conflict or inference limit leaves a partial report; and 2 for invalid input or file errors. `--max-facts` and `--max-work` set nonnegative inference limits separately for each side, defaulting to 10000 facts and 200000 work units. A partial report retains base-belief and world differences while marking unresolved answers explicitly. It never treats an inference error as logical falsity.

The input checkpoints are read-only; an output path resolving to either input, including a hard link, is rejected. Existing comparison output files are replaced when explicitly named. Checkpoints with schemas 1–4 remain supported. New saves use schema 5, which also preserves term-comparison proof leaves. See [the comparison reference](comparison-v0.7.md) for proof-selection details and how histories from different scenarios are compared.

## Explore logical objects

```powershell
python -m kgodel objects examples/object_routes.kg
python -m kgodel explain examples/object_routes.kg "[cautious candidateFrom: start to: forest]"
python -m kgodel shell --demo object-routes
```

The file-based commands use the examples in the checkout. The bundled shell works from any directory after installation. Enter `:objects` to inspect the class hierarchy and configured instances. `[Receiver candidateFrom: start to: Place].` enumerates supported receiver/destination bindings; `:explain [cautious candidateFrom: start to: forest]` shows the method and accepted evidence supporting the answer.

Methods are pure logical queries. A known message without supporting or opposing evidence is unknown; a missing receiver or selector is an input error. The shell reports such errors and stays open. Methods may send messages to `self` or another declared object, and inherited `self` sends use subclass overrides. Only the existing `:step` and `:run` commands advance the simulator.

Use `:checkpoint PATH` at any pause point to retain the object program and active intention. `:compare PATH` can show changing message answers, and the CLI accepts message literals in `--query`. See [the object-language guide](objects-v0.8.md) for the syntax and current limits.

## Extend a parent policy

```powershell
python -m kgodel shell --demo super-routes
```

```text
:explain [cautious candidateFrom: start to: forest]
[cautious candidateFrom: start to: bridge].
:step
:checkpoint super-session.json
:run
```

Methods can send `[super selector]` to reuse the implementation above their defining class. The demo adds approval and open-route conditions through three classes. Its proof annotations, such as `^RoutePolicy`, identify where parent lookup starts. The bridge query is unknown because its open-route condition lacks evidence. The forest route succeeds after four simulator operations. See [superclass semantics, proof annotations, and checkpoint compatibility](super-v0.9.md).

## Combine Prolog-style queries

Use comma for joined conditions, semicolon for alternatives, and parentheses to group them. Comma binds more tightly. An anonymous `_` matches independently without adding a named binding:

```powershell
python -m kgodel query examples/prolog_family.kg "?- parent(alice, Parent), parent(Parent, Child)."
python -m kgodel query examples/prolog_family.kg "?- ancestor(alice, Person), (artist(Person); scientist(Person))."
python -m kgodel explain examples/prolog_family.kg --file examples/prolog_family.kgq
```

The same syntax works in shell queries, `:explain`, and `Agent.query`. Single-quoted constants and named underscore variables are supported. See the [Prolog feature guide](prolog-v0.11.md) for binding rules, proof output, limits, and saved-session compatibility.

## Compare bound values

Term filters are available inside queries and logical conditions: `parent(alice, Child), Child \== bob` keeps supported children whose names differ from Bob. `First @< Second` can choose one orientation of a pair. Both operands must already be bound; these tests do not assign variables. Try `python -m kgodel explain examples/tutorials/comparisons.kg --file examples/tutorials/comparisons.kgq` and follow the [comparison tutorial](tutorials/09-term-comparisons.md).

## Find hypothetical explanations

```powershell
python -m kgodel abduce --demo super-routes "[cautious mayMoveFrom: start to: bridge]" --assume "clear(bridge)" --assume "open(bridge)" --explain
```

Use `--program PATH` to inspect a source program without loading a world, or `--resume SESSION` to inspect saved current beliefs. `--file examples/route_abduction.kga` provides the query and candidates together. `--result-json PATH` exports proofs, conflicts, and search coverage.

In the shell:

```text
:abduce [cautious mayMoveFrom: start to: bridge] from (open(bridge), clear(bridge), clear(forest))
```

The result contains the minimal pair `clear(bridge), open(bridge)` and leaves accepted beliefs and any active intention unchanged. Searches are limited to explicit ground candidates. The CLI lets you set `--max-assumptions`, `--max-contexts`, `--max-solutions`, `--max-facts`, and `--max-work`. A partial report retains verified explanations and clearly reports the unfinished search. See [abduction semantics and examples](abduction-v0.10.md).

## Test a built distribution

```powershell
python -m unittest discover -s tests -v
python tools/verify_tutorials.py
python -m pip wheel . --no-deps --wheel-dir dist
python tools/verify_install.py dist
```

The verifier requires a wheel path or a directory containing exactly one KGodel wheel. It creates a fresh temporary environment, installs the local wheel without using a package index, and runs from a directory outside the repository. It checks that the imported package comes from the temporary environment, validates metadata and both command entry points, runs every bundled demo, steps a shell session, restores a checkpoint in separate processes, and compares saved and live states. The resumed trace must equal an uninterrupted run.

The normal test suite needs only Python's standard library. Wheel creation needs the declared setuptools build dependency. GitHub Actions checks Windows, Linux, and macOS using Python 3.10 and 3.13, and also validates the source package and offline kit. See [the release guide](releasing.md) for the complete build and distribution checks.

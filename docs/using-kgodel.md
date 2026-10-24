# Using KGodel 0.7

KGodel has two entry points: `python -m kgodel` and, after installation, the `kgodel` console command. Both call the same interpreter and accept the same arguments. Python 3.10 or newer is required.

## Installation

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
| `:preview` | Preview the next operation, continuation, or reconsideration. |
| `:step [N]` | Execute at most N more operations, default 1. |
| `:run [N]` | Execute at most N more operations, default 50. |
| `:status` | Show current goal support, operation counts, and the intention cursor. |
| `:beliefs` | Show accepted base beliefs and their evidence sources. |
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

Checkpoints are self-contained and need no original `.kg` or world file. A saved trace from `:save` or `--trace-json` cannot be resumed. Invalid, truncated, oversized, and unsupported checkpoint formats produce a diagnostic. The language and intention semantics remain those of 0.4; persistence currently supports only the built-in local route simulator. See [the session format and Python API](sessions-v0.6.md) for precise guarantees and limits.

## Compare evidence and progress

```powershell
python -m kgodel demo --max-steps 3 --checkpoint before.json
python -m kgodel resume before.json --checkpoint after.json
python -m kgodel compare before.json after.json --query "at(goal)" --explain --result-json comparison.json
```

The report compares base beliefs, derived conclusions, goal support, active intentions, histories, and the simulated world. `--query` accepts a ground literal and can be repeated, including an explicit negative literal such as `not clear(bridge)`. `--explain` prints proof trees for goals, requested queries, and changed derived conclusions. The JSON report contains those proofs even without `--explain`.

In the shell, `:compare PATH` uses the checkpoint as the baseline and the current agent as the comparison target. Paths containing spaces may be quoted. It uses the default inference budgets, leaves the live agent and its last trace unchanged, and saves no files. Use the command-line form for custom budgets, extra queries, or JSON export.

Comparison exits with 0 when both sides finish reasoning, whether or not state differs; 1 when a conflict or inference limit leaves a partial report; and 2 for invalid input or file errors. `--max-facts` and `--max-work` set nonnegative inference limits separately for each side, defaulting to 10000 facts and 200000 work units. A partial report retains base-belief and world differences while marking unresolved answers explicitly. It never treats an inference error as logical falsity.

The input checkpoints are read-only; an output path resolving to either input, including a hard link, is rejected. Existing comparison output files are replaced when explicitly named. Schema-1 checkpoints from KGodel 0.6 remain supported. See [the comparison reference](comparison-v0.7.md) for proof-selection details and how histories from different scenarios are compared.

## Test a built distribution

```powershell
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir dist
python tools/verify_install.py dist
```

The verifier requires a wheel path or a directory containing exactly one KGodel wheel. It creates a fresh temporary environment, installs the local wheel without using a package index, and runs from a directory outside the repository. It checks that the imported package comes from the temporary environment, validates metadata and both command entry points, runs every bundled demo, steps a shell session, restores a checkpoint in separate processes, and compares saved and live states. The resumed trace must equal an uninterrupted run.

The normal test suite needs only Python's standard library. Wheel creation needs the declared setuptools build dependency. GitHub Actions is configured to perform both checks on Windows and Linux using Python 3.10 and 3.13.

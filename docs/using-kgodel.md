# Using KGodel 0.5

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

Exit statuses match `run`: 0 for achieved goals, 1 for a completed invocation that did not achieve all goals, and 2 for input or file errors. A step limit is not proof of goal impossibility. `demo --list` is read-only and cannot be combined with a demo name or trace output. Trace paths are relative to your current directory unless absolute.

## Interactive sessions

```powershell
python -m kgodel shell --demo multistep-route
python -m kgodel shell examples/multistep_route.kg
```

Supply exactly one source: a program file or `--demo NAME`. File-based sessions accept `--world PATH`; otherwise the companion `.world.json` file is loaded. `--world` cannot override a bundled demo. `--max-hypotheses N` sets the context budget for each query request or plan-selection decision, defaulting to 64.

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
| `:help` | Show the command reference. |
| `:quit` | Exit the session. |

Only `:step` and `:run` advance the simulator. Queries, previews, status, beliefs, and trace inspection do not change the agent. `:save` writes the named file, creating parent directories and replacing an existing file at that path. It does not advance the agent. A run record must exist before `:trace` or `:save`; use `:step` or `:run` first.

Operation budgets must be nonnegative integers. `:step 0` records a status check without performing operations. As with the Python API, a zero-budget run may release an intention whose goal is already supported. Budgets limit further operations, while trace counters remain cumulative across the session.

Invalid input prints a diagnostic and leaves the session open. If reasoning finds a contradiction, no further operation executes; `:beliefs` and `:trace` still help inspect the conflict. This shell does not provide arbitrary belief editing or conflict repair. An inconsistent hypothesis remains isolated from accepted beliefs.

`:quit` and end-of-input exit with code 0. Ctrl+C exits with code 130. Normal shell exit does not imply all agent goals were achieved; inspect `:status` or the last run result for that. On Windows, terminal end-of-input is usually Ctrl+Z followed by Enter; on macOS/Linux it is Ctrl+D.

The session, intention cursor, and attempt history are in memory. Exiting and starting again creates a new agent. Saved traces are records, not restart checkpoints. No persistent or real-world tool execution is introduced in this version; the language and intention semantics remain those of 0.4.

## Test a built distribution

```powershell
python -m unittest discover -s tests -v
python -m pip wheel . --no-deps --wheel-dir dist
python tools/verify_install.py dist
```

The verifier requires a wheel path or a directory containing exactly one KGodel wheel. It creates a fresh temporary environment, installs the local wheel without using a package index, and runs from a directory outside the repository. It checks that the imported package comes from the temporary environment, validates metadata and both command entry points, runs every bundled demo, then steps and resumes a shell session and exports its trace.

The normal test suite needs only Python's standard library. Wheel creation needs the declared setuptools build dependency. GitHub Actions is configured to perform both checks on Windows and Linux using Python 3.10 and 3.13.

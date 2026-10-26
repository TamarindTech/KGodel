# KGodel developer preview

[Documentation home](README.md) · [Tutorials](tutorials/README.md) · [Release guide](releasing.md)

KGodel **0.13.0a1** is an alpha preview for developers, educators, and researchers exploring explainable agent reasoning. Its workflow is: describe a small world, query its knowledge, inspect a proposed decision, run a simulated agent, and review or resume its reasoning later.

## What you receive

- A Python wheel with the command-line tool and Python modules, with no runtime dependencies.
- Five packaged demos and two starter project templates.
- A source distribution and starter kit containing examples, nine tutorials, references, and tests.
- SHA-256 checksums for the three downloads and a machine-readable release manifest.

This preview is a local developer tool. The route simulator supports `clear` observations and `move` actions. It has no graphical UI, hosted account, LLM connection, arbitrary tool execution, billing, or telemetry. Pure logic queries can model other domains without using the simulator. The language remains a function-free Prolog-inspired subset with read-only Smalltalk-style logical objects.

## Install a release download

Download a wheel or starter kit from a **published** [GitHub prerelease](https://github.com/TamarindTech/KGodel/releases). A draft is visible only to repository users with the required access. If no published release is listed, install the source checkout using [the usage guide](using-kgodel.md). Do not assume that `pip install kgodel` resolves to this project: PyPI publication is a separate step.

Create an environment and install the downloaded wheel on Windows:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --no-index --no-deps ./kgodel-0.13.0a1-py3-none-any.whl
.venv\Scripts\python -m kgodel doctor
```

On macOS or Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps ./kgodel-0.13.0a1-py3-none-any.whl
.venv/bin/python -m kgodel doctor
```

Python 3.10+ and its venv/pip tools must already be available. The wheel installs offline. The starter kit's `START_HERE.md` uses the wheel bundled in its `wheels/` folder.

Below, `python` means that environment's interpreter. Activate it or keep using its full path above. `doctor` displays the interpreter and package location, checks the installed version, and runs one self-contained simulation in memory. It performs no external actions or network requests. A source checkout shadowing an older installation produces a warning; running outside the checkout helps diagnose that mismatch.

## First project in five minutes

```sh
python -m kgodel init my-agent
python -m kgodel check my-agent/agent.kg
python -m kgodel explain my-agent/agent.kg --file my-agent/queries.kgq
python -m kgodel run my-agent/agent.kg --trace-json my-agent/run.trace.json
python -m kgodel shell my-agent/agent.kg
```

The run should finish with `Result: achieved`. Open `my-agent/README.md` to understand its program and world. In the shell, try `:preview`, `:step`, and `:run`. `:checkpoint my-agent/paused.session.json` saves the agent; `:quit` exits. Shell paths are relative to the terminal's current folder. Resume with `python -m kgodel resume my-agent/paused.session.json`.

For a pure logic project:

```sh
python -m kgodel init my-knowledge --template logic
python -m kgodel explain my-knowledge/agent.kg --file my-knowledge/queries.kgq
```

The destination must be a new folder whose parent already exists. `init` refuses existing files, folders, and links. The logic starter teaches recursion, comparisons, and hypothetical queries. It has no agent goal or simulated world, so use query commands instead of `run` or the agent shell.

## Compatibility and limits

This preview retains schema-5 saves and reads checkpoint schemas 1–5. Copy important checkpoints before trying a new version. A trace export is not a resumable checkpoint. Queries inspect beliefs rather than certify external truth; unknown is different from false. Resource-limit failures are reported instead of being treated as logical false.

Syntax and Python APIs may change during the 0.x series. Pin the exact version for repeatable experiments and consult the changelog before upgrading. There is no stable 1.0 API commitment yet. Checkpoints contain their program, beliefs, and history. Bounds on inference are not an operating-system sandbox for untrusted workloads.

Command-line exports reject input-file aliases and duplicate output destinations before execution. `resume FILE --checkpoint FILE` intentionally permits replacing that checkpoint with updated state. Interactive shell save paths are explicit user choices; choose dedicated output names there.

## Report feedback

Use [GitHub issues](https://github.com/TamarindTech/KGodel/issues), including a minimal example and expected/actual result. `python -m kgodel doctor --json` helps identify the installed package; review personal paths before sharing it. Support is best effort. Start the [tutorial course](tutorials/README.md) after your first project, or read the [command reference](reference.md).

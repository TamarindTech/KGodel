# 1. Install and ask your first question

By the end, you will run a query, recognize a proof, and explore a simulated agent. You need Python 3.10 or newer and a checkout of KGodel 0.12. No API key is required.

## Install the checkout

If you already have the repository, open a terminal in its root. Otherwise obtain it first:

```powershell
git clone https://github.com/TamarindTech/KGodel.git
cd KGodel
```

Install into the same Python you will use throughout the course:

```powershell
python --version
python -m pip install -e .
python -m kgodel --version
```

The final command should print `KGodel 0.12.0`. An editable installation reads this checkout as you change it. Keep the checkout in place. KGodel is not published to PyPI; these commands install this repository.

To use an isolated environment on Windows without activating a script:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m kgodel --version
```

For every later `python` command, substitute `.\.venv\Scripts\python.exe` if you chose that option. On macOS/Linux use `.venv/bin/python`. This avoids depending on PATH or PowerShell activation settings. The first installation may download the build dependency, setuptools; the interpreter has no third-party runtime dependencies.

## Ask a question

```powershell
python -m kgodel check examples/tutorials/library.kg
python -m kgodel query examples/tutorials/library.kg "recommended(alice, Book)"
```

The check reports a valid `library` agent. The query returns:

```text
Book = "Logic for Agents"
```

`Book` is a variable. KGodel found a value supported by the library's facts and rules. To see the evidence:

```powershell
python -m kgodel explain examples/tutorials/library.kg "recommended(alice, Book)"
```

Below the answer, the proof shows Alice's interest in logic, the book's topic, and its availability. The command loads no world and executes no action. A logical knowledge base does not need a goal.

## Meet a live agent

```powershell
python -m kgodel shell --demo multistep-route
```

At the `kgodel>` prompt, enter one request per line:

```text
:status
:preview
:step
:explain not clear(bridge)
:quit
```

The preview describes an observation of the bridge but does not perform it. `:step` performs that observation. The next query is supported by evidence that the bridge is blocked. `:quit` ends the session; this first exercise does not save it.

Terminal commands start KGodel. Once inside its shell, enter KGodel queries or colon-prefixed commands. `:help` lists them. `python -m kgodel demo --list` belongs in the terminal, not inside the KGodel shell.

## Exercise

Ask whether `'Field Notes'` is available. Predict whether the answer is true, false, or unknown before running it.

<details>
<summary>Worked answer</summary>

```powershell
python -m kgodel query examples/tutorials/library.kg "available('Field Notes')"
```

The answer is `unknown`. The knowledge base contains neither positive nor negative availability evidence for that book. Unknown does not mean unavailable.

</details>

If the module cannot be found, check `python -m pip show kgodel` and the selected interpreter. If an example cannot be found, check your working directory. The [troubleshooting guide](../troubleshooting.md) covers both cases.

[Course index](README.md) · [Next: facts and queries →](02-logic-and-queries.md)

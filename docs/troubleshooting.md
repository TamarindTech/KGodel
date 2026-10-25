# Troubleshooting KGodel 0.12

[Documentation home](README.md) · [Command reference](reference.md) · [Tutorial course](tutorials/README.md)

## `No module named kgodel`

Check the interpreter and its package installation:

```powershell
python -c "import sys; print(sys.executable)"
python -m pip show kgodel
```

From the checkout root, install with that same interpreter: `python -m pip install -e .`. In a virtual environment, use its Python for installation and execution. Installing with a different Python does not make the package available to this one. After installation, `python -m kgodel --version` should show 0.12.0 for this documentation.

If only the `kgodel` console command is missing, use `python -m kgodel`; the script directory need not be on PATH. Do not assume `pip install kgodel` from PyPI identifies this project.

## A source or world file cannot be found

Relative paths start at the terminal's current directory. Run tutorial commands from the repository root or supply full file paths. Installing KGodel does not copy `examples/tutorials` into every working directory or into the wheel.

`run agent.kg` and `shell agent.kg` look for `agent.world.json` beside the program. Use `--world PATH` for another world. A bundled `demo` or `shell --demo NAME` includes its inputs; a checkpoint includes its original program and world.

## The answer is unknown, but I expected false

KGodel requires explicit opposing evidence for falsity. `not available(book)` must be supplied or derived before `available(book)` is false. Absence of a proof is unknown. `not` does not mean "try and fail to prove." `unknown(...)` is a plan guard, not a general query operator.

Use `explain` or `:explain` and check each condition of the relevant rule. A variable query with no supported bindings also does not prove falsity for every possible value.

## A query returned fewer or different bindings

Repeated named variables must agree. Every `_` is independent; `_Name` is not anonymous. Comma binds more tightly than semicolon, so add parentheses when joining an alternative. A period starts another request with independent bindings.

Answers are distinct binding dictionaries, not every possible proof path. An alternative using different variable names may return partial dictionaries. Quoted constants are case-sensitive, and `'Mary Jane'` differs from `mary_jane`.

## `Every rule-head variable must occur in the rule body`

A rule cannot invent an arbitrary value for its head. In `related(X, Y) :- known(X).`, nothing supplies `Y`. Add a supported body condition that binds it or change the head. Initial facts and goals must be ground. Anonymous `_` is allowed in rule bodies but not heads or persisted facts.

All named plan variables must be declared, and variables needed by operations, unknown guards, or hypothetical checks must be bound by the goal or signed entry guards. `_` cannot stand in for an operation argument; the runtime needs a concrete value.

## A term comparison reports an unbound variable

First match the value with a signed literal, for example `parent(alice, Child), Child \== bob`. `Child == bob` alone is a test with a missing input, not an assignment. Every incoming branch must bind the variables used by a later test. `_` cannot be compared; use a bound named variable. In rules and methods, comparison variables must occur in a signed body literal. Terms are strings, so ordering is lexical rather than arithmetic. See the [comparison tutorial](tutorials/09-term-comparisons.md).

## An object message is invalid or unexpectedly unsupported

Use `objects PROGRAM` or shell `:objects` to check spelling, slots, selectors, and inherited owners. `[curated recommends: Book]` is a message; `recommends(curated, Book)` is a different predicate. Each keyword argument requires a corresponding selector colon.

A missing receiver or selector is an input error. A valid message without support is unknown. Inherited `self` sends use subclass overrides. A `super` send must appear inside a method with a suitable superclass implementation. Proof labels such as `^Catalog` are not syntax to copy into ordinary queries.

## The agent is stuck or a step limit was reached

Use `:status`, `:preview`, `:beliefs`, and `:trace` to locate the missing condition. Check the plan target, entry guards, hypotheses, requirements, and previous attempts. An unknown entry guard stops matching when a fact becomes known; add a separate plan for the known case if needed.

An active intention continues with fixed bindings and checks its next `require` conditions. New high-priority plans do not automatically preempt it. If a requirement or operation fails, the remaining steps are abandoned. The same plan instance is not immediately retried against the same accepted state.

`--max-steps` counts further operations, not logical rule applications. A pause returning exit code 1 can be intentional. Resume from a checkpoint, or continue the same shell/Agent. A fresh `run` starts over. `stuck` and `step_limit` are not proofs of general impossibility.

## A hypothetical or abductive result did not change behavior

Those requests are pure. They show what follows under temporary evidence and leave accepted state unchanged. Plans can use hypotheses to qualify a choice, but still need actual evidence for later requirements. Abduction does not synthesize or execute a plan.

Hypotheses add evidence and cannot replace an opposing belief. An inconsistent scope returns no answers. Abduction excludes directly contradicted candidates and reports conflicting combinations. To study a different starting state, edit a copy of the program/world and start a new experiment.

## A search is partial or exceeds a limit

Inspect the stopping reason before changing budgets. Abduction is bounded by candidate count, assumption-set size, contexts, solutions, and per-context inference. Increasing a budget can explore more combinations but does not guarantee useful answers. No candidate outside the supplied set is invented.

Query composition is limited to 256 literal or comparison conditions, 32 nested operator nodes, and fewer than 64 nested grouping parentheses. Hypothesis nesting is limited separately. Resource errors must not be interpreted as false statements or as complete search results.

## `Route simulator does not support ...`

The current runtime only supports `observe clear(Location)` and `act move(From, To)`. Adding a predicate or logical method does not register a tool. A query-only program may omit goals and worlds, but an `Agent` or file-based shell requires both a goal and compatible world.

For the world, use exactly `position`, `edges`, and `blocked`; edges are directed pairs of strings, and blocked locations must occur among its nodes. A belief in a path does not add an actual edge.

## A saved file will not resume, or recent work disappeared

Only checkpoints from `--checkpoint` or `:checkpoint` are resumable. Trace/result exports are different formats. New checkpoints use schema 5; KGodel 0.12 reads schemas 1–5. An older interpreter cannot read schema 5. Invalid, oversized, or truncated files are rejected; do not repair them by guessing field values.

Sessions do not autosave. `resume` leaves its input unchanged unless you explicitly select it as the new checkpoint output. Save to a new filename when you want to preserve the earlier state. A resumed `run` performs more operations; `shell --resume` opens the state for inspection first.

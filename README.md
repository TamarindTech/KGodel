<p align="center">
  <img src="docs/assets/kgodel-logo-transparent.svg" alt="KGödel — Agentic Logic Programming" width="640">
</p>

# KGodel 0.6

**An experimental logic language for agents that can revise their beliefs and explain their decisions.**

New to KGodel? Read the [introduction for developers and non-developers](docs/introduction.md).

KGodel combines a small Prolog-inspired syntax with explicit goals, guarded plans, observations, and actions. This working prototype explores the reasoning cycle in a finite simulated world.

KGodel supports **hypothetical reasoning**: `suppose` creates a temporary belief context, answers queries within it, and labels the assumptions behind each proof. Plans use hypothetical checks and priorities to choose their next commitment. **Multi-step intentions** let agents follow a sequence, check each step's declared requirements against current evidence, and reconsider when a requirement or operation fails. Version 0.6 adds saved sessions: close the interpreter and later continue with the same beliefs, simulator state, and unfinished intention.

The first experiment starts with an outdated belief that a bridge is clear. The agent tries the bridge, discovers the blockage, retracts its old belief, checks a forest route, and reaches its destination. Its decision record preserves the evidence used before each action and the observations returned afterward.

## Install and try a demo

Requires Python 3.10 or newer. There are no third-party runtime dependencies or API keys. From the root of this repository, install KGodel into the Python environment you want to use:

```powershell
python -m pip install .
python -m kgodel demo
```

After installation, `python -m kgodel` works from any folder when using that same Python environment. The installed `kgodel` command is also available when that environment's Scripts/bin directory is on your PATH. For active development, use `python -m pip install -e .` so source edits take effect immediately. KGodel has not been published to PyPI; these instructions install this local checkout.

The default demo is the multi-step route. List or choose a bundled experiment:

```powershell
python -m kgodel demo --list
python -m kgodel demo blocked-route
python -m kgodel demo hypothesis-planning
python -m kgodel demo multistep-route
```

Demos include their programs and simulated worlds, so they need no relative file paths. You can still run directly from the source folder without installing:

```powershell
python -m kgodel run examples/blocked_route.kg
```

The companion `examples/blocked_route.world.json` supplies the environment. The expected sequence is:

1. Attempt `move(start, bridge)`; the simulator reports a blockage.
2. Replace `clear(bridge)` with `not clear(bridge)`.
3. Observe that `forest` is clear, then move there.
4. Observe that `goal` is clear, then move there.
5. Report `achieved`, with the final location confirmed by the simulator.

There are five plan executions: one failed movement, two observations, and two successful movements. The completed run is saved in [the readable trace](output/blocked-route.trace.txt) and [the structured trace](output/blocked-route.trace.json).

If you see **`No module named kgodel`**, either run from the repository root (the folder containing `kgodel/`) or install the checkout using the same `python` you use to run it. Installation in one virtual environment does not install it into other Python environments. See the [installation and shell guide](docs/using-kgodel.md) for Windows setup and troubleshooting.

## Explore a live agent

Start a session with a bundled demo:

```powershell
python -m kgodel shell --demo multistep-route
```

Enter these requests at the `kgodel>` prompt, one line at a time:

```text
:preview
:step
clear(bridge).
:step 2
:explain at(forest)
suppose(clear(goal)) { prove(clear(goal)). }
:status
:run
:save session.trace.json
:quit
```

The first step observes the blocked bridge; the next two operations inspect the forest and move there. Queries use the agent's current beliefs and do not advance it. `:preview` explains the next decision. `:step` and `:run` continue the same agent and its active intention, preserving earlier observations. `:help` lists all commands, including `:beliefs` and `:trace`.

To use your own program, run `python -m kgodel shell path/to/agent.kg`. Its companion world is loaded by default, or supply `--world PATH`. `:save` exports a cumulative trace. Use `:checkpoint session.json` to save a resumable session before exiting.

## Save and continue later

```powershell
python -m kgodel demo --max-steps 3 --checkpoint session.json
python -m kgodel shell --resume session.json
```

The first command pauses in the forest, with two operations still to perform, and returns exit code 1 because the goal is unfinished. The second opens that saved agent for inspection: use `:preview`, `:trace`, or `:run`. Previous operations are not repeated.

To continue directly and save the resulting state:

```powershell
python -m kgodel resume session.json --checkpoint session.json
```

Checkpoints contain the program, current beliefs and their sources, world, attempt history, execution records, and active intention. The original program and world files are not needed to resume. Saving replaces the specified file atomically; resuming only writes a new checkpoint when `--checkpoint` is supplied. Budgets apply to each new invocation and are not stored. See [saved-session semantics and the Python API](docs/sessions-v0.6.md).

## The language

```text
agent explorer {
    belief at(start).
    belief path(start, goal).

    rule can_move(X, Y) :- at(X), path(X, Y), clear(Y).

    goal at(goal).

    plan inspect(X, Y) for at(Y) {
        when at(X), path(X, Y), unknown(clear(Y)).
        observe clear(Y).
    }

    plan travel(X, Y) for at(Y) {
        when can_move(X, Y).
        act move(X, Y).
    }
}
```

- `belief` supplies a ground statement accepted at startup.
- `rule` derives a conclusion from a conjunction of supported statements.
- `goal` names a condition the agent wants its beliefs to support.
- `plan` matches a goal, checks entry guards, then commits to one or more operations.
- `require` checks current evidence before the immediately following operation.
- `observe` asks the environment for evidence.
- `act` asks the environment to perform an action; its outcome supplies evidence.
- `not clear(bridge)` is explicit negative evidence.
- `unknown(clear(bridge))` succeeds only when neither polarity is supported.

Names beginning with uppercase letters are variables. Lowercase names and double-quoted strings are constants. `%` and `//` introduce line comments. KGodel is a function-free subset: it does not implement full Prolog.

## Query and explain

These commands inspect the program's **initial** knowledge. They do not run plans or contact the simulator.

```powershell
python -m kgodel check examples/blocked_route.kg
python -m kgodel query examples/blocked_route.kg "reachable(start, Destination)"
python -m kgodel query examples/blocked_route.kg "clear(forest)"
python -m kgodel explain examples/blocked_route.kg "can_move(start, bridge)"
```

The forest query returns `unknown`. The explanation for moving to the bridge traces back to the outdated initial belief. That is an explanation of what the agent believed, not a claim about the simulator's reality.

To preserve a fresh execution record:

```powershell
python -m kgodel run examples/blocked_route.kg --trace-text output/blocked-route.trace.txt --trace-json output/blocked-route.trace.json
```

The JSON contains the full nested proof supporting each guard, substitutions, observations, belief revisions, and final goal proofs. The text trace presents a shorter summary.

## Explore a hypothesis

Ask whether movement would be supported if the forest were clear:

```text
prove(can_move(start, forest)).

suppose(clear(forest)) {
    prove(can_move(start, forest)).
}

prove(can_move(start, forest)).
```

The answers are **unknown, true within the hypothesis, unknown again**. The conditional proof identifies `clear(forest)` as an assumption. The agent neither learns that the forest is clear nor performs a movement.

Run the example, which also demonstrates a nested hypothesis:

```powershell
python -m kgodel explain examples/blocked_route.kg --file examples/forest_hypothesis.kgq
```

Use `query` for shorter output or append `--result-json output/forest-hypothesis.results.json` to save the structured results. The saved [readable example](output/forest-hypothesis.results.txt) and [structured results](output/forest-hypothesis.results.json) include conditional proofs and their assumption dependencies. A single query can also be passed directly:

```powershell
python -m kgodel query examples/blocked_route.kg "suppose(clear(forest)) { prove(can_move(start, forest)). }"
```

An assumption that conflicts with accepted evidence produces an `inconsistent` scope. It does not replace that evidence. The [conflict example](examples/inconsistent_hypothesis.kgq) demonstrates that later queries still see the original beliefs.

For an agent already running through the Python API, `agent.query(...)` evaluates the same syntax against its current, revised beliefs. Hypothetical queries are pure: they do not advance the agent, alter its goals, or invoke its environment.

## Let plans use hypotheses

A plan can ask whether an observation would be useful before performing it:

```text
plan inspect_route(X, Y, G) for at(G) priority 10 {
    when at(X), path(X, Y), unknown(clear(Y)).
    suppose(clear(Y)) {
        prove(promising(X, Y, G)).
    }
    observe clear(Y).
}
```

The ordinary `when` conditions use accepted knowledge. The hypothetical block then checks whether a clear destination would support a useful route. Every proof in the block must succeed. A false, unknown, or inconsistent hypothesis makes this candidate inapplicable. Only an actual observation can establish whether the destination is clear.

The [planning example](examples/hypothesis_planning.kg) includes a dead-end alley, a blocked bridge, and a forest route. The agent skips inspecting the alley because assuming it is clear does not establish a promising route. It observes the blocked bridge, checks the forest, and reaches its goal. A movement plan has priority 20, so supported movement is preferred over another inspection at priority 10.

Preview the next decision, or run the complete experiment:

```powershell
python -m kgodel deliberate examples/hypothesis_planning.kg
python -m kgodel run examples/hypothesis_planning.kg
```

`deliberate` loads no world and performs no operations. It prints considered candidates, hypothetical evidence, and the selected operation. Append `--result-json PATH` to save the preview. Both `deliberate` and `run` accept `--max-hypotheses` to bound hypothetical contexts per decision; the default is 64.

See the [saved planning trace](output/hypothesis-planning.trace.txt) for the complete example. Through the Python API, `agent.deliberate()` previews the next decision against current beliefs without changing the agent. A run's structured trace now includes `decisions`, with each executed event referring to the decision that selected it.

## Commit to a sequence

An observation and its follow-up action can belong to the same plan:

```text
plan inspect_and_move(X, Y) for at(Y) {
    when at(X), path(X, Y), unknown(clear(Y)).
    observe clear(Y).
    require at(X), path(X, Y), clear(Y).
    act move(X, Y).
}
```

The `when` guards choose the plan and bind its variables. `require` checks accepted evidence immediately before the next operation. If inspection reports a blockage, the agent abandons the remaining sequence and selects again. Entry guards are not invariants: observing `clear(Y)` naturally makes the entry condition `unknown(clear(Y))` stop holding. An operation without `require` has no additional step conditions.

Run the new four-step journey example:

```powershell
python -m kgodel run examples/multistep_route.kg
```

The agent abandons the bridge intention after inspection, then follows the forest intention through inspection, movement, another inspection, and arrival. It performs three observations and two successful movements. The [saved trace](output/multistep-route.trace.txt) explains the canceled intention and each continued step.

An active intention keeps its fixed bindings and is not preempted by newly applicable plans. It ends on completion, failure, or satisfaction of its goal. Through Python, calling `agent.run(max_steps=...)` again on the same agent resumes at its next unfinished step; `agent.deliberate()` previews that step or its replacement. Checkpoints preserve this state across process restarts. See the [0.4 specification](docs/language-v0.4.md) for intention semantics and the [0.6 session guide](docs/sessions-v0.6.md) for disk persistence.

## Try a different world

Edit the companion world JSON and rerun the same program:

- Set `"blocked": []` to make the bridge usable.
- Set `"blocked": ["bridge", "forest"]` to leave the agent stuck at the start.
- Use `--max-steps 1` to stop after the first action. A budget limit is distinct from logical falsity.

The agent's map and the actual edges in the world are separate. If an attempted edge does not exist, the simulator returns explicit negative evidence about that path.

## Semantics and current boundaries

Pure queries have no effects. Inference computes a finite closure of the current beliefs and rules, with explicit resource limits. After an observation revises a base belief, the closure is rebuilt, removing conclusions whose support disappeared. If an alternative proof still exists, the conclusion remains supported.

When selecting a new intention, KGodel considers unsatisfied goals in declaration order, then plans by descending priority. Equal priorities preserve declaration order; bindings remain deterministic. Priorities default to 0, so older programs retain their selection order. This is an explicit preference order, not a search for optimal plans. An identical plan instance is not retried for the same goal and base-belief set during an agent session. Multi-step intentions also record states visited during execution, preventing an immediate restart of their completed prefix. A previously unvisited belief set can permit a new attempt.

Observations from the local simulator are trusted. They replace the directly opposing base belief. Contradictions remaining in the derived knowledge stop the run with a diagnostic. This is a deliberately simple revision policy; it is not a general theory of trust or belief revision.

A goal is satisfied when it is supported by the current knowledge. That does not make every supplied initial belief objectively true. In the example, the final goal's proof comes from the simulator's successful movement observation.

Implemented: one agent, ground goals, function-free rules, explicit negation, unknown guards, local simulation, belief revision, proof records, bounded execution, nested hypothetical contexts, conditional plan applicability, explicit priorities, pure decision previews, multi-step intentions with current-evidence requirements, saved sessions, bundled demos, and an interactive shell.

Future experiments: competing evidence, counterfactual belief replacement, computed utility and information gain, and optional LLM-generated proposals. Hypothetical checks qualify declared plans; they do not synthesize new plans, predict actual tool outcomes, or grant facts to the accepted belief state. There is no general external-tool interface or real-world action execution.

See [the 0.4 intention specification](docs/language-v0.4.md), [the 0.3 planning specification](docs/language-v0.3.md), [the 0.2 hypothesis specification](docs/language-v0.2.md), and [the 0.1 core semantics](docs/language-v0.1.md) for exact behavior. The 0.4 specification supersedes the single-operation limit; 0.3 supersedes the original selection order.

## Validate

```powershell
python -m unittest discover -s tests -v
```

The tests cover recursive rules, variable consistency, explicit negation, unknown facts, invalid syntax, stale conclusions, alternative proofs, contradictions, action isolation, failed actions, repeat prevention, execution limits, trace determinism, and the command-line example. Hypothesis tests also cover nested and sibling isolation, conditional proofs, contradictory assumptions, resource limits, variable answers, and exploration of a live agent without changing its later behavior.

Planning tests cover bound hypothesis variables, priority and tie ordering, fallback after unsupported or inconsistent checks, shared decision budgets, pure previews, real observation requirements, decision-history continuity, and the route experiment.

Intention tests cover fixed bindings, local requirements, fresh derived evidence, goal completion, failed operations, retry suppression, priority behavior during commitments, pure continuation previews, and resuming at every pause boundary without replaying operations.

Shell tests cover current-state queries, inspection without effects, continued intentions, invalid input, resource budgets, exports, and clean exit. To verify the actual installed distribution from outside the checkout:

```powershell
python -m pip wheel . --no-deps --wheel-dir dist
python tools/verify_install.py dist
```

The verifier installs the wheel into a temporary environment and exercises the module command, console command, every bundled demo, a stepped shell session, and checkpoint resumption in separate processes from an unrelated directory. Session tests also cover every demo pause boundary, retained proof sources, conflicts, retry suppression, malformed files, and failed writes. The `dist` directory must contain exactly one KGodel wheel, or pass a specific wheel path. GitHub Actions runs the unit suite and this installation check on Windows and Linux with Python 3.10 and 3.13.

## Design references

KGodel is an experiment, with no claim that its components are novel. [Jason / AgentSpeak](https://jason-lang.github.io/) is a relevant precedent for logic-based agent plans and beliefs. [SWI-Prolog's account of tabled execution](https://www.swi-prolog.org/pldoc/man?section=tabling) discusses recursive inference and the importance of changing knowledge. KGodel itself uses bottom-up fixed-point inference, not SWI-Prolog or tabled resolution.

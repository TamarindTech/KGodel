# KGodel 0.3

**An experimental logic language for agents that can revise their beliefs and explain their decisions.**

KGodel combines a small Prolog-inspired syntax with explicit goals, guarded plans, observations, and actions. This working prototype explores the reasoning cycle in a finite simulated world.

KGodel supports **hypothetical reasoning**: `suppose` creates a temporary belief context, answers queries within it, and labels the assumptions behind each proof. Version 0.3 lets plans use these hypothetical checks to decide whether they are applicable, and adds explicit plan priorities and a preview of the next decision.

The first experiment starts with an outdated belief that a bridge is clear. The agent tries the bridge, discovers the blockage, retracts its old belief, checks a forest route, and reaches its destination. Its decision record preserves the evidence used before each action and the observations returned afterward.

## Run the experiment

Requires Python 3.10 or newer. There are no third-party dependencies, API keys, or installation steps. Open a terminal in this `KGodel` folder and run:

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
- `plan` matches a goal, checks guards, then performs exactly one operation.
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

## Try a different world

Edit the companion world JSON and rerun the same program:

- Set `"blocked": []` to make the bridge usable.
- Set `"blocked": ["bridge", "forest"]` to leave the agent stuck at the start.
- Use `--max-steps 1` to stop after the first action. A budget limit is distinct from logical falsity.

The agent's map and the actual edges in the world are separate. If an attempted edge does not exist, the simulator returns explicit negative evidence about that path.

## Semantics and current boundaries

Pure queries have no effects. Inference computes a finite closure of the current beliefs and rules, with explicit resource limits. After an observation revises a base belief, the closure is rebuilt, removing conclusions whose support disappeared. If an alternative proof still exists, the conclusion remains supported.

KGodel considers unsatisfied goals in declaration order, then plans by descending priority. Equal priorities preserve declaration order; bindings remain deterministic. Priorities default to 0, so older programs retain their selection order. This is an explicit preference order, not a search for optimal plans. Each plan has one operation. An identical plan instance is not retried for the same goal and base-belief set during an agent session.

Observations from the local simulator are trusted. They replace the directly opposing base belief. Contradictions remaining in the derived knowledge stop the run with a diagnostic. This is a deliberately simple revision policy; it is not a general theory of trust or belief revision.

A goal is satisfied when it is supported by the current knowledge. That does not make every supplied initial belief objectively true. In the example, the final goal's proof comes from the simulator's successful movement observation.

Implemented: one agent, ground goals, function-free rules, explicit negation, unknown guards, local simulation, belief revision, proof records, bounded execution, nested hypothetical contexts, conditional plan applicability, explicit priorities, and pure decision previews.

Future experiments: competing evidence, counterfactual belief replacement, computed utility and information gain, multi-step intentions, and optional LLM-generated proposals. Hypothetical checks qualify declared plans; they do not synthesize new plans, predict actual tool outcomes, or grant facts to the accepted belief state. There is no general external-tool interface or real-world action execution.

See [the 0.3 planning specification](docs/language-v0.3.md), [the 0.2 hypothesis specification](docs/language-v0.2.md), and [the 0.1 core semantics](docs/language-v0.1.md) for exact behavior. The 0.3 specification supersedes the earlier plan-selection order.

## Validate

```powershell
python -m unittest discover -s tests -v
```

The tests cover recursive rules, variable consistency, explicit negation, unknown facts, invalid syntax, stale conclusions, alternative proofs, contradictions, action isolation, failed actions, repeat prevention, execution limits, trace determinism, and the command-line example. Hypothesis tests also cover nested and sibling isolation, conditional proofs, contradictory assumptions, resource limits, variable answers, and exploration of a live agent without changing its later behavior.

Planning tests cover bound hypothesis variables, priority and tie ordering, fallback after unsupported or inconsistent checks, shared decision budgets, pure previews, real observation requirements, decision-history continuity, and the route experiment.

## Design references

KGodel is an experiment, with no claim that its components are novel. [Jason / AgentSpeak](https://jason-lang.github.io/) is a relevant precedent for logic-based agent plans and beliefs. [SWI-Prolog's account of tabled execution](https://www.swi-prolog.org/pldoc/man?section=tabling) discusses recursive inference and the importance of changing knowledge. KGodel itself uses bottom-up fixed-point inference, not SWI-Prolog or tabled resolution.

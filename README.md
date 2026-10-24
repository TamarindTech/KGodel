# KGodel 0.1

**An experimental logic language for agents that can revise their beliefs and explain their decisions.**

KGodel combines a small Prolog-inspired syntax with explicit goals, guarded plans, observations, and actions. This working prototype explores the reasoning cycle in a finite simulated world.

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

Names beginning with uppercase letters are variables. Lowercase names and double-quoted strings are constants. `%` and `//` introduce line comments. Version 0.1 is a function-free subset: it does not implement full Prolog.

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

## Try a different world

Edit the companion world JSON and rerun the same program:

- Set `"blocked": []` to make the bridge usable.
- Set `"blocked": ["bridge", "forest"]` to leave the agent stuck at the start.
- Use `--max-steps 1` to stop after the first action. A budget limit is distinct from logical falsity.

The agent's map and the actual edges in the world are separate. If an attempted edge does not exist, the simulator returns explicit negative evidence about that path.

## Semantics and current boundaries

Pure queries have no effects. Inference computes a finite closure of the current beliefs and rules, with explicit resource limits. After an observation revises a base belief, the closure is rebuilt, removing conclusions whose support disappeared. If an alternative proof still exists, the conclusion remains supported.

Version 0.1 uses source goal order, source plan order, and deterministic matching to choose an applicable plan. It does not search for optimal plans. Each plan has one operation. An identical plan instance is not retried for the same goal and base-belief set during an agent session.

Observations from the local simulator are trusted. They replace the directly opposing base belief. Contradictions remaining in the derived knowledge stop the run with a diagnostic. This is a deliberately simple revision policy; it is not a general theory of trust or belief revision.

A goal is satisfied when it is supported by the current knowledge. That does not make every supplied initial belief objectively true. In the example, the final goal's proof comes from the simulator's successful movement observation.

Implemented: one agent, ground goals, function-free rules, explicit negation, unknown guards, local simulation, belief revision, proof records, and bounded execution.

Future experiments: isolated hypotheses (`suppose`), competing evidence, plan ranking, multi-step intentions, and optional LLM-generated proposals. These features are not implemented in 0.1. There is no general external-tool interface or real-world action execution.

See [the language specification](docs/language-v0.1.md) for exact behavior and research questions.

## Validate

```powershell
python -m unittest discover -s tests -v
```

The tests cover recursive rules, variable consistency, explicit negation, unknown facts, invalid syntax, stale conclusions, alternative proofs, contradictions, action isolation, failed actions, repeat prevention, execution limits, trace determinism, and the command-line example.

## Design references

KGodel is an experiment, with no claim that its components are novel. [Jason / AgentSpeak](https://jason-lang.github.io/) is a relevant precedent for logic-based agent plans and beliefs. [SWI-Prolog's account of tabled execution](https://www.swi-prolog.org/pldoc/man?section=tabling) discusses recursive inference and the importance of changing knowledge. KGodel 0.1 itself uses bottom-up fixed-point inference, not SWI-Prolog or tabled resolution.

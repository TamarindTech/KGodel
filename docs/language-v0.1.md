# KGodel 0.1 language specification

Historical specification: this records the original core. KGodel 0.12 adds composed queries, hypotheses, multi-step plans, objects, and persistence. Use the [documentation home](README.md) for the current feature map and the [tutorials](tutorials/README.md) to learn today's syntax. Version-specific limits below apply to 0.1.

Status: experimental, implemented by the Python reference interpreter in this project.

## Purpose

Make an agent's accepted beliefs, logical consequences, goals, plan choices, observations, and belief changes inspectable. A recorded proof explains support within the agent's knowledge. It does not establish that the knowledge matches the world.

## Syntax

```ebnf
program     = "agent", name, "{", { declaration }, "}" ;
declaration = belief | rule | goal | plan ;
belief      = "belief", literal, "." ;
rule        = "rule", literal, ":-", literal, { ",", literal }, "." ;
goal        = "goal", atom, "." ;
plan        = "plan", name, [ "(", [ variables ], ")" ],
              "for", atom, "{", "when", guard, { ",", guard }, ".",
              operation, atom, ".", "}" ;
variables   = variable, { ",", variable } ;
guard       = literal | "unknown", "(", atom, ")" ;
operation   = "act" | "observe" ;
literal     = [ "not" ], atom ;
atom        = name, [ "(", [ term, { ",", term } ], ")" ] ;
term        = name | quoted_string | variable ;
```

Names match `[a-z][A-Za-z0-9_]*`. Variables match `[A-Z][A-Za-z0-9_]*`. Quoted strings use JSON string escapes. Constants are strings; numbers, lists, anonymous variables, and nested function terms are not supported. A predicate is identified by its name and arity. Commas mean conjunction. `%` or `//` begins a comment extending to the end of its line.

Only one agent is allowed per source file. Beliefs and goals are ground. A running agent needs at least one goal; query-only programs need not declare goals. Goal declarations are positive atoms in this version; a rule can define a positive goal predicate from negative evidence if needed.

Every rule-head variable must occur in its body. A plan declares exactly its variables, with no duplicates. Variables in an operation or an `unknown` guard must be bound by the ground goal match or an ordinary signed guard. Plan names must be unique.

## Logical meaning

Let `B` be the finite set of signed base beliefs and `R` the rules. The inference engine repeatedly adds all supported ground rule heads until no new signed atom is added. It retains one deterministic proof per conclusion. With function-free, range-restricted rules and finite input, the possible ground atoms are finite.

Explicit negative literals behave as signed evidence. `not p(a)` does not mean that a search for `p(a)` failed. There is no contraposition or negation-as-failure operator.

For a ground literal `L`:

| Evidence | Query result |
| --- | --- |
| `L` is supported and its opposite is not | `true` |
| The opposite of `L` is supported and `L` is not | `false` |
| Neither is supported | `unknown` |
| Both are supported | Reasoning error; ordinary inference stops |

A variable query enumerates supported bindings. No bindings means no supported answer; it does not establish explicit falsity for all substitutions.

`unknown(A)` is available only in plan guards. It checks that neither `A` nor `not A` is in the completed inference closure. It never generates bindings. All ordinary signed guards are solved before unknown guards, irrespective of their textual positions. The test is relative to the current belief snapshot; it is not asserted as a permanent fact.

Default inference limits are 10,000 supported signed atoms and 200,000 candidate matches per inference object. Exceeding a limit is an error, never a false result. This is a small reference implementation, not an optimized database.

## Agent state and execution

The state consists of base beliefs with sources, fixed rules, declared goals, fixed plans, a history of attempted plan instances, and an event log. The simulator stores its own position, directed edges, and blocked locations separately.

Each cycle:

1. Recompute logical consequences from the current base beliefs.
2. Check every goal. Finish with `achieved` if all are currently supported.
3. If the operation budget has been consumed, return `step_limit`.
4. Enumerate unsatisfied goals in declaration order. For each, enumerate plans in declaration order whose target matches that goal. Ordinary guard candidates are sorted by their rendered literals, then joined in guard order.
5. Select the first applicable plan instance not previously attempted for that goal and exact set of signed base beliefs. If none exists, return `stuck`.
6. Record the attempted instance and execute its single grounded operation once.
7. Accept the simulator's observations, replacing directly opposing base beliefs. Record the selected goal, plan, bindings, guard proofs, outcome, and belief changes.
8. Repeat from step 1. An action failure is an outcome that can supply new evidence; it does not automatically terminate deliberation.

Inference and plan matching do not execute operations. Logical backtracking cannot rerun an action. Repeat prevention is scoped to the current in-memory agent session and exact belief set; it is not a distributed exactly-once delivery guarantee.

All goals must hold in the same current closure for completion. Reaching a goal once does not permanently mark it achieved if subsequent actions invalidate it. The scheduler is deterministic, but it does not guarantee fairness or optimality.

The default run budget is 50 operations. Calling the Python agent object's `run` method again continues its in-memory state with an additional budget and preserves the trace numbering. Each command-line run starts a fresh agent and world.

## Simulator contract

The world JSON contains exactly three fields: `position` (a nonempty string), `edges` (a list of directed string pairs), and `blocked` (a list of locations). Known locations are the starting position and edge endpoints. Blocked locations must be among those known locations.

Supported operations:

| Operation | Outcome |
| --- | --- |
| `observe clear(Y)` | Reports `clear(Y)` or `not clear(Y)` for a known location. An unknown location returns an unsuccessful observation with no evidence. |
| `act move(X, Y)` with an incorrect origin | Fails, reporting `not at(X)` and the actual location. |
| `act move(X, Y)` without an actual edge | Fails, reporting `not path(X, Y)`. |
| `act move(X, Y)` into a blocked location | Fails, reporting `not clear(Y)`. |
| Successful `act move(X, Y)` | Updates the simulator position and reports `clear(Y)`, `not at(X)`, and `at(Y)`. A self-edge omits `not at(X)`. |

The runtime checks every plan's operation against this simulator before starting. It does not interpret arbitrary names as Python functions, shell commands, network calls, or file operations.

## Evidence, revision, and explanations

Initial beliefs have source `program`; simulator observations have a step-specific source such as `simulator:step_3`. Derived proofs identify the rule and supporting proofs. Version 0.1 stores one proof for each supported conclusion. Recomputing after revision can select another valid proof if the earlier support disappears.

A new observation replaces the directly opposing base belief about the same atom. It does not rewrite rules, remove unrelated beliefs, resolve every domain constraint, or automatically outrank a contradictory derived conclusion. A remaining conflict stops ordinary reasoning. In particular, the language does not enforce functional constraints such as exactly one `at` location for arbitrary supplied programs.

The event log stores the evidence that supported a plan at selection time, even if later observations invalidate it. The final goal proof reflects the revised current beliefs. A record of an `unknown` guard states that both polarities were absent from the selection snapshot; it is not a proof of falsity.

The human-readable trace summarizes each event. The JSON includes nested premises, bindings, observations, revisions, final beliefs, and final goal proofs. These are machine-generated proof and execution records, not a language model's hidden reasoning.

## Results and command-line behavior

Run results are `achieved`, `stuck`, `step_limit`, or `reasoning_error`. The last two do not imply a logically false goal. After a reasoning error, goal truth is reported as `unresolved`.

The command-line process exits with code 0 for an achieved run or a successfully evaluated query/check, code 1 for a run that did not achieve its goals, and code 2 for invalid input or file errors. Query truth is printed explicitly; a valid query returning `false` or `unknown` still exits with code 0. Trace files are written only when requested by the corresponding options, and those named files are replaced if they already exist.

`check` validates syntax and the initial inference closure. It does not load a world or establish that the goals are achievable. `query` and `explain` inspect initial knowledge only. The saved run trace or Python agent object exposes the execution's revised knowledge.

## Research direction

This implementation establishes a baseline for experiments, rather than defining the final language. The next semantic questions are:

1. How should `suppose` create an isolated hypothetical belief context and discharge assumptions?
2. How should an agent compare conflicting sources while retaining their evidence?
3. How should goal urgency, plan cost, risk, and information gain affect selection?
4. When should an agent abandon a committed multi-step intention?
5. How should proposed rules or plans from an LLM be validated before admission?

Hypothetical reasoning, probabilistic confidence, plan synthesis, multi-agent communication, arbitrary external tools, and LLM integration are not implemented in version 0.1.

Relevant primary references: [Jason / AgentSpeak](https://jason-lang.github.io/) for agent-oriented logic programming; [SWI-Prolog tabled execution](https://www.swi-prolog.org/pldoc/man?section=tabling) for recursive inference and changing knowledge. KGodel currently uses a simple fixed-point evaluator rather than those implementations.

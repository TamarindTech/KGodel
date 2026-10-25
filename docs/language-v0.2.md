# KGodel 0.2: isolated hypothetical reasoning

Historical extension: the scope and isolation semantics still apply. Later releases added [plan hypotheses](language-v0.3.md) and [composed queries](prolog-v0.11.md). Statements about future planning work below describe 0.2. See the [current tutorial](tutorials/03-hypotheses-and-abduction.md) or [documentation home](README.md).

Status: implemented in the local reference interpreter. This document adds query scopes to the [0.1 core language](language-v0.1.md); its program grammar, inference rules, and agent scheduling remain in effect.

## Meaning

`suppose` asks what follows if additional ground statements are temporarily accepted. It creates a child context, evaluates its queries, and discards that context on exit. Results are conditional records; the runtime never promotes them to accepted beliefs or completed goals.

```text
prove(can_move(start, forest)).
suppose(clear(forest)) {
    prove(can_move(start, forest)).
}
prove(can_move(start, forest)).
```

For the route example, the query is unknown in the base context, supported in the hypothetical context, and unknown again after exit.

Let `B` be a context's signed base beliefs, `R` its fixed rules, and `H` a list of assumptions. The child context computes the same fixed-point inference over `B ∪ H` and `R`. Both direct and derived contradictions make that child context inconsistent. `B`, `R`, and the environment remain unchanged.

This is additive hypothetical reasoning. It is not a counterfactual operator that retracts inconvenient evidence. If `clear(bridge)` is accepted, `suppose(not clear(bridge))` is inconsistent. A separate, explicit counterfactual revision operation may be explored later.

## Query syntax

Requests can be supplied as a command-line expression or a `.kgq` file. A request contains one or more statements:

```ebnf
request     = statement, { statement } ;
statement   = proof, "." | hypothesis, [ "." ] ;
proof       = literal | "prove", "(", literal, ")" ;
hypothesis  = "suppose", "(", literal, { ",", literal }, ")",
              "{", statement, { statement }, "}" ;
```

For convenience, the final top-level proof can omit its period, preserving ordinary command-line queries such as `clear(forest)`. Proof statements inside a hypothesis require a period. A period after a closing hypothesis brace is optional.

The program's atom, variable, quoted-constant, explicit-negation, and comment syntax also applies to requests. Assumptions must be ground; query literals may contain variables. Hypotheses require at least one assumption and one query. Empty requests are invalid.

`prove` and `suppose` introduce commands at the start of a query statement. To query a predicate with one of these names, place its literal inside `prove(...)`, for example `prove(prove(a)).` The separate legacy `parse_query` Python function still parses a single literal.

Variables in separate proof statements are independent. Query results do not bind variables in later statements. Unknown guards, rule declarations, goal declarations, action execution, and observations are not query statements. In particular, a `suppose` block cannot contain `act` or `observe` operations.

## Scope and evidence

The base context is named `base`. Hypothetical contexts are named `hypothesis_1`, `hypothesis_2`, and so on in encounter order within a request. Each record includes its parent context.

Nested contexts inherit the parent's base beliefs and assumptions, then add their own. Siblings are independent. Leaving an inner context removes its assumptions while retaining the outer context's assumptions. Leaving the outer context returns to the accepted base knowledge.

An assumption introduced by a context has a proof source such as `assumption:hypothesis_1`. Derived proofs retain their supporting premises, including these sources. An assumption that exactly repeats an existing base belief preserves the existing proof and source. Repeated identical assumptions have no additional logical effect.

Each query answer reports the assumptions used by its selected proof. An irrelevant assumption is not listed as a dependency. The engine still records one deterministic proof per conclusion: this is a sufficient support record, not a search for every proof or a minimal assumption set. In particular, a directly assumed literal may be selected even if the same literal could also be derived independently.

For a false ground query, the proof and assumption dependencies support its explicit opposite. Unknown queries have no supporting proof. Variable queries return supported substitutions, each with its own proof and dependencies. No supported substitutions is distinct from explicit falsity.

The query result itself can be retained after a scope closes, but it remains labeled with its original context and assumptions. It must not be treated as an unconditional proof about the base context.

## Inconsistency and resource limits

Contradictory assumptions in one scope are rejected regardless of their order. An assumption that contradicts accepted base evidence or creates a derived contradiction makes the entire child scope inconsistent; its body is not evaluated. A nested inconsistent scope does not invalidate an otherwise consistent parent, so following parent or sibling queries still run.

Exceeding an inference budget is an `error`, not an inconsistent hypothesis and not a false query. A valid base context is required before hypothetical evaluation begins. Invalid or contradictory initial knowledge is a request error rather than a child-scope result.

The parser permits at most 16 nested hypotheses. Evaluation also defaults to depth 16 and at most 64 hypothetical contexts per request. Every context receives the core limits of 10,000 supported facts and 200,000 candidate matches, shared by inference and variable queries in that context. The Python API can lower these limits; it can raise the evaluation limits, but the source parser still caps nesting at 16. Limits must be nonnegative.

Context counting includes attempted inconsistent scopes. Once the context limit is reached, further hypothetical scopes report an error without evaluation. Ordinary queries can still inspect their existing parent context.

## Command line

```powershell
python -m kgodel --version
python -m kgodel query examples/blocked_route.kg "suppose(clear(forest)) { prove(can_move(start, forest)). }"
python -m kgodel explain examples/blocked_route.kg --file examples/forest_hypothesis.kgq
python -m kgodel query examples/blocked_route.kg --file examples/inconsistent_hypothesis.kgq
```

`query` and `explain` accept exactly one input: an expression or `--file`. Both evaluate the same requests. `explain` prints the full selected proofs; `query` prints shorter answers and any assumption dependencies.

Append `--result-json PATH` to save the structured report. It includes the overall status and nested result records. Query records contain their context, literal, status, and proof or variable answers. Hypothesis records contain their assumptions, parent context, status, and body results or an error diagnostic.

| Overall report | Exit code | Meaning |
| --- | --- | --- |
| `ok` | 0 | Evaluation completed; individual answers may be true, false, unknown, or have no supported bindings. |
| `inconsistent` | 1 | At least one hypothetical scope was inconsistent. Valid surrounding queries were still evaluated. |
| `error` | 2 | At least one query or scope hit an evaluation error. |
| Input/base-knowledge/file error | 2 | The request could not begin normal evaluation. |

When both inconsistency and an evaluation error occur in a report, `error` takes precedence. A parent scope's `evaluated` status means its body was processed; inspect nested records or the overall report for child inconsistencies and errors.

Command-line queries load the program's initial beliefs. They do not load the companion world, run plans, or consume the agent's operation budget.

## Querying an agent's current knowledge

```python
agent.run(max_steps=1)  # The bridge failure revises its belief.
report = agent.query("""
    prove(clear(bridge)).
    suppose(clear(forest)) {
        prove(can_move(start, forest)).
    }
    prove(clear(forest)).
""")
```

`Agent.query` uses a snapshot of the agent's current base beliefs and its rules. It does not change those beliefs, the event history, plan-attempt history, environment position, or action/observation counters. A later `run` continues as if the exploration had not occurred.

For independent use, `parse_queries(source)` returns the request syntax tree and `evaluate_queries(knowledge, rules, queries, **limits)` returns a report. `format_query_results(report, explain=True)` renders a readable explanation. Constructing an inconsistent base inference raises a `KGodelError`; child-scope inconsistencies appear in the report.

Hypothetical reasoning is available to callers through this API, but is not yet a plan guard or an automatic plan-selection mechanism. Plan ranking and actions inside simulations are separate future work.

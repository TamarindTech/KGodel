# KGodel 0.3: hypothetical plan applicability

Versioned reference: the selection and hypothetical-check semantics still apply. [Version 0.4](language-v0.4.md) adds ordered operations and intentions, and [0.11](prolog-v0.11.md) adds composed queries in hypothesis bodies. See the [current planning tutorial](tutorials/05-goals-and-plans.md) or [documentation home](README.md).

Status: implemented by the reference interpreter. This extends the [0.2 hypothesis semantics](language-v0.2.md) and updates plan selection from the [0.1 core](language-v0.1.md).

## Plan syntax

```text
plan inspect_route(X, Y, G) for at(G) priority 10 {
    when at(X), path(X, Y), unknown(clear(Y)).
    suppose(clear(Y)) {
        prove(promising(X, Y, G)).
    }
    observe clear(Y).
}
```

The extended grammar is:

```ebnf
plan = "plan", name, [ "(", [ variables ], ")" ], "for", atom,
       [ "priority", integer ], "{",
       "when", guard, { ",", guard }, ".",
       { hypothesis }, operation, atom, ".", "}" ;
```

`hypothesis` uses the same `suppose(...) { ... }` syntax as query requests, including nested hypotheses. It appears after `when` and before the single operation. Multiple top-level hypothesis blocks are allowed. A period after a block is optional.

Priorities are one to seven decimal digits representing an integer from 0 through 1,000,000. Higher values are preferred. The default is 0. This numeric syntax is limited to priority metadata; numeric logical constants and arithmetic are still unsupported.

All variables in every hypothetical assumption and proof must already be bound by the goal match or ordinary signed guards. They must appear in the plan's declared variable list. Hypotheses cannot introduce output bindings for the action or later guards. Unknown guards also cannot create bindings.

Standalone hypothetical query requests still require ground assumptions. Plan templates may contain variables because the selector grounds the complete template before evaluation.

## Applicability

For each candidate plan instance:

1. Match its target against an unsatisfied ground goal.
2. Solve the `when` guards using accepted knowledge only. Ordinary signed guards bind variables; unknown guards test the completed base closure.
3. Ground all hypothesis templates using those bindings.
4. Evaluate the hypotheses in temporary contexts, using the existing additive and conflict-detecting semantics.
5. Require every proof statement in every block, including nested blocks, to return `true`.

A `false` or `unknown` proof makes the candidate `unsupported`. Any inconsistent hypothesis makes it `inconsistent`. These are applicability failures, so the selector can consider another candidate. A resource or evaluation error aborts the decision with `reasoning_error`; it is not treated as evidence that a lower-ranked plan is preferable.

Multiple top-level blocks are independent siblings and all must pass. Assumptions introduced in one block are unavailable in the next. Nested blocks inherit their outer assumptions only within that nesting. Successful hypothetical proofs are not inserted into accepted knowledge and cannot satisfy the ordinary guards of another plan.

Hypothetical applicability does not certify that an action is safe or will succeed. A programmer can explicitly choose an operation based on a conditional result. Programs that require observed preconditions must put those preconditions in ordinary guards. In the example, `travel` requires accepted evidence that its destination is clear; the hypothesis is used to select an observation first. The simulator still checks every real operation independently.

An assumption of the goal itself does not complete the agent. Goal satisfaction is checked against accepted knowledge, with observations supplying any real state changes.

## Selection order

The selector considers:

1. Unsatisfied goals in declaration order.
2. Plans for that goal by descending priority.
3. Equal-priority plans in declaration order.
4. Ground guard solutions in the existing deterministic matching order.

It selects the first applicable instance that has not already been attempted for the same goal and signed base-belief set. A high-priority plan for a later goal does not preempt a candidate for an earlier goal. Default priority 0 preserves earlier programs' behavior.

This is declared preference ordering, not utility maximization, plan synthesis, exhaustive search, or a fairness guarantee. Once a plan is selected, later candidates are not evaluated. A rejected hypothesis is reconsidered in a later decision; no global rejection cache is maintained.

## Decisions and evidence

A decision report contains:

- `status`: `selected`, `achieved`, `stuck`, or `reasoning_error`.
- `reason`: a short explanation of the result.
- `candidates`: untried instances with supported ordinary guards that were considered before selection stopped.
- `selected`: the selected candidate, or null.
- `hypotheses_checked`: the number of hypothetical scope attempts, including rejected or budget-denied scopes.

Each candidate includes its goal, plan name, priority, bindings, operation, accepted guard evidence, and hypothetical query report when applicable. The hypothetical report retains assumption provenance and supporting proofs. Candidates with no ordinary guard solutions and instances already attempted in the same belief state are not listed. Lower-ranked candidates after a selection are also not listed.

Hypothesis scope identifiers are local to each candidate's query report; `hypothesis_1` in two different candidate records does not denote shared state. The candidate record identifies the context in which its proof applies.

Agent execution keeps a `decisions` history. An executed event's `decision` field is a one-based index into that history. Final failed selections are retained even when they produce no action event. Decision and event references remain consistent when a paused operation budget is resumed in memory.

## Budgets

Each decision permits at most 64 hypothetical context evaluations by default, shared across candidate instances and including nested contexts. Directly contradictory contexts count as attempts. When a further scope is requested after the budget is exhausted, its report records an error and selection stops without executing an operation. As a result, the attempt count may include the denied scope beyond the budget.

`--max-hypotheses N` configures the decision budget for both `deliberate` and `run`; `N` must be nonnegative. A budget of zero allows ordinary plans with no hypothetical checks. The run operation budget is independent: hypothetical checks do not consume action or observation steps.

Core per-context inference limits and the depth-16 parser limit remain unchanged. Every run cycle gets a new decision budget. A preview uses a separate budget and does not consume an agent's future execution budget.

## Preview without action

```powershell
python -m kgodel deliberate examples/hypothesis_planning.kg
python -m kgodel deliberate examples/hypothesis_planning.kg --result-json output/planning-preview.json
python -m kgodel run examples/hypothesis_planning.kg --max-hypotheses 64
```

The command-line preview uses initial beliefs and loads no world file. It validates logical applicability, not whether a simulator implements the named operation or whether an actual path exists. `run` performs the normal simulator-operation validation before execution.

`deliberate` exits with code 0 for `selected` or `achieved`, 1 for `stuck`, and 2 for an input or reasoning error. Existing `run` exit behavior remains unchanged: 0 for achieved goals, 1 for a completed run result without achievement (including `reasoning_error`), and 2 for invalid input or file errors. Inspect the saved run's `status` for the distinction.

Through Python, `agent.deliberate(max_hypotheses=64)` previews using current revised beliefs and the agent's actual attempt history. It changes neither beliefs, action events, decision history, attempts, nor the environment. Repeated previews at the same state are deterministic. `agent.run(..., max_hypotheses=64)` performs actual operations and records decisions.

## Demonstration

The example's accepted map contains a dead-end alley, a bridge route, and a forest route. None of those destinations is initially known clear. Assuming the alley is clear cannot establish a promising route, so its observation plan is rejected. Assuming the bridge is clear does support a route, so the agent observes it; the actual observation reports a blockage. A later hypothesis qualifies an observation of the forest instead.

Once the forest is observed clear, the priority-20 movement plan takes precedence over priority-10 inspections, even though the inspection plan appears first in the source. The agent then observes its goal location and moves there. The run performs three observations and two successful movements, with no movement attempted into the blocked bridge.

The logical `reachable` rule describes map connectivity, not a guarantee that every later destination is clear. The agent still gathers evidence step by step. The saved trace preserves both the conditional reasoning and the separate real observations.

Further work includes computed utility, information gain, multi-step intentions, counterfactual state replacement, and richer environments. This version chooses among declared single-operation plans.

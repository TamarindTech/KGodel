# Prolog-style features in KGodel 0.11

Versioned reference: this describes syntax introduced in 0.11. KGodel 0.12 also adds [ground term comparisons](comparisons-v0.12.md) and writes schema-5 checkpoints while reading schemas 1–5. The schema-4 section below describes 0.11.

[Documentation home](README.md) · [Step-by-step logic tutorial](tutorials/02-logic-and-queries.md) · [Command reference](reference.md)

KGodel now supports composed queries, anonymous variables, single-quoted constants, and shorter fact and rule declarations. These build on the existing recursive, function-free rules and explicit signed evidence.

## Try the family-tree example

From the repository root:

```powershell
python -m kgodel check examples/prolog_family.kg
python -m kgodel query examples/prolog_family.kg "?- parent(alice, Parent), parent(Parent, Child)."
python -m kgodel explain examples/prolog_family.kg --file examples/prolog_family.kgq
```

The first query returns `Parent = bob, Child = "Mary Jane"` and `Parent = carol, Child = david`. The example needs no world file: `query` and `explain` inspect logical knowledge without running plans.

## Facts, rules, and constants

Inside an `agent` declaration, `parent(alice, bob).` is equivalent to `belief parent(alice, bob).`, and `ancestor(X, Y) :- parent(X, Y).` is equivalent to its `rule` form. Both styles may be mixed. Rule source numbers follow declaration order across both styles.

Facts must be ground. Every variable in a rule head must occur in the body. Anonymous variables cannot appear in a head. Recursive rules keep the existing finite fixed-point semantics. Shorthand also accepts explicit negative literals, such as `not retired(alice).`.

The declaration words `belief`, `rule`, `goal`, `plan`, `class`, and `object` remain reserved at the start of a declaration. Use explicit declarations for predicates with those names, for example `belief goal(review).`.

Single-quoted constants work wherever a term is accepted, including message receivers and slot values. `'Mary Jane'` and `"Mary Jane"` denote the same constant; `'alice'` and `alice` do too. A doubled apostrophe gives a literal apostrophe: `'it''s'`. Supported backslash escapes are `\n`, `\r`, `\t`, `\b`, `\f`, `\\`, `\'`, and `\"`. Other escapes are rejected. Unicode characters are preserved. Canonical output uses lowercase names or double quotes, so original quote style is not retained.

Predicate names, selectors, and declaration names still use their existing identifier syntax; quoted predicate names are not supported. Numbers, compound terms, and lists are not added in this release.

## Variables and anonymous matches

Names beginning with an uppercase ASCII letter or `_` are variables. A named variable such as `Person` or `_Person` must take the same value everywhere it occurs within one query expression. Period-separated queries have independent bindings.

Every occurrence of `_` is an independent anonymous match:

```text
?- parent(_, _).                  % Is any parent relationship supported?
?- parent(Parent, _).             % Return each distinct parent.
?- parent(_Person, _Person).      % Require the same value in both positions.
```

Anonymous matches never appear in the bindings dictionary. A successful query with only anonymous variables returns one empty binding, displayed as `true (no named bindings)`. No matches returns `no_answers`, not evidence of explicit falsity. Quoted `'_'` is an ordinary constant.

Anonymous variables are supported in query literals, rule bodies, logical method bodies, and signed plan entry guards. They are rejected in facts, goals, rule heads, method/plan parameters, plan targets, operations, step requirements, unknown guards, and plan hypotheses. Those contexts need ground values or stable named bindings. Ordinary standalone hypothesis query bodies may use `_`; the assumptions themselves must remain ground.

## Conjunction, disjunction, and grouping

```text
?- parent(alice, Parent), parent(Parent, Child).
?- artist(Person); scientist(Person).
?- ancestor(alice, Person), (artist(Person); scientist(Person)).
prove(ancestor(alice, Person), (artist(Person); scientist(Person))).
```

`,` means conjunction and joins on shared variables. `;` means disjunction and explores each alternative with the incoming bindings. A failed alternative cannot leak bindings into another. Comma binds more tightly: `a(X); b(X), c(X)` means `a(X); (b(X), c(X))`. Parentheses override that grouping. The `?-` prefix and the final period on a standalone request are optional; periods separate multiple requests.

Results contain each distinct named binding dictionary once, retaining its first proof. Alternatives are visited left to right; literal matching uses the existing deterministic ordering. If branches use different variables, a result may be partial: `artist(X); scientist(Y)` returns an `X` binding or a `Y` binding. Unbound names are omitted, not filled with invented values. Bindings from an earlier conjunction remain available to every later alternative.

Composition is available in CLI queries, `.kgq` files, shell queries and `:explain`, `Agent.query`, and `prove` bodies in temporary contexts. Object messages may appear as any leaf, for example `[Policy candidateFrom: start to: Place], path(Place, goal)`. Every message branch is validated, including branches whose answers would not be needed.

Rule bodies and plan entry guards retain conjunction-only syntax; method conditions remain period-separated. To express alternative rule clauses, write multiple rules with the same head. The comparison and abduction APIs still accept one ground literal per target. `parse_query` remains the single-literal parser; `parse_queries` parses composed requests.

## Truth and supporting evidence

KGodel retains explicit negative evidence. `not clear(bridge)` requires support for that negative literal. Missing support does not make it true. The `not` keyword applies to a literal, not a parenthesized expression.

For expressions without variables:

| Operator | True | False | Unknown |
| --- | --- | --- | --- |
| `A, B` | Both true | At least one false | Otherwise |
| `A; B` | At least one true | Both false | Otherwise |

Variable queries enumerate supported matches instead of claiming universal truth or falsity. Contradictions still produce a reasoning error. Queries have no action effects.

JSON reports retain the existing query result structure. Composed proof nodes have source `query:and` or `query:or`. Their conclusion names the requested expression, with query variables preserved; the answer's `bindings` dictionary gives the substitution and leaf proofs contain the actual ground evidence. An AND success records all component proofs; an OR success records its first successful branch for that binding. A false AND records one opposing branch, while a false OR records opposition to every branch. Opposing composite conclusions are labeled `not (...)` in proof output; that label is explanatory text, not executable negation syntax.

Temporary assumptions are reported only when present in the retained proof. Querying a temporary context does not grant its assumptions to accepted knowledge:

```text
suppose(artist(david)) {
    ancestor(alice, Person), artist(Person).
}
```

Plan hypotheses can combine checks with comma and semicolon, but all their named variables must already be bound by the plan's goal or entry guards. A plan check must evaluate to `true` before it qualifies the plan. Query composition neither executes nor synthesizes actions.

## Python and saved sessions

```python
from kgodel.demos import load_demo

agent = load_demo("super-routes")
report = agent.query("?- path(start, Place), path(Place, goal).")
for answer in report["results"][0]["answers"]:
    print(answer["bindings"])
```

Single literals still parse to `ProveQuery`. Composed requests parse to `ExpressionQuery` containing a `GoalExpression` tree. Evaluation combines answers without expanding the expression into disjunctive normal form.

Each expression is limited to 256 literal occurrences and 32 nested operator nodes; source grouping is separately limited to fewer than 64 nested parentheses. Redundant grouping does not add operator nodes. The existing inference fact/work limits apply, including literal matches during joins. Limit exhaustion reports an error, never logical falsity or a supposedly complete answer set.

New session saves use schema 4. Schemas 1–3 continue to load, including older superclass-message semantics. Canonical serialization preserves composed plan hypotheses and anonymous matching without inventing persisted bindings. Older KGodel versions cannot read schema-4 checkpoints.

KGodel remains an experimental finite logic language. This release does not implement general term unification, lists, arithmetic, cut, negation-as-failure, dynamic assertion/retraction, or Prolog's depth-first backtracking execution. For the source-language conventions, see the official [SWI-Prolog syntax reference](https://www.swi-prolog.org/man/syntax.html) and [SICStus variable reference](https://sicstus.sics.se/sicstus/docs/3.12.5/html/sicstus/Variables.html).

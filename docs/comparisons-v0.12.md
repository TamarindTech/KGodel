# KGodel 0.12: ground term comparisons

[Documentation home](README.md) · [Comparison tutorial](tutorials/09-term-comparisons.md) · [Command reference](reference.md)

KGodel can now compare constant values in queries, rule bodies, logical methods, plan entry guards, step requirements, and hypothetical query bodies. Comparisons filter existing bindings; they do not assign values or perform unification.

## Operators

| Operator | Meaning for resolved constants | Example |
| --- | --- | --- |
| `==` | Equal | `alice == 'alice'` |
| `\==` | Different | `alice \== bob` |
| `@<` | Lexically before | `alice @< bob` |
| `@=<` | Before or equal | `alice @=< alice` |
| `@>` | Lexically after | `bob @> alice` |
| `@>=` | After or equal | `bob @>= bob` |

Every logical constant remains a string. Ordering is case-sensitive lexicographic order by Unicode code point, with no locale collation or normalization. For example, `'10' @< '2'` is true because these are strings, not numbers. Single-quoted, double-quoted, and unquoted spellings of the same constant compare equally. An empty quoted constant is valid.

The notation follows [Prolog's term-comparison operators](https://www.swi-prolog.org/pldoc/man?section=compare), restricted here to ground constants. Unlike Prolog's identity test on variables, KGodel requires both operands to resolve to constants, even for `X == X`. This release does not add `=`, `\=`, `dif/2`, arithmetic, or structured terms.

## Bind before querying

```text
?- parent(alice, Child), Child \== bob.
?- parent(alice, Child), (Child == bob; Child == david).
?- parent(alice, First), parent(alice, Second), First @< Second.
```

Query conjunctions evaluate left to right. A comparison uses the incoming bindings and preserves them if it succeeds. `Child == bob` alone, or before any condition that binds `Child`, reports an unbound-variable error; it does not bind `Child`. An error invalidates that request's answer set rather than returning a misleading partial success.

Disjunctive branches keep separate bindings. In `(p(X); q(Y)), X == a`, rows from the second branch leave `X` unbound, so evaluation reports an error if such a row reaches the comparison. A later comparison is not evaluated if an earlier conjunction has no matches. Do not rely on an invalid branch being skipped: branch validation/evaluation can still report errors.

Comparisons bind more tightly than `,` and `;`. Their operands are individual terms, not predicates or nested comparisons. Parentheses group goal expressions, as before. Each side may be a named variable or a constant; methods also allow `@slot` and `self`. Anonymous `_` is rejected because it has no stable value to compare. Quoted `'_'` is an ordinary constant.

## Filter rules and methods

```text
sibling(X, Y) :- parent(Parent, X), parent(Parent, Y), X \== Y.
sibling_pair(X, Y) :- sibling(X, Y), X @< Y.
```

Rule bodies, method bodies, and plan entry guards first match their signed literals, then apply comparison filters, then test any unknown guards. This preserves their declarative binding behavior: a comparison may be written before the literal that supplies its variables. Nevertheless, writing binding conditions first usually makes the source easier to follow.

Every comparison variable in a rule or method must occur in a signed literal in that body. A comparison is not a binding source for head variables or method parameters. Constant-only conditions are valid, such as `same :- a == a.`. A failed filter simply prevents that rule instance from deriving its head. Therefore `sibling(bob, bob)` remains unknown unless separately opposed by explicit evidence; a failed body does not derive a negative head.

Methods resolve slots and `self` for the concrete receiver before evaluating conditions. Inherited methods and `super` keep that receiver. Quoted `'self'` and `'super'` remain literal constants through checkpoint serialization. Comparison-only methods may define unary truth tests, but their named parameters still need binding literals.

## Plans and temporary reasoning

```text
plan travel(From, To) for at(To) {
    when at(From), path(From, To), From \== To, unknown(clear(To)).
    suppose(clear(To)) { clear(To), From \== To. }
    observe clear(To).
    require clear(To), From \== To.
    act move(From, To).
}
```

This plan skips a move from a location to itself. Comparison variables must already be bound by the goal or signed entry conditions. Requirements and plan hypotheses use those fixed bindings. A false entry comparison disqualifies a candidate; a false requirement prevents its associated operation. Comparisons are pure and cannot supply observation evidence.

Comparisons cannot be asserted as facts, used as rule heads or agent goals, observed, or supplied as hypothesis/abduction assumptions. Abduction can prove a normal literal through rules containing comparison filters. Its target and candidate interfaces, and the saved-state `compare --query` interface, still accept single ground literals rather than comparison expressions.

## Truth, proofs, limits, and persistence

A resolved comparison is true or false. A true result has a ground proof node such as `bob \== carol [builtin:\==]`. A false result carries the supporting opposite comparison: querying `bob == carol` returns false with evidence for `bob \== carol`. Comparisons in successful rule/method proofs appear alongside the facts that supplied their bindings.

Builtin evidence is computed, not stored as an accepted fact. It introduces no assumption dependency of its own; any dependency arises from the fact/method evidence used to bind its operands. Hypothesis isolation, three-valued ordinary predicates, and conflict handling are unchanged. Query proofs retain the existing JSON structure.

Each evaluated comparison consumes one inference work unit, including false tests. Ground compound expressions evaluate their component statuses; they are not promised to short-circuit at an earlier true/false operand. Query expression limits count comparisons alongside literals: at most 256 conditions, 32 nested operator nodes, and fewer than 64 nested grouping parentheses.

New saves use checkpoint schema 5; schemas 1–4 remain readable. Comparison proof leaves must be ground, true, have the matching `builtin:` source, and have no premises. They cannot appear as accepted base beliefs. Stored intentions retain comparison evidence across restart. Older KGodel versions cannot read schema-5 checkpoints.

Python exposes `Comparison(left, operator, right)` in `kgodel.model`, and `parse_condition` parses one literal or comparison. `parse_query` remains the single-literal parser. `parse_queries` returns an `ExpressionQuery` for a comparison or a composite expression; `Agent.query` is the convenient interface for current-state queries.

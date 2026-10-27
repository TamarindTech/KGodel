# 9. Compare values and exclude duplicate pairs

Prerequisite: [facts and queries](02-logic-and-queries.md); [objects](04-objects-and-messages.md) for the final section. This lesson uses KGodel **0.12** and the complete [comparisons.kg](../../examples/tutorials/comparisons.kg) example.

## Find siblings without self-matches

Alice has three children: Bob, Carol, and David. Matching the parent relationship twice produces nine ordered combinations, including three self-pairs. A comparison removes those:

```text
sibling(X, Y) :- parent(Parent, X), parent(Parent, Y), X \== Y.
```

```powershell
python -m kgodel query examples/tutorials/comparisons.kg "sibling(First, Second)"
```

Six bindings remain: each person paired with each of the other two. `\==` asks whether the two bound values differ. It does not infer or assign either value.

## Return each pair once

Use lexical ordering to choose one orientation of every pair:

```text
sibling_pair(X, Y) :- sibling(X, Y), X @< Y.
```

```powershell
python -m kgodel explain examples/tutorials/comparisons.kg "sibling_pair(First, Second)"
```

The result contains exactly three bindings:

```text
First = bob, Second = carol
First = bob, Second = david
First = carol, Second = david
```

Below each binding, the explanation shows the parent facts, the different-value test, and the ordering test. The output includes computed evidence such as `bob @< carol [builtin:@<]`. This ordering selects a representative pair; it says nothing about age or importance.

## Select specific values

```powershell
python -m kgodel query examples/tutorials/comparisons.kg "?- parent(alice, Child), (Child == bob; Child == david)."
```

This returns Bob and David. `==` tests equality after the parent literal supplies `Child`. If you run `Child == bob` on its own, you get an unbound-variable error. KGodel's comparisons do not provide Prolog unification. `Child = bob` is also unsupported.

All six operators test strings: `==`, `\==`, `@<`, `@=<`, `@>`, and `@>=`. Thus `'10' @< '2'` is true lexically. Use quoted strings for those values; numeric logical terms and arithmetic remain outside this release. Anonymous `_` cannot be compared, but `_Child` is a normal named variable.

## Distinguish failed tests from negative facts

```powershell
python -m kgodel explain examples/tutorials/comparisons.kg "bob == carol"
python -m kgodel query examples/tutorials/comparisons.kg "sibling(bob, bob)"
```

The comparison is false because the constants differ; its proof shows the opposite comparison. The sibling predicate is unknown: no rule supports that self-pair, and no rule supplied its explicit negation. Failed rule conditions do not become negative facts.

## Reuse comparisons in methods and hypotheses

The example's `family` object has an `excluded` slot set to `bob`. Its method includes `Child \== @excluded` after matching a child. `[family otherChild: Child]` therefore returns Carol and David. A method can compare its configured values without changing them.

```powershell
python -m kgodel explain examples/tutorials/comparisons.kg --file examples/tutorials/comparisons.kgq
```

The query file also temporarily assumes that Emma is Alice's child. Within that context, `sibling_pair(carol, Other)` returns David and Emma; only Emma's proof depends on the temporary parent assumption. After the context closes, that relationship disappears.

Comparisons also work in plan guards and step requirements. For example, `From \== To` can rule out a self-move once the plan's goal and signed guards have bound both locations. Requirements test the fixed plan bindings before the associated operation; they cannot assign missing values.

## Exercise

Add a rule to a copy of the example that returns Alice's children whose names are lexically at or after `carol`. Predict the result.

<details>
<summary>Worked answer</summary>

```text
later_child(Child) :- parent(alice, Child), Child @>= carol.
```

`later_child(Child)` returns Carol and David. Names are compared using case-sensitive Unicode code-point ordering, not locale sorting or age. In a rule body the engine matches signed literals before filtering, but putting them first also makes the dependency clear to a reader.

</details>

See the [comparison reference](../comparisons-v0.12.md) for binding order, proof semantics, resource limits, and schema-5 persistence. [Saved-state comparison](../comparison-v0.7.md) is a separate feature: it compares whole agent snapshots.

[← Delivery capstone](08-delivery-capstone.md) · [Course index](README.md) · [Documentation home](../README.md)

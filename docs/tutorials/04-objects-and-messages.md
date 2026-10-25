# 4. Objects, messages, and inheritance

Prerequisite: [facts and queries](02-logic-and-queries.md). KGodel uses Smalltalk-inspired objects to organize logical policies. The interpreter is Python; a method describes evidence and returns supported answers, not an arbitrary Python value.

## Configure a policy object

[policies.kg](../../examples/tutorials/policies.kg) defines:

```text
class Catalog {
    slot subject.
    method candidate: Book { topic(Book, @subject). }
    method recommends: Book {
        [self candidate: Book].
        available(Book).
    }
}
object general : Catalog { subject = logic. }
```

These declarations belong inside the example's `agent` block. `@subject` reads the instance's configured value. Slots are initialized once and are read-only. `[general recommends: Book]` sends the keyword message `recommends:` to that object. Each method body condition must be supported; periods separate those conditions.

```powershell
python -m kgodel objects examples/tutorials/policies.kg
python -m kgodel query examples/tutorials/policies.kg "[general recommends: Book]"
```

The inspection lists the classes, instances, slots, and selectors. The query returns both logic books. This example intentionally marks both books available; it is a separate program from the earlier library knowledge base.

## Extend a parent condition

The example also contains:

```text
class CuratedCatalog extends Catalog {
    method candidate: Book {
        [super candidate: Book].
        featured(Book).
    }
}
object curated : CuratedCatalog { subject = logic. }
```

Only `'Logic for Agents'` is featured. Compare:

```powershell
python -m kgodel query examples/tutorials/policies.kg "[general recommends: 'Small Worlds']"
python -m kgodel query examples/tutorials/policies.kg "[curated recommends: 'Small Worlds']"
python -m kgodel explain examples/tutorials/policies.kg "[curated recommends: 'Logic for Agents']"
```

The results are true, unknown, and true. The inherited `recommends:` method sends to `self`, so the curated receiver uses its overridden `candidate:` method. That override asks `super` for the parent condition and adds `featured(Book)`. Missing featured evidence produces unknown, not false.

`self` keeps the actual receiver and uses its public method lookup. `super` also keeps the receiver, but starts lookup above the class defining the currently executing method. It does not create a parent object or change the slot values. Proofs show method sources and an annotation such as `^Catalog` for the parent lookup. That annotation is explanatory output, not ordinary source syntax.

## Query several objects

```powershell
python -m kgodel query examples/tutorials/policies.kg "?- [Shelf recommends: Book], available(Book)."
```

There are three distinct bindings: the general shelf with both books and the curated shelf with `'Logic for Agents'`. A variable receiver ranges over compatible declared objects. A nonexistent concrete receiver or a selector understood by no relevant object is an error; a valid message without evidence is unknown.

Methods remain pure. Sending a message cannot move an agent, mutate a slot, or call an external service. Policies can be used as plan guards later, where their answers qualify an explicitly declared operation.

## Exercise

In a copy of the example, add `featured('Small Worlds').` inside the agent. Does an additional `recommends:` override need to be written?

<details>
<summary>Worked answer</summary>

No. The existing inherited method sends through `self`, and the curated `candidate:` now has all required evidence for both books. `[curated recommends: Book]` returns both. This is a change to the facts supplying a policy, not a change to the method implementation.

</details>

The [object reference](../objects-v0.8.md) explains method clauses, receiver validation, and negative methods. The [super reference](../super-v0.9.md) explains lexical lookup and proof separation. Mutable slots, runtime allocation, metaclasses, blocks, and general Smalltalk syntax are outside this prototype.

[← Hypotheses](03-hypotheses-and-abduction.md) · [Course index](README.md) · [Next: goals and plans →](05-goals-and-plans.md)

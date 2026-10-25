# KGodel 0.9: extend reasoning with `super`

Version 0.9 lets an overriding method reuse its parent's reasoning and add conditions. Methods remain pure logical clauses, and instance variables remain read-only.

## Run the experiment

```powershell
python -m kgodel shell --demo super-routes
```

At the shell prompt:

```text
:objects
[approved candidateFrom: start to: bridge].
[cautious candidateFrom: start to: bridge].
:explain [cautious candidateFrom: start to: forest]
suppose(open(bridge)) { prove([cautious candidateFrom: start to: bridge]). }
:step
:checkpoint super-session.json
:run
```

The approved policy considers the bridge. The cautious policy also requires evidence that the route is open, so its bridge answer is initially unknown. Assuming `open(bridge)` supports a conditional answer without changing accepted beliefs or testing the real bridge. During execution, the cautious agent observes and follows the forest route, reaching the goal in four operations.

The editable program is [super_routes.kg](../examples/super_routes.kg); its world is [super_routes.world.json](../examples/super_routes.world.json). Resume the checkpoint with `python -m kgodel shell --resume super-session.json`.

## Add a condition without copying the parent

These declarations belong inside an agent:

```text
class RoutePolicy {
    method candidateFrom: From to: To {
        at(From).
        path(From, To).
    }
    method mayMoveFrom: From to: To {
        [self candidateFrom: From to: To].
        clear(To).
    }
}

class ApprovedPolicy extends RoutePolicy {
    slot permission.
    method candidateFrom: From to: To {
        [super candidateFrom: From to: To].
        approved(To, @permission).
    }
}

class OpenRoutePolicy extends ApprovedPolicy {
    method candidateFrom: From to: To {
        [super candidateFrom: From to: To].
        open(To).
    }
}

object cautious : OpenRoutePolicy { permission = reviewed. }
```

The cautious policy requires all three layers: an outgoing path from the current position, approval with the configured permission, and evidence of an open route. Multiple clauses for the same selector remain logical alternatives; each overriding clause can choose whether to use `super`.

## Lookup rules

- `[self selector]` starts lookup at the concrete object's class.
- `[super selector]` starts at the parent of the class **defining the containing method**. The receiver is still the same object.
- Lookup walks upward to the nearest class defining the selector and uses all its clauses. A `super` send may name a different selector from the containing method.
- A parent method sees the original object's instance values. Its `self` sends still use the concrete object's overrides.

For example, if a fourth class inherits `ApprovedPolicy`'s method unchanged, the `super` expression in that method still starts at `RoutePolicy`. It does not restart above that fourth class. This follows the [Smalltalk `self` and `super` lookup model described by Pharo](https://books.pharo.org/booklet-ReflectiveCore/html/Chapters/ObjVTheory/ObjVTheory.html).

`super` is special only as an unquoted receiver inside a method. To address an object literally named `super` from a method, use `["super" ready]`. Outside methods, `[super ready]` is an ordinary message to an object with that name. Predicate arguments such as `named(super)` remain constants; use `self` for the current object as an argument.

A root class cannot send to `super`. A missing superclass selector is a source error, including in an unused class. A declared selector without supporting evidence is unknown. `not [super ready]` requires an explicit negative parent clause; failure to prove a positive clause does not establish its negation. If both signs of a referenced parent selector are supported, inference reports the usual knowledge conflict.

## Follow the proof

An explanation for the cautious object's forest candidate contains this chain:

```text
[cautious candidateFrom: start to: forest]
  [cautious ^ApprovedPolicy candidateFrom: start to: forest]
    [cautious ^RoutePolicy candidateFrom: start to: forest]
      at(start)
      path(start, forest)
    approved(forest, reviewed)
  open(forest)
```

The full explanation also identifies each defining class and clause in its `method:Class>>selector@receiver#clause` source. `^Class` is a proof annotation meaning "lookup starts at this class." It is reserved for generated proof records, not accepted as program or query syntax.

Superclass support is kept separate from ordinary message support. A parent proving a candidate does not make that candidate true for a stricter subclass. Likewise, an ordinary belief or rule supporting `[cautious candidateFrom: ...]` cannot supply a missing superclass proof. As in 0.8, explicit beliefs and ordinary rules can independently support public messages; classes are an organization mechanism, not an authorization boundary.

Comparisons report changes to public conclusions and include superclass premises in their explanations. They omit internal lookup conclusions as standalone change rows. Assumptions used by parent methods remain visible in hypothetical proofs.

## Persistence and limits

New checkpoints use schema 3. They retain `super` expressions, annotated proofs, and active intentions. Loading resumes without replaying actions. Schema-1 and schema-2 checkpoints still load; schema-2 method receivers named `super` retain their original literal meaning and are quoted when saved again. Older KGodel versions cannot read schema 3.

The compiler expands only ancestor selectors referenced by `super`, sharing repeated targets for each receiver and lookup class. These clauses count toward the existing 10,000-rule limit, and their evidence counts toward inference fact/work budgets. Recursive `self` sends still use finite bottom-up reasoning. Exceeding a budget is an error, not a false answer.

No mutable slots, runtime allocation, class-side methods, blocks, cascades, binary selectors, or arbitrary return objects are added. See the [object-language guide](objects-v0.8.md) for the rest of KGodel's logical object model.

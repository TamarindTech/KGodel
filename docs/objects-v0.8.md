# KGodel 0.8: Smalltalk-inspired logical objects

This guide describes the object model introduced in 0.8. Current KGodel 0.11 also supports [`super` messages](super-v0.9.md), [composed queries](prolog-v0.11.md), and schema-4 checkpoints. The version-specific persistence and boundary sections below describe 0.8. Start with the [current object tutorial](tutorials/04-objects-and-messages.md) for a guided example.

This extension adds classes, instances, single inheritance, and message sending to KGodel. The interpreter remains Python. A method defines logical support for a message; its answer is true, false, unknown, or a set of supported variable bindings, accompanied by proof records.

## A complete example

```text
agent explorer {
    class Location {
        slot place.
        method clear { clear(@place). }
        method not clear { not clear(@place). }
        method reachableFrom: From { path(From, @place). }
    }

    object bridge : Location { place = bridge. }
    object forest : Location { place = forest. }

    belief at(start).
    belief path(start, forest).
    belief not clear(bridge).
    belief clear(forest).
    goal at(forest).

    plan move for at(forest) {
        when at(start), [forest reachableFrom: start], [forest clear].
        act move(start, forest).
    }
}
```

The class declarations live inside the agent. Class names start with an uppercase letter; object names and selectors start with a lowercase letter. Each object initializes exactly the instance variables declared by its class and ancestors. Initial values are constants, including quoted strings. `@place` accesses an instance variable inside a method; it is not available in ordinary rules or queries.

Queries for this program include:

```text
[forest clear].
[bridge clear].
[forest reachableFrom: From].
[Object clear].
```

The first answer is true; the second is false because an explicit negative method derives `not [bridge clear]`. The other queries enumerate supported bindings. Without the negative method, a blocked location would leave the positive message unknown rather than automatically false.

To run the complete program in the simulator, save a companion world with position `start`, an edge from `start` to `forest`, and an empty blocked list. A world is unnecessary for `check`, `query`, `explain`, `deliberate`, or `objects` inspection.

## Message syntax and methods

Unary messages have no arguments: `[forest clear]`. Keyword messages pair selector parts with arguments: `[cautious candidateFrom: start to: forest]`. Its selector is `candidateFrom:to:`. Square brackets delimit KGodel message literals; they do not introduce Smalltalk blocks.

```text
method candidateFrom: From to: To {
    at(From).
    path(From, To).
}
```

Every condition in the body must hold. Periods separate conditions; methods do not execute those conditions as imperative statements. Head parameters are unique uppercase variables and must appear in the body. Additional variables are local logical variables. Bodies contain ordinary signed literals or message literals, and must be nonempty. Multiple clauses of the same selector in one class provide alternative logical proofs. Positive and explicit negative clauses may coexist; contradictory support produces KGodel's normal knowledge-conflict diagnostic.

Arguments and receivers can be variables in queries and rules. A supported message from a concrete receiver can bind a receiver variable. Repeated variables must match consistently across receiver and arguments. Predicate `clear(forest)` and message `[forest clear]` are distinct facts, even when a method connects them.

Methods can read accepted beliefs, invoke other logical methods, and reason recursively under the existing finite-inference limits. All objects reason over the enclosing agent's accepted knowledge; they do not have separate belief stores. They cannot perform `act`, `observe`, host-language evaluation, or network calls. The simulator still executes only explicit agent-plan operations.

## Inheritance, overriding, and `self`

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
        at(From).
        path(From, To).
        approved(To, @permission).
    }
}
```

Lookup starts at the receiver's concrete class and follows its single-parent chain. The nearest class declaring a selector supplies all clauses for that selector, replacing all inherited positive and negative clauses. Other selectors remain inherited.

Inside a method, `self` denotes the concrete receiver, including when the method was inherited. Thus the inherited `mayMoveFrom:to:` method sends `candidateFrom:to:` to the cautious receiver and uses `ApprovedPolicy`'s override. Self can also appear as an argument to an ordinary predicate. Use the quoted constant `"self"` when you mean the literal string instead.

Composition uses a declared receiver directly, or an instance variable holding another object's name: `[@delegate ready]`. Instances have stable names and read-only configuration for the duration of an experiment. Inherited instance variables cannot be shadowed or initialized twice. A parent method can access only variables declared in that parent or its ancestors.

The design borrows receiver-based method lookup and inherited self sends from Smalltalk. See the official [Pharo object-model discussion](https://books.pharo.org/booklet-ReflectiveCore/html/Chapters/ObjVTheory/ObjVTheory.html) and [Pharo by Example](https://books.pharo.org/pharo-by-example/) for the source language's broader model.

## Methods in agent reasoning

Message literals work in beliefs, ordinary rule heads and bodies, positive goals, plan targets, guards, `unknown(...)` tests, step requirements, and hypothetical assumptions or proofs. They remain signed logical statements, so explicit initial beliefs or ordinary rules may also support a message. Methods are an organization and dispatch mechanism, not a trust or security boundary.

A plan can use a receiver variable when it is bound by its target or accepted guard evidence. An inherited method's hypothetical proof remains conditional: `suppose(clear(forest))` does not establish that the forest is actually clear. A later observation supplies real evidence before movement.

The bundled example demonstrates this sequence:

```powershell
python -m kgodel demo object-routes
python -m kgodel shell --demo object-routes
python -m kgodel objects examples/object_routes.kg
```

In the shell:

```text
:objects
[Receiver candidateFrom: start to: Place].
suppose(clear(bridge)) { prove([relaxed mayMoveFrom: start to: bridge]). prove([cautious mayMoveFrom: start to: bridge]). }
:step
:explain [cautious mayMoveFrom: start to: forest]
:run
```

The hypothetical bridge query is true for the relaxed object and unknown for the cautious object because bridge approval is absent. The cautious agent uses the forest and reaches `[cautious finished]` after four simulator operations.

## Python API and inspection

```python
from kgodel.demos import load_demo

agent = load_demo("object-routes")
report = agent.send("cautious", "candidateFrom:to:", "start", "forest")
assert report["results"][0]["status"] == "true"

answers = agent.query("[Receiver candidateFrom: start to: Place]")
assert agent.world.action_calls == 0
```

`Agent.send` accepts a receiver name, selector, and ground string arguments. The selector's colon count must match the argument count. It returns the same structured query report as `Agent.query` and accepts the same inference-limit keyword arguments. Use `Agent.query` for variables, signed messages, and hypothetical blocks.

`objects PROGRAM` and shell `:objects` show class ancestry, inherited selectors and defining classes, instances, and configured values. These commands do not invoke methods or operations. A nonexistent receiver or unsupported selector in a program or direct query is an error; a supported selector without evidence is unknown. Variable-receiver queries enumerate supported answers among instances whose classes implement that selector. A selector implemented by no declared instance is an error.

For direct use of `Inference` or `evaluate_queries`, pass `program.effective_rules` to include methods. `program.rules` continues to contain only the authored ordinary rules.

## Proofs, persistence, and comparison

For the finite declared object set, the interpreter instantiates effective methods into signed, function-free rules. Inherited self sends refer to the actual instance, preserving receiver-based dispatch. Each method proof source records `method:Class>>selector@object#clause`. Ordinary rule and observation proofs remain premises, including the assumptions used inside hypothetical scopes. Conclusions are recomputed after belief revision.

Version 0.8 introduced checkpoint schema 2 to embed class declarations, object configuration, and message-bearing rules, goals, histories, and active intentions. Loading restores the original program and resumes at its unfinished step without replaying observations. KGodel 0.11 writes schema 4 and continues to read schemas 1–3. Versions before 0.8 cannot read schema 2. An object program claiming schema 1 is rejected.

Comparisons include changes to class definitions and instance configuration, as well as changed message support and proofs. A comparison query may refer to an object absent from one side; on that side it is treated as an unsupported logical statement so additions and removals remain comparable. Direct program and agent query validation remains stricter.

## Boundaries in version 0.8

This is a logical object layer, not an implementation of the complete Smalltalk language. There are no mutable slots, runtime allocation, class-side methods, metaclasses, `super`, binary selectors, cascades, closures, implicit returns, or arbitrary returned objects. Logical methods return truth/proof information and supported bindings. Instance-variable inspection is explicit and values are not security secrets.

Inheritance is bounded at 64 classes per chain and method expansion at 10000 instantiated clauses per program. Duplicate declarations, cycles, unknown classes, invalid initializers, inaccessible slots, and unbound method parameters are rejected. Recursion uses the existing bottom-up inference engine and its fact/work budgets. Declarations and class hierarchy do not change during a run.

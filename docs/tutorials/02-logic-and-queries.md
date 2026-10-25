# 2. Facts, rules, and Prolog-style queries

Prerequisite: [lesson 1](01-getting-started.md). Work with [library.kg](../../examples/tutorials/library.kg), a complete knowledge base that runs without a simulator.

## Read a rule as a relationship

The program includes these declarations inside `agent library { ... }`:

```text
likes(alice, logic).
topic('Logic for Agents', logic).
available('Logic for Agents').
not available('Small Worlds').

recommended(Person, Book) :- likes(Person, Topic), topic(Book, Topic), available(Book).
```

A fact records accepted evidence. A rule says that a conclusion is supported when every body condition is supported with consistent variable values. Here the shared `Topic` links a person's interest to a book; `available(Book)` supplies the final condition. A rule does not call an external recommender or generate new books.

`belief likes(alice, logic).` and `rule recommended(...) :- ... .` are the longer declaration forms. Use either style. Facts cannot contain variables; every variable in a rule head must occur in its body.

## Bind and join variables

```powershell
python -m kgodel query examples/tutorials/library.kg "?- likes(Person, Topic), topic(Book, Topic)."
```

This returns three bindings: Alice with the two logic books, and Bob with `'Field Notes'`. Unlike `recommended`, this query does not require availability. Reusing `Topic` requires the two matched facts to agree on its value.

Uppercase names such as `Person` and names beginning with an underscore such as `_Person` are variables. Lowercase names and quoted strings are constants. Single and double quotes denote the same kind of constant; `'it''s'` contains an apostrophe. Predicate names remain lowercase identifiers.

```powershell
python -m kgodel query examples/tutorials/library.kg "?- likes(Person, _)."
python -m kgodel query examples/tutorials/library.kg "?- likes(_, _)."
```

The first returns Alice and Bob once each. The second prints `true (no named bindings)`. Every `_` matches independently and is omitted from results. `_Person` is named and repeated occurrences must agree.

## Combine alternatives

```powershell
python -m kgodel query examples/tutorials/library.kg "?- book(Book), (available(Book); not available(Book))."
```

This returns `'Logic for Agents'` and `'Small Worlds'`: both have some explicit availability evidence. `'Field Notes'` is omitted. `,` means and; `;` means or. Comma binds more tightly, so `a(X); b(X), c(X)` means `a(X); (b(X), c(X))`.

Variable scope is one whole expression. A period starts a separate request with new bindings. Alternatives return distinct binding dictionaries, retaining the first proof for duplicates. If branches mention different variables, some dictionaries may contain only one branch's names; use shared variable names when you want comparable answers.

## Separate false from unknown

```powershell
python -m kgodel query examples/tutorials/library.kg --file examples/tutorials/library.kgq
```

The file includes these ground questions:

| Query | Result | Why |
| --- | --- | --- |
| `available('Logic for Agents')` | true | Positive evidence exists |
| `available('Small Worlds')` | false | Its explicit negation exists |
| `not available('Small Worlds')` | true | The negative literal itself is supported |
| `available('Field Notes')` | unknown | Neither polarity is supported |

The query file asks a selection of these questions plus composed queries. A variable query with no matches reports no supported bindings, not a universal claim of falsity. KGodel does not interpret `not` as Prolog's negation-as-failure.

For a ground conjunction, any false operand makes it false; all operands must be true for it to be true. For a ground disjunction, any true operand makes it true; all must be false for it to be false. Remaining cases are unknown. Supporting or opposing evidence is available through `explain`.

## Follow recursion

[prolog_family.kg](../../examples/prolog_family.kg) contains:

```text
ancestor(X, Y) :- parent(X, Y).
ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
```

```powershell
python -m kgodel query examples/prolog_family.kg "ancestor(alice, Descendant)"
```

The supported descendants are Bob, Carol, Mary Jane, David, and Emma, rendered using their exact constants (`bob`, `carol`, `"Mary Jane"`, `david`, `emma`). KGodel repeatedly derives consequences until no new facts appear. This is finite bottom-up inference, not depth-first Prolog execution. Rules do not create compound terms or an unbounded stream of new constants.

## Exercise

In a copy of the library program, define `unavailable_interest(Person, Book)` for a person who likes a book's topic when that book has explicit negative availability evidence. Query all supported pairs.

<details>
<summary>Worked answer</summary>

Add inside the agent:

```text
unavailable_interest(Person, Book) :- likes(Person, Topic), topic(Book, Topic), not available(Book).
```

`unavailable_interest(Person, Book)` returns Alice and `'Small Worlds'`. Bob and `'Field Notes'` are absent because missing availability is not negative evidence.

</details>

The [Prolog reference](../prolog-v0.11.md) gives exact syntax and limits. Lists, arithmetic, cut, general unification, and disjunction inside rule bodies are not implemented; alternative rules can share a head.

[← Getting started](01-getting-started.md) · [Course index](README.md) · [Next: hypothetical reasoning →](03-hypotheses-and-abduction.md)

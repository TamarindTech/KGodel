# 3. Hypotheses and missing assumptions

Prerequisite: [facts and queries](02-logic-and-queries.md). This lesson asks two related questions: "What follows if this evidence were available?" and "Which missing evidence would support this conclusion?"

## Explore a temporary context

Bob likes travel, and `'Field Notes'` is a travel book, but its availability is unknown. Run:

```powershell
python -m kgodel explain examples/tutorials/library.kg --file examples/tutorials/library_hypotheses.kgq
```

The file contains:

```text
recommended(bob, 'Field Notes').
suppose(available('Field Notes')) {
    recommended(bob, Book), topic(Book, travel).
}
recommended(bob, 'Field Notes').
```

The first answer is unknown. Inside the temporary context, `Book = "Field Notes"` has a proof depending on the assumption `available("Field Notes")`. The final answer is unknown again. Discarding a hypothesis discards its conclusions as well; accepted beliefs are unchanged.

Nested contexts inherit outer assumptions, but a child cannot change its parent or siblings. Assumptions must be ground signed literals. Query bodies can bind variables, combine conditions, and send logical messages.

## Explore a contradiction

```powershell
python -m kgodel query examples/tutorials/library.kg "suppose(available('Small Worlds')) { recommended(alice, 'Small Worlds'). }"
```

The report is `inconsistent`, with exit code 1. Accepted knowledge already contains `not available('Small Worlds')`. A hypothesis adds evidence; it does not erase opposing evidence. The context returns no answers and leaves the original knowledge usable. This differs from an observation, which may revise a base belief during execution.

## Ask for missing assumptions

```powershell
python -m kgodel abduce --program examples/tutorials/library.kg --file examples/tutorials/library_abduction.kga --explain
```

The `.kga` request is:

```text
recommended(bob, 'Field Notes') from (
    available('Field Notes'),
    available('Logic for Agents'),
    available('Small Worlds')
)
```

The complete report identifies one explanation: assume `available("Field Notes")`. The other candidates are excluded because one is already supported and the other contradicts accepted evidence. Neither is needed to explain Bob's recommendation.

You supply the possible assumptions. KGodel searches consistent combinations and returns subset-minimal explanations: removing any assumption from a returned set would lose support. This does not rank explanations by plausibility, cost, or probability. An explanation is conditional support, not a fact, observation, or automatically chosen action.

## Understand search limits

```powershell
python -m kgodel abduce --program examples/tutorials/library.kg --file examples/tutorials/library_abduction.kga --max-contexts 0
```

This reports a partial search and exits 1 because it cannot evaluate the required hypothetical context. It does not establish that no explanation exists. `complete` means complete within the supplied candidate set and maximum assumption count; it is not a claim about every possible explanation in the world.

The defaults are at most 16 distinct supplied candidates, explanation size 3, 256 hypothetical contexts, and 20 solutions. Inference has additional fact/work budgets. Initial inconsistency and inference errors are reported separately. See the [abduction reference](../abduction-v0.10.md) for exact limits and JSON fields.

## Exercise

Predict the result of explaining Alice's existing recommendation with no candidates:

```powershell
python -m kgodel abduce --program examples/tutorials/library.kg "recommended(alice, 'Logic for Agents')"
```

<details>
<summary>Worked answer</summary>

The query is already supported. The minimal explanation is the empty assumption set, and the proof depends only on accepted evidence. Empty assumptions mean no additional evidence is needed; they do not mean that the search failed.

</details>

[← Logic and queries](02-logic-and-queries.md) · [Course index](README.md) · [Next: objects and messages →](04-objects-and-messages.md)

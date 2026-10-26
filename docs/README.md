# KGodel documentation

This is the documentation home for **KGodel 0.13.0a1**, an alpha developer preview. KGodel is an experimental language for inspectable agent reasoning: facts and rules describe knowledge, queries explain support, and plans act through a local simulator.

## Choose a starting point

| You want to… | Start here |
| --- | --- |
| Try the product preview or create a starter project | [Developer preview](product-preview.md) |
| Prepare verified release downloads | [Release guide](releasing.md) |
| Understand the idea without programming | [Introduction for developers and non-developers](introduction.md) |
| Learn by running and changing examples | [Nine-part tutorial course](tutorials/README.md) |
| Install KGodel or use the interactive shell | [Usage guide](using-kgodel.md) |
| Find a command, exit code, or file format | [Command reference](reference.md) |
| Resolve an error or an unexpected answer | [Troubleshooting](troubleshooting.md) |
| Understand a term such as belief or intention | [Glossary](glossary.md) |
| See what changed between releases | [Changelog](../CHANGELOG.md) |

No hosted service, API key, or language model is needed. Pure knowledge bases need no simulated world. Running plans or using the agent shell requires a goal and a route-world definition; bundled demos include both.

## Current feature references

Read these after a tutorial when you need precise behavior. Each versioned filename identifies the release that introduced that part of the language; it is not a separate edition to install.

| Area | Reference | Current behavior |
| --- | --- | --- |
| Term comparisons | [Equality, difference, and ordering](comparisons-v0.12.md) | Pure filters over bound constants, with computed proofs |
| Prolog-style syntax | [Queries, variables, and shorthand declarations](prolog-v0.11.md) | Conjunction/disjunction, grouping, anonymous matches, quoted constants |
| Hypotheses | [Scoped reasoning](language-v0.2.md) | Isolated assumptions; also usable in plans since 0.3 |
| Planning | [Selection](language-v0.3.md) and [intentions](language-v0.4.md) | Priorities, conditional checks, ordered operations, fresh requirements |
| Logical objects | [Objects](objects-v0.8.md) and [superclass reasoning](super-v0.9.md) | Read-only slots, single inheritance, dynamic `self`, lexical `super` |
| Abduction | [Missing-assumption search](abduction-v0.10.md) | Bounded, subset-minimal explanations over supplied candidates |
| Persistence | [Session structure](sessions-v0.6.md) and [current usage](using-kgodel.md) | Writes schema 5; reads schemas 1–5, including comparison evidence |
| Comparison | [Comparing evidence and progress](comparison-v0.7.md) | Pure comparison of saved/live state and proofs |
| Core reasoning | [Original core specification](language-v0.1.md) | Finite signed inference; later references extend syntax and scheduling |

## What is implemented

KGodel implements one agent per program, finite function-free rules, explicit negative evidence, three-valued ground queries, pure methods, temporary contexts, declared plans, a route simulator, checkpoints, and proof reports. Variable queries return distinct supported bindings. Observations can revise accepted beliefs; queries do not advance the world.

It does not implement full Prolog or Smalltalk, general term unification, lists, arithmetic, cut, negation-as-failure, mutable object slots, automatic plan synthesis, arbitrary external tools, LLM integration, or multi-agent communication. Plan priorities are an ordering preference, not an optimizer.

## Files and verification

Tutorial programs live in [examples/tutorials](../examples/tutorials/README.md). Run commands from the repository root unless a lesson says otherwise. Bundled `demo` commands work from any directory after installation; example paths refer to files in the checkout.

```powershell
python tools/verify_tutorials.py
```

This runs the teaching examples, checks their expected answers and restart behavior, and checks local Markdown link targets. Generated verification files stay in a temporary directory. The same check runs in CI on Windows and Linux.

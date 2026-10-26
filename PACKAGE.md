# KGodel

**Inspectable logic for experimental agents.** KGodel combines Prolog-inspired facts and rules with Smalltalk-style logical objects, explicit goals, guarded plans, belief revision, and explanations of each decision.

The developer preview includes:

- Queries, recursive rules, comparison filters, temporary hypotheses, and bounded abduction.
- Classes, inheritance, and `self` / `super` logical messages.
- A local route simulator, resumable sessions, and proof and trace exports.
- Two starter projects, five bundled demos, and an installation diagnostic.

Python 3.10 or newer is required. There are no runtime dependencies, API keys, or hosted services. Install the wheel from a verified [GitHub release](https://github.com/TamarindTech/KGodel/releases) with `python -m pip install PATH_TO_WHEEL`, then:

```sh
python -m kgodel doctor
python -m kgodel demo
python -m kgodel init my-agent
python -m kgodel run my-agent/agent.kg
```

This is an alpha developer preview, not a complete Prolog or Smalltalk implementation. It supports finite function-free logic and a local simulator. Arithmetic, general unification, external tool connectors, and a graphical application are not included. Syntax and Python APIs may change before 1.0; checkpoint compatibility is documented per release.

[Documentation](https://github.com/TamarindTech/KGodel/tree/main/docs) · [Tutorials](https://github.com/TamarindTech/KGodel/tree/main/docs/tutorials) · [Issues](https://github.com/TamarindTech/KGodel/issues) · [Source](https://github.com/TamarindTech/KGodel)

Released under the MIT license. Current source installation instructions are in the repository README. Availability on PyPI is not implied by this package description.

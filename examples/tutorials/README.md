# Tutorial examples

These files accompany the [KGodel tutorial course](../../docs/tutorials/README.md). Run commands from the repository root after installing KGodel 0.12 into your chosen Python.

| File | Lesson and purpose |
| --- | --- |
| [library.kg](library.kg), [library.kgq](library.kgq) | Facts, rules, variables, alternatives, true/false/unknown |
| [library_hypotheses.kgq](library_hypotheses.kgq) | Pure hypothetical queries against the library |
| [library_abduction.kga](library_abduction.kga) | Candidate assumptions for Bob's recommendation |
| [policies.kg](policies.kg) | Logical objects, slots, `self`, and `super` |
| [first_route.kg](first_route.kg), [world](first_route.world.json) | Minimal inspect-and-move agent |
| [delivery.kg](delivery.kg), [world](delivery.world.json) | Full policy/planning capstone |
| [inspect_agent.py](inspect_agent.py) | Python integration with checkpoints and comparison |
| [comparisons.kg](comparisons.kg), [queries](comparisons.kgq) | Distinct siblings, unique pairs, equality filters, and method slot comparisons |

```powershell
python -m kgodel query examples/tutorials/library.kg --file examples/tutorials/library.kgq
python -m kgodel explain examples/tutorials/policies.kg "[curated recommends: Book]"
python -m kgodel run examples/tutorials/first_route.kg
python -m kgodel run examples/tutorials/delivery.kg
python -m examples.tutorials.inspect_agent output/tutorial-python
python -m kgodel explain examples/tutorials/comparisons.kg --file examples/tutorials/comparisons.kgq
```

The library and policy files are pure knowledge bases: use `check`, `query`, `explain`, `objects`, or program-based `abduce`. They have no world or goal and cannot be run as simulated agents. The route examples have both.

To check the teaching scenarios and their expected answers without writing outputs into the repository:

```powershell
python tools/verify_tutorials.py
```

Examples are source-checkout resources, not additional bundled demos. They are not installed into the wheel. Use full paths if running a file-based command from another directory; run the Python `examples.tutorials` module from the checkout root.

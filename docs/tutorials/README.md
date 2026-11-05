# Learn KGodel step by step

These tutorials target **KGodel 0.14.0a1**. Start with no previous logic-programming experience, then build toward an agent whose decisions you can inspect, pause, and explain. Each lesson includes a runnable example, expected results, and an exercise with a worked answer.

## The course

| Lesson | What you will learn | Approximate time |
| --- | --- | --- |
| [1. Install and ask your first question](01-getting-started.md) | Run KGodel, distinguish terminal commands from language requests | 10 minutes |
| [2. Facts, rules, and Prolog-style queries](02-logic-and-queries.md) | Bind variables, join relationships, use alternatives and recursive rules | 20 minutes |
| [3. Hypotheses and missing assumptions](03-hypotheses-and-abduction.md) | Explore temporary evidence and ask what would make a conclusion provable | 20 minutes |
| [4. Objects, messages, and inheritance](04-objects-and-messages.md) | Write logical methods, configure slots, extend policies with `super` | 20 minutes |
| [5. Goals, plans, and observations](05-goals-and-plans.md) | Build a two-operation agent and inspect how evidence controls actions | 25 minutes |
| [6. Save, resume, and compare](06-sessions-and-comparison.md) | Preserve progress, inspect a saved state, compare changing proofs | 15 minutes |
| [7. Use KGodel from Python](07-python-api.md) | Evaluate pure knowledge and embed a resumable agent | 25 minutes |
| [8. Build an inspectable delivery agent](08-delivery-capstone.md) | Combine policy objects, hypotheses, abduction, execution, and persistence | 30 minutes |
| [9. Compare values and exclude duplicate pairs](09-term-comparisons.md) | Filter bound values with equality, difference, and lexical ordering | 20 minutes |
| [10. Build an agent from reusable modules](10-reusable-modules.md) | Split policies and plans across files, inspect dependencies, resume without source files | 25 minutes |

For a non-developer walkthrough, begin with the [introduction](../introduction.md), then lessons 1, 3, 5, and 6. You can inspect the supplied programs without writing one. Developers new to Prolog should follow the sequence. Developers familiar with logic programming can start at lesson 2 and continue to the agent features.

## Working conventions

- Run terminal commands from the repository root, where `pyproject.toml` lives. In a virtual environment, use that environment's Python throughout.
- Blocks labeled `powershell` are terminal commands. They use syntax that also works in ordinary macOS/Linux shells, except where Windows-specific paths are explicitly shown.
- Blocks labeled `text` contain KGodel source, shell requests, or output; the surrounding sentence tells you where they belong. Do not paste `kgodel>` prompt text into a request.
- Each `query`, `run`, or `demo` command starts from its input again. The interactive shell and Python `Agent` retain state across requests; `resume` starts from a checkpoint.
- A planned pause returns terminal exit code 1 when goals remain unfinished. That is expected in the persistence lessons.
- Lessons 1–9 write outputs under `output/tutorial-*`. Lesson 10 creates `my-modular-agent` and named checkpoint files in the current folder. Rerunning exports replaces those named outputs; project creation refuses existing folders. Keep source inputs and saved outputs at different paths.

Programs in [the example directory](../../examples/tutorials/README.md) are complete; short extracts in lessons illustrate specific parts. Exercises that change a program should use a copy so the baseline examples remain available.

## After the course

Use the [command reference](../reference.md) during daily work, [troubleshooting](../troubleshooting.md) when a result surprises you, and the [feature references](../README.md) for semantics and limits. Run `python tools/verify_tutorials.py` to reproduce the main teaching scenarios.

[Start lesson 1 →](01-getting-started.md) · [Documentation home](../README.md)

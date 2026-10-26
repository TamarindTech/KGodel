# Contributing to KGodel

Use Python 3.10 or newer and a virtual environment. Install the checkout with `python -m pip install -e .`. Runtime and unit tests use the standard library.

```sh
python -m unittest discover -s tests -v
python tools/verify_tutorials.py
```

For a distributable preview, follow [the release guide](docs/releasing.md). Change language semantics together with regression tests, examples, and the relevant feature reference. Preserve explicit false versus unknown results, pure queries, bounded reasoning, assumption provenance, and checkpoint compatibility. Test intentional incompatibilities and document them in the changelog.

Open a focused pull request describing the user-visible problem, resulting behavior, and checks run. Use [GitHub issues](https://github.com/TamarindTech/KGodel/issues) for reproducible bugs and feature proposals. Include KGodel/Python versions, operating system, a minimal program, the command, expected behavior, and actual output. `python -m kgodel doctor --json` gathers local installation details; review personal filesystem paths before sharing it.

This project is an experimental developer preview. Support is best effort through issues; there is no promised response time or production service agreement. Before proposing a large feature, explain the use case and intended language semantics in an issue.

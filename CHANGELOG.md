# Changelog

## 0.2.0

- Added nested `suppose` scopes for pure hypothetical reasoning.
- Added `prove(...)` query expressions and multi-query `.kgq` request files.
- Included assumption provenance and dependencies in query explanations and JSON results.
- Kept contradictory hypotheses isolated from accepted beliefs and sibling scopes.
- Added `Agent.query(...)` to explore an agent's current knowledge without advancing it.
- Added context and nesting limits, query exit statuses, examples, and a language-specification extension.
- Added a command-line version display. Existing route-world behavior and core rules remain compatible.

## 0.1.0

- Implemented function-free logical rules, explicit negation, and open-world query results.
- Added goals, guarded single-operation plans, observation-driven belief revision, and a local route simulator.
- Added proof records, execution traces, and the blocked-route experiment.

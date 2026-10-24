# Changelog

## 0.5.0

- Added standard Python packaging, wheel support, editable installation, and a `kgodel` console command.
- Bundled all three route experiments and their worlds; `demo` runs from any directory after installation.
- Added an interactive `shell` for querying current beliefs, explaining proofs, previewing decisions, stepping operations, continuing intentions, and exporting traces.
- Kept inspection commands pure and retained a live agent across shell commands, including after invalid input.
- Added setup and troubleshooting guidance for module-discovery errors and interpreter/environment mismatches.
- Added 21 demo and shell tests plus a wheel verification tool that installs and runs outside the source tree.
- Added Windows/Linux CI for Python 3.10 and 3.13, including installation verification.

## 0.4.0

- Added ordered multi-operation plans with optional `require` guards before each operation.
- Added intentions with fixed bindings, current-evidence checks, cancellation on failure or goal satisfaction, and in-memory resumption at the next unfinished step.
- Preserved existing single-operation syntax and selection behavior; prevented multi-step plans from restarting their completed prefixes at belief states already visited by the same instance.
- Extended pure previews to continuing and released intentions, including grounded sequences and requirement diagnostics.
- Recorded intention lifecycle events, operation cursors, and fresh requirement proofs in execution traces.
- Added the four-step route experiment, language specification, and 27 tests for continuation, reconsideration, and compatibility.

## 0.3.0

- Added `suppose` applicability checks inside plans, with variables grounded from accepted guard evidence and the goal match.
- Added explicit plan priorities, preserving declaration order for ties and existing programs.
- Added pure `deliberate` previews through the command line and the agent API.
- Recorded considered candidates, rejected hypotheses, conditional proofs, and selected operations in decision histories.
- Bounded hypothetical evaluation across candidates within each decision; errors stop selection rather than silently choosing a fallback.
- Added a route experiment that skips an unhelpful inspection, observes a blockage, and reaches the goal through an alternative route.

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

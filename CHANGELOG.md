# Changelog

## 0.14.0a1 — reusable modules

- Added local `module` declarations and `include` composition across all program-file commands, with shared logical names and validation after linking.
- Added `parse_file` and `load_project`, deterministic first-include expansion, bounded file/depth/byte loading, original-file syntax diagnostics, and dependency paths/content hashes through `imports`.
- Rejected cycles, duplicate module/class/object/plan names, module-defined goals, and paths outside the entry directory. Export protection now includes every loaded module.
- Kept text/checkpoint parsing free of filesystem includes. Saved sessions embed the combined program and retain schema-5 compatibility without needing their original source files.
- Added a packaged modular starter, a tenth tutorial, semantic/integration tests, and installed-wheel verification of module loading and restart without source files.

## 0.13.0a1 — developer preview

- Added `init` with route-agent and pure-logic starters, packaged query files, and first-project instructions. Existing destinations are never overwritten.
- Added local `doctor` diagnostics for the active Python/package, metadata mismatch, and bundled-demo health, with text and JSON output.
- Protected command-line exports from overwriting input files or sharing output paths, while preserving explicit in-place checkpoint resume. Invalid UTF-8 input reports a normal CLI error.
- Added wheel/source metadata validation, an offline starter kit, release manifests and checksums, isolated starter verification, and a manual draft-prerelease workflow.
- Extended the test matrix to macOS alongside Windows/Linux, added contributor/issue guidance, and documented alpha compatibility, supported use cases, and release steps. Checkpoint schema 5 is unchanged.

## 0.12.0

- Added ground equality, difference, and lexical-order comparisons (`==`, `\==`, `@<`, `@=<`, `@>`, `@>=`) to queries, rule/method bodies, plan entry guards, requirements, and hypothetical checks.
- Kept comparisons pure and non-binding, validated safe rule/method/plan variables, charged inference work for each test, and retained computed supporting/opposing evidence in proofs.
- Added checkpoint schema 5 for comparison proof leaves while retaining schema-1 through schema-4 loading and resumable intentions.
- Added 36 comparison semantic/integration tests, a ninth tutorial with runnable sibling/pair examples, and installed-package/tutorial verification of the new syntax.

- Added a documentation home, a tutorial course with exercises and worked answers, a command/exit-code reference, troubleshooting, and a glossary; the course now covers nine lessons for KGodel 0.12.
- Added runnable library, policy, first-route, delivery, and Python integration examples with query and abduction request files.
- Clarified historical language boundaries and current persistence compatibility, refreshed usage navigation, and added tutorial verification to Windows/Linux CI.

## 0.11.0

- Added conjunctive and disjunctive queries with shared variable bindings, comma-before-semicolon precedence, grouped expressions, and an optional `?-` prefix.
- Added independent anonymous `_` variables, named underscore variables, single-quoted constants, and shorthand facts and rules inside agents.
- Kept explicit three-valued truth for ground expressions, distinct named answer bindings, supporting/opposing proof trees, and hypothetical assumption provenance.
- Integrated composition with object messages, interactive queries, and plan hypotheses; bounded expression size/depth and reused inference work limits.
- Added checkpoint schema 4 for the expanded syntax, while retaining loading of schemas 1, 2, and 3.
- Added 34 semantic and integration tests, a family-tree example and query file, developer documentation, and installed-package verification for composed queries and resumable plans.

## 0.10.0

- Added bounded abductive reasoning: search explicit ground candidates for subset-minimal, consistent explanations of a query, with conditional proofs and no changes to accepted state.
- Integrated signed literals, recursive rules, object messages, and superclass proofs; distinguish baseline evidence, rejected candidates, conflicting combinations, and partial searches.
- Added `Agent.abduce`, the `abduce` CLI for program/demo/checkpoint sources, `.kga` request files, JSON reports, and shell `:abduce`.
- Added size, context, solution, and inference limits. Stop on unresolved inference to preserve the minimality of every returned explanation.
- Added 29 tests for semantic correctness, limits, pure inspection, CLI/shell behavior, and input-file protection; expanded installed-package checks for abduction and checkpoint inspection.
- Added a route-abduction example and user/developer documentation; checkpoint schema 3 remains unchanged.

## 0.9.0

- Added method-level `super` sends with lookup starting above the defining class, preserving the original receiver and dynamic `self` dispatch.
- Kept parent-method support separate from public messages so superclass answers cannot bypass subclass conditions; retained explicit negative support, alternative clauses, recursion, and inference budgets.
- Added nested superclass proof annotations and a three-level `super-routes` demo with hypothetical checks and resumable intentions.
- Added checkpoint schema 3 while retaining schema-1/schema-2 loading, including legacy objects literally named `super`.
- Added dispatch and integration tests plus installed-wheel checks for superclass explanations and cross-process resume.
- Updated the introduction, usage guide, README, and superclass reasoning reference.

## 0.8.0

- Added Smalltalk-inspired class and object declarations, read-only instance variables, single inheritance, selector overriding, and unary/keyword messages.
- Added pure logical methods, including explicit negative clauses, recursive message reasoning, variable receivers, object composition, and inherited `self` dispatch to subclass overrides.
- Integrated message literals with rules, goals, plan guards, step requirements, hypothetical queries, and comparisons; method proofs identify the defining class, receiver, selector, and clause.
- Added `Agent.send`, the `objects PROGRAM` command, and shell `:objects` inspection.
- Added the bundled `object-routes` experiment demonstrating relaxed and cautious route policies.
- Added checkpoint schema 2 for object programs while continuing to read schema-1 sessions.
- Added 27 object tests and installed-package checks for object queries, inspection, restart, and proof comparison.

## 0.7.0

- Added pure comparisons of saved and live agent states, including belief additions, removals, sign reversals, changed evidence, derived conclusions, goals, active intentions, and simulator state.
- Added `compare BEFORE AFTER`, repeatable ground `--query` arguments, `--explain`, JSON export, and the shell command `:compare PATH`.
- Compared full proof trees so alternative support remains visible when a conclusion stays true.
- Compared history prefixes and both differing tails without assuming the inputs share an execution lineage.
- Added independent inference budgets and partial reports that retain inspectable state while marking failed reasoning unresolved.
- Kept input checkpoints read-only, including protection against output aliases, and retained compatibility with schema-1 sessions from 0.6.
- Removed hidden inference during checkpoint loading so comparison budgets govern the actual reasoning work.
- Added 21 comparison tests and installed-package checks for CLI, shell, JSON export, and incomplete reasoning.

## 0.6.0

- Added self-contained JSON session checkpoints for the built-in route simulator, preserving program semantics, current beliefs and proof sources, world state, attempts, histories, and active intentions.
- Added `--checkpoint PATH` to `run` and `demo`, a `resume SESSION` command, `shell --resume SESSION`, and the shell's `:checkpoint PATH` command.
- Restored unfinished intentions without replaying prior operations; trace exports remain separate from resumable checkpoints.
- Added version and structural validation, bounded file loading, and atomic replacement that preserves an existing checkpoint when writing fails.
- Added a pure `Agent.execution_record()` accessor so reopened shells can inspect earlier traces immediately.
- Added 21 session tests and cross-process restart checks to the installed-wheel verifier.
- Updated the README, introduction, and usage guide; added a session format and semantics reference.

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

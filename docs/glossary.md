# KGodel glossary

[Documentation home](README.md) · [Tutorial course](tutorials/README.md)

| Term | Meaning in KGodel |
| --- | --- |
| Agent | One program with accepted beliefs, goals, declared plans, and execution state |
| Atom | A predicate applied to constant/variable terms, such as `path(start, X)`, or a logical message |
| Literal | An atom with positive or explicit negative polarity, such as `not clear(bridge)` |
| Ground | Contains no variables; every required value is concrete |
| Variable | A named placeholder whose repeated occurrences must agree within a query/rule instance |
| Anonymous variable | `_`, an independent match whose value is not included in bindings |
| Binding | An assignment such as `Place = forest` supporting a matched query or plan |
| Fact / base belief | A ground signed statement currently accepted, with its source |
| Rule | A clause deriving a head literal when all body conditions are supported |
| Closure | All consequences reached by repeatedly applying the finite rules to current base beliefs |
| Proof | An evidence tree describing why a literal or query expression is supported or opposed |
| Unknown | Neither a ground statement nor its explicit opposite is supported |
| Conflict | Both polarities are supported in one reasoning context; ordinary reasoning cannot continue consistently |
| Query | A pure question returning truth/support or bindings, without executing simulator operations |
| Term comparison | A computed equality, difference, or lexical-order test of two bound constants; it never binds variables |
| Hypothesis | A `suppose` context that temporarily adds ground evidence, then discards it and its consequences |
| Assumption dependency | A temporary assumption actually used in a retained proof |
| Abduction | Search over supplied candidates for consistent assumptions sufficient to prove a target |
| Subset-minimal | No proper subset of a returned assumption set still proves the target; not a probability or cost ranking |
| Goal | A ground condition the agent wants its accepted knowledge to support |
| Plan | A declared goal target, entry conditions, optional hypothetical checks, and ordered operations |
| Guard | A condition used to match a plan; signed guards can bind variables, unknown guards test support |
| Requirement | A condition rechecked against current evidence immediately before its associated operation |
| Intention | A selected plan instance with fixed bindings and a cursor identifying its next operation |
| Observation | A request for evidence from the simulator, currently `observe clear(Location)` |
| Action | A request to change simulator state, currently `act move(From, To)`; its outcome supplies evidence |
| Belief revision | Replacement of an opposing base belief after accepted simulator evidence, followed by recomputing conclusions |
| Logical object | A declared instance with read-only slots and logical methods |
| Selector | A message name such as `finished` or `candidateFrom:to:`; colons identify keyword arguments |
| `self` | The current receiver, using dynamic public dispatch even from an inherited method |
| `super` | The same receiver with lookup starting above the class defining the current method |
| Checkpoint | Self-contained resumable agent/world state, currently written with schema 5 |
| Trace | A cumulative execution report containing operations, decisions, and evidence; not a checkpoint |
| Partial result | A report whose requested reasoning/search did not fully resolve within its limits |

These meanings describe this prototype. A supported belief can still be wrong about the simulated world, a successful hypothesis is not an observation, and a logical message is not an external tool call.

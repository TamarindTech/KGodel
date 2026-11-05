# KGodel 0.14: reusable local modules

[Documentation home](README.md) · [Tutorial](tutorials/10-reusable-modules.md) · [Command reference](reference.md)

An entry file contains one `agent`. It can include files containing one `module` each:

```text
agent family_app {
    include "lib/family.kg".
    parent(alice, bob).
}
```

```text
module family {
    ancestor(X, Y) :- parent(X, Y).
    ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
}
```

The library may contain facts, rules, classes, objects, and plans, plus further includes. Only the entry agent may declare goals. All declarations share one logical namespace: module names identify source files; they do not qualify predicates or hide definitions. This feature is source composition, not Prolog's export/import namespace system.

## Linking and ordering

Includes expand where written, depth first. Each resolved file path is read once per load. Repeated includes and diamond dependencies reuse the first occurrence; an active circular include is an error. For example, both an agent and its policy module can include the same geography without duplicating its classes or plans.

Rules receive sequential `rule_1`, `rule_2`, … proof identifiers in the combined declaration order. Inserting a rule can renumber later identifiers, as with a single-file program. Classes and objects are validated after composition, so an inherited class or object may refer to a definition in a later included file. Existing inference, query, comparison, and hypothesis semantics are unchanged.

Distinct files must use distinct module names. Duplicate classes, objects, and plan names are rejected across the combined program. Multiple clauses of the same predicate are intentional and remain allowed. Conflicting facts are detected when knowledge is constructed, such as by `check` or a query; a dependency report performs structural validation only.

`include "path".` is recognized only as a top-level declaration in an agent or module. It cannot occur inside a method, plan, or query. Existing predicates named `include` or `module` remain valid, for example `include(item).`.

## Paths, errors, and loading limits

Paths are quoted strings relative to the file containing that include. Use forward slashes on every operating system. The project root is the resolved entry file's parent directory. Subfolders and `..` paths that remain inside that root are supported; absolute paths, backslashes, drive-qualified paths, control characters, and resolved paths outside the root are rejected. Symlinks are resolved before the boundary check. Place the entry file at the root of the source tree you want to use.

There are no URL imports, environment-variable expansion, search paths, package downloads, or code execution during loading. UTF-8 sources may begin with a BOM. Syntax errors retain the original file, line, and column, and nested errors identify the include chain. The loader is not an operating-system sandbox against concurrent hostile filesystem changes.

Default limits apply to the entry and its included sources together:

| Limit | Default |
| --- | --- |
| Unique source files, including the entry | 64 |
| Include depth, with entry at depth 0 | 16 |
| Bytes in one file | 1 MiB |
| Total bytes read | 8 MiB |

Repeated modules do not consume additional file or byte budget. Depth bounds still apply to each include traversal. Limits are checked while reading; failures raise input errors rather than return a partial program. The CLI uses these defaults, including for single-file input. Python callers can specify nonnegative integer limits.

## CLI and Python

All program-file commands load modules: `check`, `query`, `explain`, `objects`, `deliberate`, `run`, `shell`, and `abduce --program`. The world's default filename is still the entry file's `.world.json` companion. Module files do not choose worlds.

```sh
python -m kgodel imports my-agent/agent.kg
python -m kgodel imports my-agent/agent.kg --result-json dependencies.json
```

`imports` reports each file, declaration name, direct dependencies, raw-byte SHA-256 hash, and byte count. It performs no inference or agent operations. Its JSON uses `format: "kgodel-project"`, report version 1, and paths relative to the reported absolute root. File order is first discovery, beginning with the entry; that is different from the order in which nested declarations finish expanding. Hashes identify loaded bytes, not signatures or a package lockfile. Command-line exports cannot overwrite any loaded source or its file alias.

```python
from kgodel.loading import load_project, parse_file

program = parse_file("my-agent/agent.kg")
project = load_project("my-agent/agent.kg", max_files=32, max_bytes=2 * 1024 * 1024)
print(project.program.name)
print(project.as_dict())
```

`parse_file` returns a normal `Program`. `load_project` additionally returns immutable source descriptions and the dependency report. Each new call reads current files; an already-loaded agent or shell keeps its own program. There is no automatic live reload.

`kgodel.parser.parse(source)` remains a pure text parser and rejects include directives with a message to use `parse_file`. It never follows filesystem references. Demos that are already self-contained continue to use the text parser.

## Checkpoints

Checkpoints embed the complete combined program, with ordinary declarations and stable rule IDs for that loaded program. No include directives or source paths are needed to resume. Schema 5 is unchanged, and schemas 1–5 remain readable. Editing a library after saving does not change the saved agent; start a fresh run to use that edit. A checkpoint that contains an include directive is rejected, so loading saved state does not follow files from the checkpoint.

The source-dependency report is not stored in checkpoints. Export it separately when you need to record which file hashes produced a run.

# My modular KGodel agent

Run these commands in this folder using the environment where KGodel is installed:

```sh
python -m kgodel imports agent.kg
python -m kgodel check agent.kg
python -m kgodel explain agent.kg --file queries.kgq
python -m kgodel run agent.kg --trace-json run.trace.json
python -m kgodel shell agent.kg
```

The agent reaches its goal through the approved forest route in four operations. `agent.kg` chooses its goal and object configuration. `geography.kg` supplies facts and recursive reachability rules. `policies.kg` defines inherited message policies. `travel.kg` supplies a reusable plan.

Both the agent and policy module include geography; the loader reads it once. All declarations share one logical namespace. Module names label files, not predicate namespaces. Include paths are relative to the containing file and must stay within the entry agent's folder or subfolders. Circular includes and conflicting class, object, plan, or module names are errors.

Try removing `approved(forest).` from geography and rerunning: the agent becomes stuck because its policy has no approved first step. Restore it to continue. Every command reloads the files; an already-open shell keeps its loaded program.

Use `:checkpoint paused.session.json` to save progress. The checkpoint embeds the combined program, so `python -m kgodel resume paused.session.json` works even if the original module files have moved.

[Tutorials and reference](https://github.com/TamarindTech/KGodel/tree/main/docs)

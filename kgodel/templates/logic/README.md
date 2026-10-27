# My KGodel knowledge base

Run these commands from this folder with the Python environment where KGodel is installed:

```sh
python -m kgodel check agent.kg
python -m kgodel query agent.kg "ancestor(alice, Person)"
python -m kgodel explain agent.kg --file queries.kgq
```

`agent.kg` contains family facts, recursive rules, and comparison filters. The pair query returns Bob/Carol once and excludes self-pairs. The hypothetical query temporarily assumes a new child without changing the original knowledge.

Add another `parent` fact and repeat the queries. Variables begin with uppercase letters; constants begin with lowercase letters or use quotes. `\==` tests that two bound values differ; it does not assign values. Unknown means neither positive nor negative evidence is supported.

This is a pure knowledge base: it needs no world file. `run` and the agent shell additionally require goals, plans, and a world; create a `route` project to explore those features.

[Tutorials and reference](https://github.com/TamarindTech/KGodel/tree/main/docs)

# My KGodel route agent

Run these commands from this folder with the Python environment where KGodel is installed:

```sh
python -m kgodel check agent.kg
python -m kgodel explain agent.kg --file queries.kgq
python -m kgodel run agent.kg --trace-json run.trace.json
python -m kgodel shell agent.kg
```

This simulated agent discovers a blocked bridge, revises its beliefs, and travels through the forest. The run ends with `Result: achieved`. `agent.kg` describes its reasoning; `agent.world.json` describes the simulated environment. It does not call external services.

In the shell, try `:preview`, `:step`, `:explain not clear(bridge)`, and `:run`. Use `:checkpoint paused.session.json` to save progress and `:quit` to exit. Resume with `python -m kgodel resume paused.session.json`.

Experiment: add `forest` to the world's `blocked` list and run again. The agent should stop without claiming to have reached its goal. A run that does not achieve all goals returns exit code 1; malformed input returns 2.

[Tutorials and reference](https://github.com/TamarindTech/KGodel/tree/main/docs)

"""Tutorial 7: query, pause, save, resume, and compare a local agent.

From the repository root:
    python -m examples.tutorials.inspect_agent output/tutorial-python
"""

import argparse
from pathlib import Path

from kgodel.comparison import compare_agents
from kgodel.parser import parse
from kgodel.runtime import Agent, RouteWorld
from kgodel.sessions import load_session, save_session


def main(output: Path):
    folder = Path(__file__).resolve().parent
    program = parse((folder / "delivery.kg").read_text(encoding="utf-8"))
    world = RouteWorld.from_json((folder / "delivery.world.json").read_text(encoding="utf-8"))
    agent = Agent(program, world)

    answers = agent.query("?- [courier candidateFrom: depot to: Place].")
    print("Candidates:", [row["bindings"] for row in answers["results"][0]["answers"]])
    explanations = agent.abduce("[courier mayMoveFrom: depot to: bridge]",
                                ["clear(bridge)", "open(bridge)"])
    print("Missing assumptions:", explanations["solutions"][0]["assumptions"])
    print("Before execution:", world.observation_calls, "observations,", world.action_calls, "actions")

    agent.run(max_steps=1)
    checkpoint = output / "paused.session.json"
    save_session(agent, checkpoint)
    baseline = load_session(checkpoint)
    resumed = load_session(checkpoint)
    result = resumed.run()
    save_session(resumed, output / "finished.session.json")
    comparison = compare_agents(baseline, resumed, queries=["[courier finished]"])
    print("Resumed:", result["status"], "after", result["steps"], "total operations")
    print("Comparison:", comparison["status"], "changed:", comparison["changed"])
    print("Files:", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Folder for the two generated checkpoints")
    main(parser.parse_args().output)

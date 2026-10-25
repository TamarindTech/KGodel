"""Bundled experiments, loaded as package resources rather than working-directory files."""

from importlib.resources import files

from ..model import KGodelError
from ..parser import parse
from ..runtime import Agent, RouteWorld


DEMOS = {
    "blocked-route": ("blocked_route", "Revise an outdated belief after a failed movement."),
    "hypothesis-planning": ("hypothesis_planning", "Use hypothetical checks to choose useful observations."),
    "multistep-route": ("multistep_route", "Commit to a sequence and reconsider a blocked route."),
    "object-routes": ("object_routes", "Send logical messages to inherited route-policy objects."),
    "super-routes": ("super_routes", "Extend parent reasoning with super across three policy classes."),
}
DEFAULT_DEMO = "multistep-route"


def load_demo(name: str = DEFAULT_DEMO) -> Agent:
    if name not in DEMOS:
        raise KGodelError(f"Unknown demo {name!r}. Choose from: {', '.join(DEMOS)}.")
    stem, _ = DEMOS[name]
    resources = files(__package__)
    program = parse(resources.joinpath(f"{stem}.kg").read_text(encoding="utf-8"))
    world = RouteWorld.from_json(resources.joinpath(f"{stem}.world.json").read_text(encoding="utf-8"))
    return Agent(program, world)

"""A deterministic agent cycle and a local route-world simulator."""

from __future__ import annotations

from dataclasses import dataclass
import json

from .logic import Inference, Knowledge
from .model import Atom, KGodelError, Literal, Program, Proof, match


@dataclass
class Outcome:
    success: bool
    detail: str
    observations: tuple[Literal, ...]


class RouteWorld:
    """The environment owns reality; logical search cannot invoke it."""

    def __init__(self, position: str, edges: list[list[str]], blocked: list[str]):
        if not isinstance(position, str) or not position:
            raise KGodelError("World 'position' must be a nonempty string.")
        if not isinstance(edges, list) or any(not isinstance(edge, list) or len(edge) != 2
                or any(not isinstance(value, str) for value in edge) for edge in edges):
            raise KGodelError("World 'edges' must be a list of pairs of strings.")
        if not isinstance(blocked, list) or any(not isinstance(value, str) for value in blocked):
            raise KGodelError("World 'blocked' must be a list of strings.")
        self.position = position
        self.edges = {tuple(edge) for edge in edges}
        self.blocked = set(blocked)
        self.nodes = {position} | {node for edge in edges for node in edge}
        if not self.blocked <= self.nodes:
            raise KGodelError("Blocked locations must occur in the world's nodes.")
        self.action_calls = 0
        self.observation_calls = 0

    @classmethod
    def from_json(cls, source: str) -> RouteWorld:
        try:
            data = json.loads(source)
            if not isinstance(data, dict) or set(data) != {"position", "edges", "blocked"}:
                raise KGodelError("World requires exactly 'position', 'edges', and 'blocked' fields.")
            return cls(data["position"], data["edges"], data["blocked"])
        except json.JSONDecodeError as error:
            raise KGodelError(f"Invalid world JSON: {error.msg}.") from error

    def validate(self, program: Program):
        for plan in program.plans:
            expected = ("clear", 1) if plan.operation == "observe" else ("move", 2)
            if (plan.argument.name, len(plan.argument.args)) != expected:
                raise KGodelError(f"Route simulator does not support {plan.operation} {plan.argument}.")

    def observe(self, atom: Atom) -> Outcome:
        if atom.name != "clear" or len(atom.args) != 1 or atom.variables:
            raise KGodelError(f"Unsupported observation: {atom}.")
        self.observation_calls += 1
        target = atom.args[0]
        if target not in self.nodes:
            return Outcome(False, f"The simulator has no location {target}; no evidence was returned.", ())
        literal = Literal(atom, target in self.blocked)
        return Outcome(True, f"Observed {literal}.", (literal,))

    def act(self, atom: Atom) -> Outcome:
        if atom.name != "move" or len(atom.args) != 2 or atom.variables:
            raise KGodelError(f"Unsupported action: {atom}.")
        self.action_calls += 1
        origin, target = atom.args
        if self.position != origin:
            return Outcome(False, f"Agent is at {self.position}, not {origin}.", (
                Literal(Atom("at", (origin,)), True), Literal(Atom("at", (self.position,)))))
        if (origin, target) not in self.edges:
            return Outcome(False, f"No actual path from {origin} to {target}.", (
                Literal(Atom("path", (origin, target)), True),))
        if target in self.blocked:
            return Outcome(False, f"Movement failed: {target} is blocked.", (
                Literal(Atom("clear", (target,)), True),))
        self.position = target
        observations = [Literal(Atom("clear", (target,)))]
        if origin != target:
            observations.append(Literal(Atom("at", (origin,)), True))
        observations.append(Literal(Atom("at", (target,))))
        return Outcome(True, f"Moved from {origin} to {target}.", tuple(observations))


class Agent:
    def __init__(self, program: Program, world: RouteWorld):
        world.validate(program)
        if not program.goals:
            raise KGodelError("Running an agent requires at least one goal.")
        self.program = program
        self.world = world
        self.knowledge = Knowledge(program.beliefs)
        self.events: list[dict] = []
        self.attempts: set[tuple] = set()

    def inference(self) -> Inference:
        # Recompute from current base beliefs: old conclusions cannot survive revision.
        return Inference(self.knowledge, self.program.rules)

    def run(self, max_steps: int = 50) -> dict:
        if max_steps < 0:
            raise KGodelError("The step limit must be nonnegative.")
        status, reason = "step_limit", "Execution budget exhausted; the goal has not been disproved."
        for step in range(max_steps + 1):
            try:
                logic = self.inference()
            except KGodelError as error:
                status, reason = "reasoning_error", str(error)
                break
            pending = [goal for goal in self.program.goals if logic.status(Literal(goal)) != "true"]
            if not pending:
                status, reason = "achieved", "All goals are supported by the current beliefs."
                break
            if step == max_steps:
                break
            selected = None
            fingerprint = self.knowledge.fingerprint()
            try:
                # Goal order, then source plan order, then sorted literal matches.
                for goal in pending:
                    for plan in self.program.plans:
                        initial = match(plan.target, goal)
                        if initial is None:
                            continue
                        for bindings, evidence in logic.solve(plan.guards, initial):
                            key = (fingerprint, str(goal), plan.name, tuple(sorted(bindings.items())))
                            if key not in self.attempts:
                                selected = (goal, plan, bindings, evidence, key)
                                break
                        if selected:
                            break
                    if selected:
                        break
            except KGodelError as error:
                status, reason = "reasoning_error", str(error)
                break
            if selected is None:
                status, reason = "stuck", "No untried plan is applicable to an unsatisfied goal."
                break
            goal, plan, bindings, evidence, key = selected
            self.attempts.add(key)
            argument = plan.argument.ground(bindings)
            outcome = (self.world.observe(argument) if plan.operation == "observe"
                       else self.world.act(argument))
            event_number = len(self.events) + 1
            changes = [self.knowledge.observe(literal, f"simulator:step_{event_number}")
                       for literal in outcome.observations]
            self.events.append({
                "step": event_number,
                "goal": str(goal),
                "plan": plan.name,
                "bindings": bindings,
                "operation": plan.operation,
                "argument": str(argument),
                "because": [p.as_dict() if isinstance(p, Proof) else p for p in evidence],
                "success": outcome.success,
                "detail": outcome.detail,
                "belief_changes": changes,
            })
        final_logic = None
        if status != "reasoning_error":
            final_logic = self.inference()
        return {
            "agent": self.program.name,
            "status": status,
            "reason": reason,
            "steps": len(self.events),
            "events": list(self.events),
            "goals": {str(goal): final_logic.status(Literal(goal)) if final_logic else "unresolved"
                      for goal in self.program.goals},
            "beliefs": list(self.knowledge.fingerprint()),
            "goal_proofs": {str(goal): final_logic.explanation(Literal(goal)).as_dict()
                            for goal in self.program.goals
                            if final_logic and final_logic.explanation(Literal(goal))},
            "world_position": self.world.position,
            "action_calls": self.world.action_calls,
            "observation_calls": self.world.observation_calls,
        }


def format_trace(result: dict) -> str:
    lines = [f"KGodel 0.1 | agent {result['agent']}", ""]
    for event in result["events"]:
        lines.append(f"{event['step']}. Goal {event['goal']}: selected {event['plan']}.")
        for evidence in event["because"]:
            if "unknown" in evidence:
                lines.append(f"   Because {evidence['unknown']} is unknown in the current belief state.")
            else:
                lines.append(f"   Because {evidence['conclusion']} [{evidence['source']}].")
        lines.append(f"   {event['operation']} {event['argument']}: {event['detail']}")
        for change in event["belief_changes"]:
            if change["retracted"]:
                lines.append(f"   Revised {change['retracted']} -> {change['accepted']}.")
            elif change["changed"]:
                lines.append(f"   Learned {change['accepted']}.")
        lines.append("")
    lines.append(f"Result: {result['status']}. {result['reason']}")
    lines.append(f"Environment position: {result['world_position']}.")
    return "\n".join(lines)

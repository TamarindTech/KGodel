"""A deterministic agent cycle and a local route-world simulator."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re

from . import __version__
from .abduction import find_explanations
from .logic import Inference, Knowledge
from .model import Atom, KGodelError, Literal, Program, Proof, ProveQuery
from .objects import ObjectSpace
from .parser import parse_queries, parse_query
from .planning import Intention, attempt_key, choose_next, deliberate, format_decision
from .querying import evaluate_queries


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
            for step in plan.steps:
                expected = ("clear", 1) if step.operation == "observe" else ("move", 2)
                if (step.operation not in ("observe", "act") or step.argument.receiver is not None
                        or (step.argument.name, len(step.argument.args)) != expected):
                    raise KGodelError(f"Route simulator does not support {step.operation} {step.argument}.")

    def observe(self, atom: Atom) -> Outcome:
        if atom.receiver is not None or atom.name != "clear" or len(atom.args) != 1 or atom.variables:
            raise KGodelError(f"Unsupported observation: {atom}.")
        self.observation_calls += 1
        target = atom.args[0]
        if target not in self.nodes:
            return Outcome(False, f"The simulator has no location {target}; no evidence was returned.", ())
        literal = Literal(atom, target in self.blocked)
        return Outcome(True, f"Observed {literal}.", (literal,))

    def act(self, atom: Atom) -> Outcome:
        if atom.receiver is not None or atom.name != "move" or len(atom.args) != 2 or atom.variables:
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
        self.decisions: list[dict] = []
        self.intention: Intention | None = None
        self.intention_events: list[dict] = []
        self._next_intention_id = 1
        self._last_outcome: tuple[str, str] | None = None

    def inference(self) -> Inference:
        # Recompute from current base beliefs: old conclusions cannot survive revision.
        return Inference(self.knowledge, self.program.effective_rules)

    def query(self, source: str, **limits) -> dict:
        """Explore current knowledge without advancing this agent or its environment."""
        queries = parse_queries(source)
        ObjectSpace(self.program).validate_queries(queries)
        return evaluate_queries(self.knowledge, self.program.effective_rules, queries, **limits)

    def send(self, receiver: str, selector: str, *arguments: str, **limits) -> dict:
        """Send a ground logical message; return truth and proof without effects."""
        if not isinstance(receiver, str) or not isinstance(selector, str) or any(not isinstance(a, str) for a in arguments):
            raise KGodelError("Message receiver, selector, and arguments must be strings.")
        if (not re.fullmatch(r"[a-z][A-Za-z0-9_]*|(?:[a-z][A-Za-z0-9_]*:)+", selector)
                or selector.count(":") != len(arguments)):
            raise KGodelError("Message selector must match its number of arguments.")
        atom = Atom(selector, tuple(arguments), receiver)
        ObjectSpace(self.program).validate_atom(atom)
        return evaluate_queries(self.knowledge, self.program.effective_rules, (ProveQuery(Literal(atom)),), **limits)

    def abduce(self, query: str, candidates: list[str] | tuple[str, ...], **limits) -> dict:
        """Find minimal hypothetical support without changing this agent."""
        if (not isinstance(query, str) or not isinstance(candidates, (list, tuple))
                or any(not isinstance(candidate, str) for candidate in candidates)):
            raise KGodelError("Abduction needs a query string and a list or tuple of candidate strings.")
        return find_explanations(self.program, self.knowledge, parse_query(query),
                                 tuple(parse_query(candidate) for candidate in candidates), **limits)

    def deliberate(self, *, max_hypotheses: int = 64) -> dict:
        """Preview the next plan without recording an attempt or performing it."""
        return deliberate(self.program, self.knowledge, self.attempts,
                          max_hypotheses=max_hypotheses, intention=self.intention).report

    def _remember_intention_state(self):
        if self.intention is not None and len(self.intention.candidate.plan.steps) > 1:
            current = self.intention.candidate
            self.attempts.add(attempt_key(self.knowledge, current.goal, current.plan, current.bindings))

    def _release_intention(self, status: str, reason: str, **details):
        if self.intention is not None:
            self._remember_intention_state()
            if status == "completed":
                details["next_step"] = None
            self.intention_events.append({**self.intention.as_dict(), "status": status, "reason": reason,
                                          "after_step": len(self.events), **details})
            self.intention = None

    def run(self, max_steps: int = 50, *, max_hypotheses: int = 64) -> dict:
        if max_steps < 0:
            raise KGodelError("The step limit must be nonnegative.")
        if max_hypotheses < 0:
            raise KGodelError("The hypothesis budget must be nonnegative.")
        status, reason = "step_limit", "Execution budget exhausted; the goal has not been disproved."
        for step in range(max_steps + 1):
            try:
                logic = self.inference()
            except KGodelError as error:
                status, reason = "reasoning_error", str(error)
                break
            pending = [goal for goal in self.program.goals if logic.status(Literal(goal)) != "true"]
            if not pending:
                self._release_intention("goal_satisfied", "The intention's goal is already supported by current beliefs.")
                status, reason = "achieved", "All goals are supported by the current beliefs."
                break
            if step == max_steps:
                if self.intention is not None and logic.status(Literal(self.intention.candidate.goal)) == "true":
                    self._release_intention("goal_satisfied", "The intention's goal is already supported by current beliefs.")
                break
            decision = choose_next(self.program, self.knowledge, logic, self.attempts, self.intention,
                                   max_hypotheses=max_hypotheses)
            self.decisions.append(decision.report)
            release = decision.report.get("released_intention")
            if release is not None:
                self._release_intention(release["status"], release["reason"],
                                        requirements=release.get("requirements", []))
            if decision.selected is None:
                status, reason = decision.report["status"], decision.report["reason"]
                break
            selected = decision.selected
            goal, plan, bindings, evidence, key = (selected.goal, selected.plan, selected.bindings,
                                                  selected.evidence, selected.key)
            self.attempts.add(key)
            if self.intention is None:
                self.intention = Intention(self._next_intention_id, selected)
                self._next_intention_id += 1
                self.intention_events.append({**self.intention.as_dict(), "status": "committed",
                                              "reason": "Selected a plan with fixed bindings.",
                                              "after_step": len(self.events)})
            self._remember_intention_state()
            operation = plan.steps[selected.step_index]
            argument = operation.argument.ground(bindings)
            outcome = (self.world.observe(argument) if operation.operation == "observe"
                       else self.world.act(argument))
            event_number = len(self.events) + 1
            changes = [self.knowledge.observe(literal, f"simulator:step_{event_number}")
                       for literal in outcome.observations]
            self.events.append({
                "step": event_number,
                "goal": str(goal),
                "plan": plan.name,
                "priority": plan.priority,
                "decision": len(self.decisions),
                "intention": self.intention.id,
                "plan_step": selected.step_index + 1,
                "total_steps": len(plan.steps),
                "bindings": dict(bindings),
                "operation": operation.operation,
                "argument": str(argument),
                "because": [p.as_dict() if isinstance(p, Proof) else p for p in evidence],
                "success": outcome.success,
                "detail": outcome.detail,
                "belief_changes": changes,
            })
            self._remember_intention_state()
            if not outcome.success:
                self._release_intention("operation_failed", outcome.detail)
            elif selected.step_index + 1 == len(plan.steps):
                self._release_intention("completed", "All operations in the plan completed successfully.")
            else:
                self.intention = replace(self.intention, next_step=selected.step_index + 1)
        self._last_outcome = (status, reason)
        return self.execution_record()

    def execution_record(self) -> dict | None:
        """Describe the last run without advancing or releasing an intention."""
        if self._last_outcome is None:
            return None
        status, reason = self._last_outcome
        final_logic = None
        if status != "reasoning_error":
            final_logic = self.inference()
        return {
            "agent": self.program.name,
            "status": status,
            "reason": reason,
            "steps": len(self.events),
            "events": list(self.events),
            "decisions": list(self.decisions),
            "active_intention": self.intention.as_dict() if self.intention else None,
            "intention_events": list(self.intention_events),
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
    lines = [f"KGodel {__version__} | agent {result['agent']}", ""]
    for event in result["events"]:
        lines.append(f"{event['step']}. Goal {event['goal']}: selected {event['plan']} "
                     f"(priority {event['priority']}).")
        if event.get("total_steps", 1) > 1:
            lines.append(f"   Intention {event['intention']}, plan step {event['plan_step']} of {event['total_steps']}.")
        decision = result["decisions"][event["decision"] - 1]
        if decision.get("released_intention") or any(candidate["hypotheses"] for candidate in decision["candidates"]):
            lines.extend("   " + line for line in format_decision(decision).splitlines())
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
    if result["decisions"] and (not result["events"]
            or result["events"][-1]["decision"] < len(result["decisions"])):
        lines.append("Final deliberation:")
        lines.extend("   " + line for line in format_decision(result["decisions"][-1]).splitlines())
    for event in result.get("intention_events", []):
        if event["status"] not in ("committed", "completed"):
            lines.append(f"Intention {event['id']} ({event['plan']}) after operation {event['after_step']}: "
                         f"{event['status']}. {event['reason']}")
    if result.get("active_intention"):
        active = result["active_intention"]
        lines.append(f"Pending intention {active['id']} ({active['plan']}): "
                     f"next plan step {active['next_step']} of {active['total_steps']}.")
    lines.append(f"Result: {result['status']}. {result['reason']}")
    lines.append(f"Environment position: {result['world_position']}.")
    return "\n".join(lines)

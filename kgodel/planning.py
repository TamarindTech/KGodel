"""Pure plan selection with explicit priorities and conditional applicability."""

from __future__ import annotations

from dataclasses import dataclass

from .logic import Inference, Knowledge
from .model import (Atom, Bindings, KGodelError, Literal, Plan, PlanStep, Program, Proof,
                    Unknown, ground_query, match)
from .querying import evaluate_queries, format_query_results


@dataclass(frozen=True)
class Candidate:
    goal: Atom
    plan: Plan
    bindings: Bindings
    evidence: tuple[Proof | dict, ...]
    key: tuple
    step_index: int = 0
    intention_id: int | None = None


@dataclass(frozen=True)
class Intention:
    id: int
    candidate: Candidate
    next_step: int = 0

    def as_dict(self) -> dict:
        return {"id": self.id, "goal": str(self.candidate.goal), "plan": self.candidate.plan.name,
                "bindings": dict(self.candidate.bindings), "next_step": self.next_step + 1,
                "total_steps": len(self.candidate.plan.steps)}


@dataclass(frozen=True)
class Decision:
    selected: Candidate | None
    report: dict


def walk_results(results: list[dict]):
    for result in results:
        yield result
        yield from walk_results(result.get("results", []))


def attempt_key(knowledge: Knowledge, goal: Atom, plan: Plan, bindings: Bindings) -> tuple:
    return (knowledge.fingerprint(), str(goal), plan.name, tuple(sorted(bindings.items())))


def check_requirements(step: PlanStep, bindings: Bindings, logic: Inference) -> tuple:
    """Requirements test fixed bindings against accepted knowledge; they never bind variables."""
    evidence, checks = [], []
    for requirement in step.requirements:
        atom = requirement.atom.ground(bindings)
        if isinstance(requirement, Unknown):
            status = logic.status(Literal(atom))
            supported = status == "unknown"
            label = str(Unknown(atom))
            proof = {"unknown": str(atom)}
        else:
            literal = requirement.ground(bindings)
            status = logic.status(literal)
            supported = status == "true"
            label = str(literal)
            proof = logic.explanation(literal)
        checks.append({"requirement": label, "status": status, "supported": supported})
        if supported:
            evidence.append(proof)
    return all(check["supported"] for check in checks), tuple(evidence), checks


def candidate_report(candidate: Candidate, checks: list[dict]) -> dict:
    plan, bindings = candidate.plan, candidate.bindings
    step = plan.steps[candidate.step_index]
    return {"goal": str(candidate.goal), "plan": plan.name, "priority": plan.priority,
            "bindings": dict(bindings), "operation": step.operation,
            "argument": str(step.argument.ground(bindings)),
            "because": [p.as_dict() if isinstance(p, Proof) else p for p in candidate.evidence],
            "hypotheses": None, "status": "checking", "requirements": checks,
            "plan_step": candidate.step_index + 1, "total_steps": len(plan.steps),
            "intention": candidate.intention_id,
            "sequence": [{"operation": item.operation, "argument": str(item.argument.ground(bindings)),
                          "requirements": [str(Unknown(guard.atom.ground(bindings)))
                                           if isinstance(guard, Unknown) else str(guard.ground(bindings))
                                           for guard in item.requirements]} for item in plan.steps]}


def choose_plan(program: Program, knowledge: Knowledge, logic: Inference,
                attempts: set[tuple] | None = None, *, max_hypotheses: int = 64) -> Decision:
    """Select without recording an attempt, changing beliefs, or invoking an environment."""
    if max_hypotheses < 0:
        raise KGodelError("The hypothesis budget must be nonnegative.")
    if not program.goals:
        raise KGodelError("Plan selection requires at least one goal.")
    attempts = attempts if attempts is not None else set()
    pending = [goal for goal in program.goals if logic.status(Literal(goal)) != "true"]
    report = {"status": "achieved" if not pending else "stuck",
              "reason": "All goals are supported by the current beliefs." if not pending
              else "No untried plan is applicable to an unsatisfied goal.",
              "candidates": [], "selected": None, "hypotheses_checked": 0}
    # Stable sorting preserves declaration order among equally ranked plans.
    plans = sorted(program.plans, key=lambda plan: -plan.priority)
    try:
        for goal in pending:
            for plan in plans:
                initial = match(plan.target, goal)
                if initial is None:
                    continue
                for bindings, evidence in logic.solve(plan.guards, initial):
                    key = attempt_key(knowledge, goal, plan, bindings)
                    if key in attempts:
                        continue
                    supported, step_evidence, checks = check_requirements(plan.steps[0], bindings, logic)
                    selected = Candidate(goal, plan, bindings, evidence + step_evidence, key)
                    candidate = candidate_report(selected, checks)
                    report["candidates"].append(candidate)
                    if not supported:
                        candidate["status"] = "requirements_failed"
                        continue
                    if plan.hypotheses:
                        queries = tuple(ground_query(query, bindings) for query in plan.hypotheses)
                        assessment = evaluate_queries(knowledge, program.effective_rules, queries,
                            max_contexts=max_hypotheses - report["hypotheses_checked"])
                        candidate["hypotheses"] = assessment
                        records = list(walk_results(assessment["results"]))
                        report["hypotheses_checked"] += sum(item["kind"] == "suppose" for item in records)
                        if assessment["status"] == "error":
                            candidate["status"] = "error"
                            raise KGodelError("Plan hypothesis evaluation failed; no action was selected.")
                        if assessment["status"] == "inconsistent":
                            candidate["status"] = "inconsistent"
                            continue
                        if any(item["status"] != "true" for item in records if item["kind"] == "query"):
                            candidate["status"] = "unsupported"
                            continue
                    candidate["status"] = "selected"
                    report.update(status="selected", selected=candidate,
                                  reason="First applicable untried plan by goal order, descending priority, "
                                         "declaration order, and deterministic bindings.")
                    return Decision(selected, report)
    except KGodelError as error:
        if report["candidates"] and report["candidates"][-1]["status"] == "checking":
            report["candidates"][-1]["status"] = "error"
        report.update(status="reasoning_error", reason=str(error))
    return Decision(None, report)


def choose_next(program: Program, knowledge: Knowledge, logic: Inference,
                attempts: set[tuple] | None = None, intention: Intention | None = None, *,
                max_hypotheses: int = 64) -> Decision:
    """Continue a commitment or release it and select again, without changing agent state."""
    if max_hypotheses < 0:
        raise KGodelError("The hypothesis budget must be nonnegative.")
    release = None
    if intention is not None:
        current = intention.candidate
        if logic.status(Literal(current.goal)) == "true":
            release = {**intention.as_dict(), "status": "goal_satisfied",
                       "reason": "The intention's goal is already supported by current beliefs."}
        else:
            step = current.plan.steps[intention.next_step]
            supported, evidence, checks = check_requirements(step, current.bindings, logic)
            if supported:
                selected = Candidate(current.goal, current.plan, current.bindings, evidence,
                                     current.key, intention.next_step, intention.id)
                candidate = candidate_report(selected, checks)
                candidate["status"] = "selected"
                return Decision(selected, {"status": "selected", "reason": "Continuing the active intention "
                                          "with requirements checked against current beliefs.",
                                          "candidates": [candidate], "selected": candidate,
                                          "hypotheses_checked": 0})
            release = {**intention.as_dict(), "status": "requirements_failed",
                       "reason": "The next step's requirements are not supported by current beliefs.",
                       "requirements": checks}
        # A released multi-step plan must not restart its successful prefix in this state.
        attempts = set(attempts or ())
        attempts.add(attempt_key(knowledge, current.goal, current.plan, current.bindings))
    decision = choose_plan(program, knowledge, logic, attempts, max_hypotheses=max_hypotheses)
    if release is not None:
        decision.report["released_intention"] = release
    return decision


def deliberate(program: Program, knowledge: Knowledge, attempts: set[tuple] | None = None, *,
               max_hypotheses: int = 64, intention: Intention | None = None) -> Decision:
    snapshot = knowledge.copy()
    logic = Inference(snapshot, program.effective_rules)
    return choose_next(program, snapshot, logic, attempts, intention, max_hypotheses=max_hypotheses)


def format_decision(report: dict) -> str:
    lines = []
    if report.get("released_intention"):
        release = report["released_intention"]
        lines.append(f"Released intention {release['id']} ({release['plan']}): "
                     f"{release['status']}. {release['reason']}")
        for check in release.get("requirements", []):
            lines.append(f"  Required {check['requirement']}: {check['status']}.")
    for candidate in report["candidates"]:
        lines.append(f"{candidate['plan']} for {candidate['goal']} "
                     f"(priority {candidate['priority']}): {candidate['status']}.")
        for evidence in candidate["because"]:
            if "unknown" in evidence:
                lines.append(f"  Accepted knowledge leaves {evidence['unknown']} unknown.")
            else:
                lines.append(f"  Supported: {evidence['conclusion']} [{evidence['source']}].")
        if candidate["hypotheses"]:
            lines.extend("  " + line for line in format_query_results(candidate["hypotheses"]).splitlines())
        for check in candidate.get("requirements", []):
            lines.append(f"  Required {check['requirement']}: {check['status']} "
                         f"({'supported' if check['supported'] else 'unsupported'}).")
    if report["selected"]:
        selected = report["selected"]
        if selected.get("total_steps", 1) > 1:
            lines.append(f"Plan step {selected['plan_step']} of {selected['total_steps']}.")
        lines.append(f"Next operation: {selected['operation']} {selected['argument']}.")
    lines.append(f"Decision: {report['status']}. {report['reason']}")
    return "\n".join(lines)

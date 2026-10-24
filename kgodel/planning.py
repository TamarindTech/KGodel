"""Pure plan selection with explicit priorities and conditional applicability."""

from __future__ import annotations

from dataclasses import dataclass

from .logic import Inference, Knowledge
from .model import Atom, Bindings, KGodelError, Literal, Plan, Program, Proof, ground_query, match
from .querying import evaluate_queries, format_query_results


@dataclass(frozen=True)
class Candidate:
    goal: Atom
    plan: Plan
    bindings: Bindings
    evidence: tuple[Proof | dict, ...]
    key: tuple


@dataclass(frozen=True)
class Decision:
    selected: Candidate | None
    report: dict


def walk_results(results: list[dict]):
    for result in results:
        yield result
        yield from walk_results(result.get("results", []))


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
    fingerprint = knowledge.fingerprint()
    # Stable sorting preserves declaration order among equally ranked plans.
    plans = sorted(program.plans, key=lambda plan: -plan.priority)
    try:
        for goal in pending:
            for plan in plans:
                initial = match(plan.target, goal)
                if initial is None:
                    continue
                for bindings, evidence in logic.solve(plan.guards, initial):
                    key = (fingerprint, str(goal), plan.name, tuple(sorted(bindings.items())))
                    if key in attempts:
                        continue
                    candidate = {"goal": str(goal), "plan": plan.name, "priority": plan.priority,
                                 "bindings": bindings, "operation": plan.operation,
                                 "argument": str(plan.argument.ground(bindings)),
                                 "because": [p.as_dict() if isinstance(p, Proof) else p for p in evidence],
                                 "hypotheses": None, "status": "checking"}
                    report["candidates"].append(candidate)
                    if plan.hypotheses:
                        queries = tuple(ground_query(query, bindings) for query in plan.hypotheses)
                        assessment = evaluate_queries(knowledge, program.rules, queries,
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
                    return Decision(Candidate(goal, plan, bindings, evidence, key), report)
    except KGodelError as error:
        if report["candidates"] and report["candidates"][-1]["status"] == "checking":
            report["candidates"][-1]["status"] = "error"
        report.update(status="reasoning_error", reason=str(error))
    return Decision(None, report)


def deliberate(program: Program, knowledge: Knowledge, attempts: set[tuple] | None = None, *,
               max_hypotheses: int = 64) -> Decision:
    snapshot = knowledge.copy()
    logic = Inference(snapshot, program.rules)
    return choose_plan(program, snapshot, logic, attempts, max_hypotheses=max_hypotheses)


def format_decision(report: dict) -> str:
    lines = []
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
    if report["selected"]:
        selected = report["selected"]
        lines.append(f"Next operation: {selected['operation']} {selected['argument']}.")
    lines.append(f"Decision: {report['status']}. {report['reason']}")
    return "\n".join(lines)

"""Bounded, pure search for subset-minimal hypothetical explanations.

Candidates are explicit ground literals. Each explanation is checked against
the entire signed closure; no assumption is installed in accepted knowledge.
"""

from __future__ import annotations

from itertools import combinations

from .logic import Inference, Knowledge
from .model import KGodelError, KnowledgeConflict, Literal, Program
from .objects import ObjectSpace
from .querying import assumptions_used


MAX_CANDIDATES = 16


def find_explanations(program: Program, knowledge: Knowledge, query: Literal,
                      candidates: tuple[Literal, ...], *, max_assumptions: int = 3,
                      max_contexts: int = 256, max_solutions: int = 20,
                      max_facts: int = 10000, max_work: int = 200000) -> dict:
    """Search in cardinality order, proving minimality before returning a set.

    Complete means complete within max_assumptions. Exhaustive additionally
    means no larger candidate sets remain outside that bound. On any unresolved
    inference, stop: skipping it could make a later minimality claim unsound.
    """
    limits = dict(max_assumptions=max_assumptions, max_contexts=max_contexts,
                  max_solutions=max_solutions, max_facts=max_facts, max_work=max_work)
    for name, value in limits.items():
        minimum = 1 if name == "max_solutions" else 0
        if type(value) is not int or value < minimum:
            raise KGodelError(f"{name} must be an integer >= {minimum}.")
    if not isinstance(candidates, (tuple, list)):
        raise KGodelError("Abduction candidates must be a list or tuple of ground literals.")
    space = ObjectSpace(program)
    for literal in (query, *candidates):
        if not isinstance(literal, Literal) or literal.atom.variables:
            raise KGodelError("Abduction requires a ground query and ground candidate literals.")
        literal.ground({})
        space.validate_atom(literal.atom)
    candidates = tuple(sorted(set(candidates), key=str))
    if len(candidates) > MAX_CANDIDATES:
        raise KGodelError(f"Abduction supports at most {MAX_CANDIDATES} distinct candidates.")
    snapshot = knowledge.copy()
    rules = program.effective_rules
    inference_limits = dict(max_facts=max_facts, max_work=max_work)
    report = {
        "status": "complete", "query": str(query), "base_status": "unresolved", "base_proof": None,
        "candidates": list(map(str, candidates)), "excluded": [], "solutions": [], "conflicts": [],
        "limits": limits, "search": {"evaluated": 0, "pruned": 0, "eligible_candidates": 0,
                                     "complete_through_size": 0, "exhaustive": False},
        "stop_reason": None, "reason": "", "unresolved_assumptions": None,
    }

    def stop(status, code, reason, unresolved=None):
        report.update(status=status, stop_reason=code, reason=reason,
                      unresolved_assumptions=unresolved)
        return report

    def solution(assumptions, logic):
        proof = logic.explanation(query)
        return {"assumptions": list(map(str, assumptions)), "proof": proof.as_dict(),
                "assumptions_used": assumptions_used(proof), "minimal": True}

    try:
        base = Inference(snapshot, rules, **inference_limits)
    except KnowledgeConflict as error:
        return stop("inconsistent", "base_conflict", str(error))
    except KGodelError as error:
        return stop("error", "base_inference_error", str(error))
    report["base_status"] = base.status(query)
    proof = base.explanation(query if report["base_status"] == "true" else query.opposite())
    report["base_proof"] = proof.as_dict() if proof else None
    active = []
    for candidate in candidates:
        status = base.status(candidate)
        if status == "unknown":
            active.append(candidate)
        else:
            proof = base.explanation(candidate if status == "true" else candidate.opposite())
            report["excluded"].append({"literal": str(candidate),
                                       "reason": "already_supported" if status == "true" else "contradicted",
                                       "proof": proof.as_dict()})
    report["search"]["eligible_candidates"] = len(active)
    if report["base_status"] == "true":
        report["solutions"].append(solution((), base))
        report["search"]["exhaustive"] = True
        report["reason"] = "The query is already supported; no assumptions are needed."
        return report
    if report["base_status"] == "false":
        report["search"]["exhaustive"] = True
        report["reason"] = "The query is explicitly opposed; additive assumptions cannot replace that evidence."
        return report

    minimal_sets, inconsistent_sets = [], []
    bound = min(max_assumptions, len(active))
    for size in range(1, bound + 1):
        for assumptions in combinations(active, size):
            selected = frozenset(assumptions)
            # Signed Horn reasoning is monotonic: a known solution cannot have
            # a minimal strict superset; a conflict cannot be repaired by adding.
            if any(previous <= selected for previous in (*minimal_sets, *inconsistent_sets)):
                report["search"]["pruned"] += 1
                continue
            if report["search"]["evaluated"] >= max_contexts:
                return stop("partial", "context_limit", "The hypothetical-context budget was reached.")
            if len(report["solutions"]) >= max_solutions:
                return stop("partial", "solution_limit", "The solution limit was reached; more explanations may exist.")
            report["search"]["evaluated"] += 1
            scope = f"abduction_{report['search']['evaluated']}"
            try:
                child = snapshot.assuming(assumptions, scope)
                logic = Inference(child, rules, **inference_limits)
            except KnowledgeConflict as error:
                inconsistent_sets.append(selected)
                report["conflicts"].append({"assumptions": list(map(str, assumptions)), "error": str(error)})
                continue
            except KGodelError as error:
                return stop("partial", "hypothesis_inference_error", str(error), list(map(str, assumptions)))
            if logic.status(query) == "true":
                minimal_sets.append(selected)
                report["solutions"].append(solution(assumptions, logic))
        report["search"]["complete_through_size"] = size
    report["search"]["exhaustive"] = bound == len(active)
    report["reason"] = f"All candidate sets with at most {max_assumptions} assumptions were resolved or pruned."
    return report


def format_abduction(report: dict, *, explain: bool = False) -> str:
    lines = [f"Abduction: {report['status']}; {report['query']} (currently {report['base_status']}).",
             report["reason"]]

    def proof_lines(proof, indent="    "):
        lines.append(f"{indent}{proof['conclusion']} [{proof['source']}]")
        for premise in proof["premises"]:
            proof_lines(premise, indent + "  ")

    for number, solution in enumerate(report["solutions"], 1):
        assumptions = ", ".join(solution["assumptions"]) or "(none)"
        lines.append(f"  Explanation {number}: assume {assumptions}.")
        if explain:
            proof_lines(solution["proof"])
    if not report["solutions"]:
        lines.append("No explanation found within this search. This does not establish impossibility.")
    for excluded in report["excluded"]:
        reason = "already supported" if excluded["reason"] == "already_supported" else "contradicted by current evidence"
        lines.append(f"  Excluded {excluded['literal']}: {reason}.")
        if explain:
            proof_lines(excluded["proof"])
    if report["conflicts"]:
        lines.append(f"Rejected {len(report['conflicts'])} inconsistent assumption set(s).")
        if explain:
            for conflict in report["conflicts"]:
                lines.append(f"  {', '.join(conflict['assumptions'])}: {conflict['error']}")
    if report["unresolved_assumptions"] is not None:
        lines.append("Unresolved: " + ", ".join(report["unresolved_assumptions"]) + ".")
    if explain and report["base_status"] == "false" and report["base_proof"]:
        lines.append("Opposing evidence:")
        proof_lines(report["base_proof"])
    if report["status"] == "complete" and not report["search"]["exhaustive"]:
        lines.append("Larger assumption sets were outside the requested size bound.")
    lines.append(f"Evaluated {report['search']['evaluated']} hypothetical context(s). "
                 "Explanations are subset-minimal within the supplied candidates; accepted beliefs are unchanged.")
    return "\n".join(lines)

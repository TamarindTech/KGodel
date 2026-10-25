"""Pure comparisons of agent states and their supported conclusions."""

from __future__ import annotations

from copy import deepcopy

from .logic import Inference
from .model import KGodelError, Literal
from .parser import parse_query
from .runtime import Agent, RouteWorld


def _transition(before, after):
    return {"before": before, "after": after, "changed": before != after}


def _set_changes(before, after):
    return {"added": sorted(after - before), "removed": sorted(before - after)}


def _history(before, after, *, include_records=False):
    common = 0
    for left, right in zip(before, after):
        if left != right:
            break
        common += 1
    relation = ("equal" if common == len(before) == len(after) else
                "after_extends_before" if common == len(before) else
                "before_extends_after" if common == len(after) else "diverged")
    result = {"relation": relation, "common_prefix": common,
              "before_count": len(before), "after_count": len(after)}
    if include_records:
        result.update(before_tail=deepcopy(before[common:]), after_tail=deepcopy(after[common:]))
    return result


def _belief_changes(before, after):
    left, right = before.knowledge.facts, after.knowledge.facts
    removed, added = set(left) - set(right), set(right) - set(left)
    revisions = sorted((item for item in removed if item.opposite() in added), key=str)
    revised_after = {item.opposite() for item in revisions}
    return {
        "added": [right[item].as_dict() for item in sorted(added - revised_after, key=str)],
        "removed": [left[item].as_dict() for item in sorted(removed - set(revisions), key=str)],
        "revised": [{"before": left[item].as_dict(), "after": right[item.opposite()].as_dict()}
                    for item in revisions],
        "evidence_changed": [{"before": left[item].as_dict(), "after": right[item].as_dict()}
                             for item in sorted(set(left) & set(right), key=str) if left[item] != right[item]],
    }


def _reason(agent, max_facts, max_work):
    try:
        logic = Inference(agent.knowledge.copy(), agent.program.effective_rules, max_facts=max_facts, max_work=max_work)
        return logic, {"status": "ok", "facts": len(logic.proofs), "work": logic.work, "error": None}
    except KGodelError as error:
        return None, {"status": "error", "facts": None, "work": None, "error": str(error)}


def _answer(logic, literal):
    if logic is None:
        return {"status": "unresolved", "proof": None}
    status = logic.status(literal)
    proof = logic.explanation(literal if status == "true" else literal.opposite())
    return {"status": status, "proof": proof.as_dict() if proof else None}


def _question(before, after, literal):
    left, right = _answer(before, literal), _answer(after, literal)
    complete = before is not None and after is not None
    return {"literal": str(literal), "before": left, "after": right,
            "truth_changed": left["status"] != right["status"] if complete else None,
            "evidence_changed": left["proof"] != right["proof"] if complete else None}


def _attempts(keys):
    return [{"beliefs": list(facts), "goal": goal, "plan": plan, "bindings": dict(bindings)}
            for facts, goal, plan, bindings in sorted(keys)]


def compare_agents(before: Agent, after: Agent, *, queries=(), max_facts=10000, max_work=200000) -> dict:
    """Compare two snapshots without running plans or changing either input.

    Queries are ground literal strings. Inference failure leaves belief and world
    differences available but marks logical comparisons unresolved, never false.
    """
    if any(type(value) is not int or value < 0 for value in (max_facts, max_work)):
        raise KGodelError("Comparison inference limits must be nonnegative integers.")
    if type(before.world) is not RouteWorld or type(after.world) is not RouteWorld:
        raise KGodelError("Comparisons currently support the built-in route simulator only.")
    if isinstance(queries, str):
        raise KGodelError("Supply comparison queries as a sequence of ground literal strings.")
    questions = []
    for source in queries:
        if not isinstance(source, str):
            raise KGodelError("Comparison queries must be ground literal strings.")
        literal = parse_query(source)
        if literal.atom.variables:
            raise KGodelError("Comparison queries must be ground; variables are not supported.")
        if literal not in questions:
            questions.append(literal)
    left, left_reasoning = _reason(before, max_facts, max_work)
    right, right_reasoning = _reason(after, max_facts, max_work)
    complete = left is not None and right is not None
    sections = [field for field in ("name", "beliefs", "rules", "goals", "plans", "classes", "objects")
                if getattr(before.program, field) != getattr(after.program, field)]
    goals = []
    for goal in sorted(set(before.program.goals) | set(after.program.goals), key=str):
        row = _question(left, right, Literal(goal))
        row["before"]["declared"] = goal in before.program.goals
        row["after"]["declared"] = goal in after.program.goals
        goals.append(row)
    consequences = {"status": "complete" if complete else "unavailable", "changes": []}
    if complete:
        # Include an atom if at least one side derives either sign without a base fact.
        atoms = {literal.atom for logic, agent in ((left, before), (right, after))
                 for literal in logic.proofs if literal not in agent.knowledge.facts
                 and literal.atom.lookup_class is None}
        for atom in sorted(atoms, key=str):
            row = _question(left, right, Literal(atom))
            if row["truth_changed"] or row["evidence_changed"]:
                consequences["changes"].append(row)
    world = {field: _transition(getattr(before.world, field), getattr(after.world, field))
             for field in ("position", "action_calls", "observation_calls")}
    world.update({field: _set_changes(getattr(before.world, field), getattr(after.world, field))
                  for field in ("edges", "nodes", "blocked")})
    # Tuples in the simulator are represented by arrays in both the API and JSON.
    world["edges"] = {kind: [list(edge) for edge in edges] for kind, edges in world["edges"].items()}
    intention = _transition(before.intention.as_dict() if before.intention else None,
                            after.intention.as_dict() if after.intention else None)
    intention["changed"] = before.intention != after.intention
    histories = {
        "operations": _history(before.events, after.events, include_records=True),
        "decisions": _history(before.decisions, after.decisions),
        "intentions": _history(before.intention_events, after.intention_events, include_records=True),
    }
    attempts = {"added": _attempts(after.attempts - before.attempts),
                "removed": _attempts(before.attempts - after.attempts)}
    outcomes = _transition(list(before._last_outcome) if before._last_outcome else None,
                           list(after._last_outcome) if after._last_outcome else None)
    identifiers = _transition(before._next_intention_id, after._next_intention_id)
    changed = (bool(sections) or before.knowledge.facts != after.knowledge.facts
               or before.world.__dict__ != after.world.__dict__ or intention["changed"]
               or any(history["relation"] != "equal" for history in histories.values())
               or before.attempts != after.attempts or outcomes["changed"] or identifiers["changed"])
    return {"format": "kgodel-comparison", "schema_version": 1,
            "status": "ok" if complete else "partial", "changed": changed,
            "program": {"before": before.program.name, "after": after.program.name,
                        "changed_sections": sections},
            "reasoning": {"before": left_reasoning, "after": right_reasoning},
            "beliefs": _belief_changes(before, after), "consequences": consequences,
            "goals": goals, "queries": [_question(left, right, question) for question in questions],
            "world": world, "intention": intention, "history": histories,
            "attempts": attempts, "last_outcome": outcomes, "next_intention_id": identifiers}


def format_comparison(report: dict, *, explain=False) -> str:
    lines = [f"KGodel comparison: {report['program']['before']} -> {report['program']['after']}",
             "State changed." if report["changed"] else "No state changes."]
    if report["program"]["changed_sections"]:
        lines.append("Program changed: " + ", ".join(report["program"]["changed_sections"]) + ".")
    for side, reasoning in report["reasoning"].items():
        if reasoning["status"] == "error":
            lines.append(f"Reasoning {side}: {reasoning['error']}")
    lines.append("Base beliefs:")
    beliefs = report["beliefs"]
    if not any(beliefs.values()):
        lines.append("  Unchanged.")
    for kind, label in (("added", "+"), ("removed", "-")):
        for proof in beliefs[kind]:
            lines.append(f"  {label} {proof['conclusion']} [{proof['source']}]")
    for pair in beliefs["revised"]:
        lines.append(f"  Revised {pair['before']['conclusion']} -> {pair['after']['conclusion']} "
                     f"[{pair['after']['source']}]")
    for pair in beliefs["evidence_changed"]:
        lines.append(f"  Evidence changed for {pair['after']['conclusion']}: "
                     f"{pair['before']['source']} -> {pair['after']['source']}")

    def proof_lines(proof, depth=0):
        if proof is None:
            return []
        rows = ["      " + "  " * depth + f"{proof['conclusion']} [{proof['source']}]"]
        for premise in proof["premises"]:
            rows.extend(proof_lines(premise, depth + 1))
        return rows

    for title, rows in (("Goals", report["goals"]), ("Queries", report["queries"]),
                        ("Derived conclusions", report["consequences"]["changes"])):
        if title == "Queries" and not rows:
            continue
        lines.append(title + ":")
        if not rows:
            lines.append("  Unavailable: reasoning did not complete on both sides."
                         if title == "Derived conclusions" and report["status"] == "partial" else "  Unchanged.")
        for row in rows:
            left, right = row["before"], row["after"]
            note = " (evidence changed)" if row["evidence_changed"] and not row["truth_changed"] else ""
            lines.append(f"  {row['literal']}: {left['status']} -> {right['status']}{note}")
            if "declared" in left and left["declared"] != right["declared"]:
                lines.append("    Goal declaration " + ("added." if right["declared"] else "removed."))
            if explain:
                for side in ("before", "after"):
                    lines.append(f"    {side} evidence:")
                    lines.extend(proof_lines(row[side]["proof"]) or ["      No resolved evidence."])
    lines.append("World:")
    world_changed = False
    for field, change in report["world"].items():
        if "changed" in change:
            if change["changed"]:
                world_changed = True
                lines.append(f"  {field}: {change['before']} -> {change['after']}")
        elif change["added"] or change["removed"]:
            world_changed = True
            lines.append(f"  {field}: added {change['added']}; removed {change['removed']}")
    if not world_changed:
        lines.append("  Unchanged.")
    lines.append("Active intention:")
    for side in ("before", "after"):
        active = report["intention"][side]
        label = (f"{active['plan']} {active['bindings']} for {active['goal']}; "
                 f"step {active['next_step']} of {active['total_steps']} (id {active['id']})") if active else "none"
        lines.append(f"  {side}: {label}")
    if report["intention"]["changed"] and report["intention"]["before"] == report["intention"]["after"]:
        lines.append("  Commitment evidence or attempt context changed.")
    for kind, history in report["history"].items():
        lines.append(f"{kind.capitalize()} history: {history['relation']}; shared prefix {history['common_prefix']}; "
                     f"counts {history['before_count']} -> {history['after_count']}.")
    for side in ("before", "after"):
        for event in report["history"]["operations"][side + "_tail"]:
            lines.append(f"  {side} {event['step']}. {event['operation']} {event['argument']}: {event['detail']}")
        for event in report["history"]["intentions"][side + "_tail"]:
            lines.append(f"  {side} intention {event['id']} ({event['plan']}): {event['status']}. {event['reason']}")
    if report["last_outcome"]["changed"]:
        lines.append("Last run:")
        for side in ("before", "after"):
            outcome = report["last_outcome"][side]
            lines.append(f"  {side}: {outcome[0]}. {outcome[1]}" if outcome else f"  {side}: not run yet.")
    attempts = report["attempts"]
    lines.append(f"Attempt records: {len(attempts['added'])} added, {len(attempts['removed'])} removed.")
    if report["next_intention_id"]["changed"]:
        change = report["next_intention_id"]
        lines.append(f"Next intention id: {change['before']} -> {change['after']}.")
    lines.append(f"Comparison: {report['status']}.")
    return "\n".join(lines)

"""Versioned, self-contained JSON checkpoints for the local route simulator.

Loading restores data only: it never invokes observations or actions. Checkpoints
are local experiment files, not authenticated evidence or external-tool receipts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from . import __version__
from .logic import Knowledge
from .model import KGodelError, Literal, Proof, ProveQuery
from .parser import parse, parse_query
from .planning import Candidate, Intention, format_decision
from .runtime import Agent, RouteWorld, format_trace


FORMAT = "kgodel-session"
SCHEMA_VERSION = 1
MAX_BYTES = 32 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise KGodelError(f"Invalid session: {message}.")


def _fields(value, names):
    _require(isinstance(value, dict) and set(value) == set(names.split()),
             f"expected fields {names}")


def _integer(value, minimum=0):
    _require(type(value) is int and value >= minimum, f"expected integer >= {minimum}")
    return value


def _string(value):
    _require(isinstance(value, str), "expected a string")
    return value


def _literal(value):
    literal = parse_query(_string(value))
    _require(not literal.atom.variables, "stored beliefs and goals must be ground")
    return literal


def _query_source(query):
    if isinstance(query, ProveQuery):
        return f"prove({query.literal})."
    return ("suppose(" + ", ".join(map(str, query.assumptions)) + ") { "
            + " ".join(_query_source(child) for child in query.body) + " }")


def program_source(program):
    """Render executable syntax; reparsing also validates API-created programs."""
    lines = [f"agent {program.name} {{"]
    lines += [f"belief {belief}." for belief in program.beliefs]
    lines += [f"rule {rule.head} :- {', '.join(map(str, rule.body))}." for rule in program.rules]
    lines += [f"goal {goal}." for goal in program.goals]
    for plan in program.plans:
        parameters = "(" + ", ".join(plan.parameters) + ")" if plan.parameters else ""
        lines += [f"plan {plan.name}{parameters} for {plan.target} priority {plan.priority} {{",
                  "when " + ", ".join(map(str, plan.guards)) + "."]
        lines += [_query_source(query) for query in plan.hypotheses]
        for step in plan.steps:
            if step.requirements:
                lines.append("require " + ", ".join(map(str, step.requirements)) + ".")
            lines.append(f"{step.operation} {step.argument}.")
        lines.append("}")
    lines.append("}")
    source = "\n".join(lines)
    _require(parse(source) == program, "program cannot be represented without changing its meaning")
    return source


def _proof(value, depth=0):
    _require(depth < 128, "proof nesting exceeds 128")
    _fields(value, "conclusion source premises")
    _require(isinstance(value["premises"], list), "proof premises must be a list")
    return Proof(_literal(value["conclusion"]), _string(value["source"]),
                 tuple(_proof(child, depth + 1) for child in value["premises"]))


def _evidence(values):
    _require(isinstance(values, list), "evidence must be a list")
    result = []
    for item in values:
        if isinstance(item, dict) and set(item) == {"unknown"}:
            literal = _literal(item["unknown"])
            _require(not literal.negative, "unknown evidence requires an atom")
            result.append({"unknown": str(literal)})
        else:
            result.append(_proof(item))
    return tuple(result)


def _instance(agent, goal, plan_name, bindings):
    goal = _literal(goal)
    _require(not goal.negative and goal.atom in agent.program.goals, "unknown goal")
    plan = next((item for item in agent.program.plans if item.name == plan_name), None)
    _require(plan is not None, "unknown plan")
    _require(isinstance(bindings, dict) and set(bindings) == set(plan.parameters)
             and all(isinstance(value, str) for value in bindings.values()), "invalid plan bindings")
    _require(plan.target.ground(bindings) == goal.atom, "plan bindings do not match the goal")
    return goal.atom, plan, dict(bindings)


def _attempt(agent, value):
    _require(isinstance(value, list) and len(value) == 4, "invalid attempt record")
    fingerprint, goal, plan_name, pairs = value
    _require(isinstance(fingerprint, list), "invalid belief fingerprint")
    literals = [_literal(item) for item in fingerprint]
    knowledge = Knowledge(tuple(literals))
    _require(list(knowledge.fingerprint()) == fingerprint, "noncanonical belief fingerprint")
    _require(isinstance(pairs, list) and all(isinstance(pair, list) and len(pair) == 2
             and all(isinstance(item, str) for item in pair) for pair in pairs), "invalid binding pairs")
    _require(pairs == [list(pair) for pair in sorted(dict(pairs).items())], "noncanonical binding pairs")
    _instance(agent, goal, plan_name, dict(pairs))
    return tuple(fingerprint), goal, plan_name, tuple(tuple(pair) for pair in pairs)


def _validate_history(agent):
    """Check execution references without replaying simulator operations."""
    for decision in agent.decisions:
        _require(isinstance(decision, dict), "invalid decision record")
        format_decision(decision)
    prior_decision = 0
    committed, released, cursors = {}, {}, {}
    previous_step = 0
    for event in agent.intention_events:
        _require(isinstance(event, dict), "invalid intention event")
        identifier = _integer(event["id"], 1)
        goal, plan, bindings = _instance(agent, event["goal"], event["plan"], event["bindings"])
        after = _integer(event["after_step"])
        _require(previous_step <= after <= len(agent.events), "invalid intention event order")
        previous_step = after
        _require(event["total_steps"] == len(plan.steps), "incorrect intention length")
        _string(event["reason"])
        if event["status"] == "committed":
            _require(identifier == len(committed) + 1 and event["next_step"] == 1,
                     "invalid intention commitment")
            _require(set(committed) == set(released), "overlapping intention commitments")
            committed[identifier] = (goal, plan, bindings, after)
            _require(any(key[1:] == (str(goal), plan.name, tuple(sorted(bindings.items())))
                         for key in agent.attempts), "commitment has no recorded attempt")
        else:
            _require(identifier in committed and identifier not in released
                     and committed[identifier][:3] == (goal, plan, bindings)
                     and event["status"] in {"completed", "operation_failed", "requirements_failed", "goal_satisfied"},
                     "invalid intention release")
            released[identifier] = event
    for index, event in enumerate(agent.events, 1):
        _require(isinstance(event, dict), "invalid operation record")
        _require(_integer(event["step"], 1) == index, "invalid operation sequence")
        decision = _integer(event["decision"], 1)
        _require(prior_decision < decision <= len(agent.decisions), "invalid decision reference")
        prior_decision = decision
        identifier = _integer(event["intention"], 1)
        _require(identifier in committed, "operation has no intention commitment")
        goal, plan, bindings = _instance(agent, event["goal"], event["plan"], event["bindings"])
        _require(committed[identifier][:3] == (goal, plan, bindings), "operation changed intention bindings")
        cursor = _integer(event["plan_step"], 1)
        _require(cursor == cursors.get(identifier, 0) + 1 and cursor <= len(plan.steps), "invalid operation cursor")
        cursors[identifier] = cursor
        _require(index == committed[identifier][3] + cursor, "intention operations are not consecutive")
        step = plan.steps[cursor - 1]
        _require(event["operation"] == step.operation and event["argument"] == str(step.argument.ground(bindings))
                 and event["total_steps"] == len(plan.steps) and event["priority"] == plan.priority,
                 "operation does not match its plan")
        _require(type(event["success"]) is bool, "operation success must be boolean")
        _string(event["detail"])
        _evidence(event["because"])
        _require(isinstance(event["belief_changes"], list), "invalid belief changes")
        for change in event["belief_changes"]:
            _fields(change, "accepted source retracted changed")
            accepted = _literal(change["accepted"])
            _string(change["source"])
            _require(type(change["changed"]) is bool, "invalid belief change flag")
            if change["retracted"] is not None:
                _require(_literal(change["retracted"]) == accepted.opposite(), "invalid belief retraction")
    for identifier, event in released.items():
        count = cursors.get(identifier, 0)
        _require(count > 0 and event["after_step"] == committed[identifier][3] + count,
                 "release does not follow the intention's operations")
        last = agent.events[event["after_step"] - 1]
        if event["status"] == "completed":
            _require(count == event["total_steps"] and event["next_step"] is None and last["success"],
                     "invalid completed intention")
        elif event["status"] == "operation_failed":
            _require(event["next_step"] == count and not last["success"], "invalid failed intention")
        else:
            _require(event["next_step"] == count + 1 and last["success"], "invalid cancelled intention")
    _require(agent._next_intention_id == len(committed) + 1, "incorrect next intention id")
    active = agent.intention
    _require(set(committed) - set(released) == ({active.id} if active else set()), "missing or extra active intention")
    if active:
        candidate = active.candidate
        _require(committed[active.id][:3] == (candidate.goal, candidate.plan, candidate.bindings)
                 and cursors.get(active.id) == active.next_step, "active intention cursor disagrees with history")
        _require(agent.events and agent.events[-1]["intention"] == active.id and agent.events[-1]["success"],
                 "active intention must follow a successful operation")
    _require(agent.world.action_calls == sum(event["operation"] == "act" for event in agent.events)
             and agent.world.observation_calls == sum(event["operation"] == "observe" for event in agent.events),
             "world counters disagree with operation history")


def _restore(data):
    _fields(data, "format schema_version kgodel_version program world beliefs attempts events decisions intention intention_events next_intention_id last_outcome")
    _require(data["format"] == FORMAT, "not a KGodel session checkpoint")
    _require(type(data["schema_version"]) is int and data["schema_version"] == SCHEMA_VERSION,
             "unsupported session schema version")
    _string(data["kgodel_version"])
    program = parse(_string(data["program"]))
    world_data = data["world"]
    _fields(world_data, "position edges blocked nodes action_calls observation_calls")
    nodes = world_data["nodes"]
    _require(isinstance(nodes, list) and all(isinstance(node, str) for node in nodes), "invalid world nodes")
    # A node can survive even when it no longer occurs in the current position or edges.
    world = RouteWorld(world_data["position"], world_data["edges"], [])
    _require(world.nodes <= set(nodes), "world nodes omit a position or edge endpoint")
    blocked = world_data["blocked"]
    _require(isinstance(blocked, list) and all(isinstance(node, str) for node in blocked)
             and set(blocked) <= set(nodes), "invalid blocked locations")
    world.nodes, world.blocked = set(nodes), set(blocked)
    world.action_calls = _integer(world_data["action_calls"])
    world.observation_calls = _integer(world_data["observation_calls"])
    agent = Agent(program, world)
    _require(isinstance(data["beliefs"], list), "beliefs must be a list")
    proofs = [_proof(value) for value in data["beliefs"]]
    agent.knowledge = Knowledge(tuple(proof.conclusion for proof in proofs))
    _require(len(agent.knowledge.facts) == len(proofs), "duplicate stored beliefs")
    agent.knowledge.facts = {proof.conclusion: proof for proof in proofs}
    _require(isinstance(data["attempts"], list), "attempts must be a list")
    agent.attempts = {_attempt(agent, value) for value in data["attempts"]}
    for name in ("events", "decisions", "intention_events"):
        _require(isinstance(data[name], list), f"{name} must be a list")
        setattr(agent, name, data[name])
    agent._next_intention_id = _integer(data["next_intention_id"], 1)
    active = data["intention"]
    if active is not None:
        _fields(active, "id goal plan bindings next_step total_steps key evidence")
        goal, plan, bindings = _instance(agent, active["goal"], active["plan"], active["bindings"])
        cursor = _integer(active["next_step"], 2) - 1
        _require(cursor < len(plan.steps) and active["total_steps"] == len(plan.steps), "invalid active intention cursor")
        key = _attempt(agent, active["key"])
        _require(key in agent.attempts and key[1:] == (str(goal), plan.name, tuple(sorted(bindings.items()))),
                 "active intention has no matching attempt")
        agent.intention = Intention(_integer(active["id"], 1),
                                    Candidate(goal, plan, bindings, _evidence(active["evidence"]), key), cursor)
    outcome = data["last_outcome"]
    if outcome is not None:
        _require(isinstance(outcome, list) and len(outcome) == 2 and outcome[0] in
                 {"achieved", "step_limit", "stuck", "reasoning_error"}, "invalid last outcome")
        agent._last_outcome = (outcome[0], _string(outcome[1]))
    _require(not agent.events or outcome is not None, "operations require a recorded outcome")
    _validate_history(agent)
    record = agent.execution_record()
    if record:
        format_trace(record)
    return agent


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON field {key}")
        result[key] = value
    return result


def loads_session(source: str) -> Agent:
    """Restore a supported checkpoint; never execute simulator operations."""
    try:
        _require(len(source.encode("utf-8")) <= MAX_BYTES, "checkpoint exceeds 32 MiB")
        data = json.loads(source, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: _require(False, f"invalid JSON constant {value}"))
        return _restore(data)
    except KGodelError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError) as error:
        raise KGodelError(f"Invalid session checkpoint: {error}.") from error


def dumps_session(agent: Agent) -> str:
    """Snapshot between run calls. No decision, belief, or world state is changed."""
    _require(type(agent.world) is RouteWorld, "only the built-in route simulator supports checkpoints")
    world = agent.world
    active = None
    if agent.intention:
        candidate = agent.intention.candidate
        active = {**agent.intention.as_dict(), "key": candidate.key,
                  "evidence": [item.as_dict() if isinstance(item, Proof) else item for item in candidate.evidence]}
    data = {"format": FORMAT, "schema_version": SCHEMA_VERSION, "kgodel_version": __version__,
            "program": program_source(agent.program),
            "world": {"position": world.position, "edges": sorted(world.edges),
                      "blocked": sorted(world.blocked), "nodes": sorted(world.nodes),
                      "action_calls": world.action_calls, "observation_calls": world.observation_calls},
            "beliefs": [proof.as_dict() for proof in agent.knowledge.facts.values()],
            "attempts": sorted(agent.attempts), "events": agent.events, "decisions": agent.decisions,
            "intention": active, "intention_events": agent.intention_events,
            "next_intention_id": agent._next_intention_id, "last_outcome": agent._last_outcome}
    try:
        source = json.dumps(data, indent=2, allow_nan=False) + "\n"
    except (ValueError, TypeError, RecursionError) as error:
        raise KGodelError(f"Cannot serialize session: {error}.") from error
    loads_session(source)  # Reject unrestorable state before touching an existing file.
    return source


def save_session(agent: Agent, path: str | Path):
    """Atomically replace the named checkpoint after validating the complete snapshot."""
    source = dumps_session(agent)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, prefix=f".{target.name}.", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(source)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def load_session(path: str | Path) -> Agent:
    with Path(path).open("rb") as stream:
        source = stream.read(MAX_BYTES + 1)
    _require(len(source) <= MAX_BYTES, "checkpoint exceeds 32 MiB")
    try:
        return loads_session(source.decode("utf-8-sig"))
    except UnicodeError as error:
        raise KGodelError("Invalid session checkpoint: expected UTF-8 JSON.") from error

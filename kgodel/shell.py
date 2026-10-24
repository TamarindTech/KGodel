"""An interactive session for examining a simulated agent."""

from __future__ import annotations

import json
from pathlib import Path

from . import __version__
from .model import KGodelError, Literal
from .planning import format_decision
from .querying import format_query_results
from .runtime import Agent, format_trace
from .sessions import save_session


HELP = """Queries inspect current beliefs without executing operations:
  clear(forest).
  suppose(clear(forest)) { prove(clear(forest)). }
  :query EXPRESSION       Query current beliefs (also accepts bare expressions)
  :explain EXPRESSION     Include supporting proofs

Commands:
  :preview               Preview the next decision without changing the agent
  :step [N]              Perform up to N further operations (default: 1)
  :run [N]               Perform up to N further operations (default: 50)
  :status                Show current goals and the active intention
  :beliefs               Show accepted base beliefs and their sources
  :trace                 Show the most recent cumulative execution record
  :save PATH             Save that execution record as JSON
  :checkpoint PATH       Save the agent and world for a later restart
  :help                  Show this help
  :quit                  End this session

Enter each request on one line. Use :checkpoint before exiting to save progress."""


class ShellSession:
    def __init__(self, agent: Agent, *, max_hypotheses: int = 64):
        if max_hypotheses < 0:
            raise KGodelError("The hypothesis budget must be nonnegative.")
        self.agent = agent
        self.max_hypotheses = max_hypotheses
        self.last_result = agent.execution_record()

    def status(self) -> str:
        logic = self.agent.inference()
        goals = [(str(goal), logic.status(Literal(goal))) for goal in self.agent.program.goals]
        lines = [f"Agent {self.agent.program.name}: " +
                 ("all goals supported." if all(status == "true" for _, status in goals)
                  else "goals still pending."),
                 f"Operations: {len(self.agent.events)} "
                 f"({self.agent.world.action_calls} actions, {self.agent.world.observation_calls} observations)."]
        lines.extend(f"  {goal}: {status}" for goal, status in goals)
        if self.agent.intention:
            active = self.agent.intention.as_dict()
            lines.append(f"Intention {active['id']}: {active['plan']} for {active['goal']}; "
                         f"next step {active['next_step']} of {active['total_steps']}.")
        else:
            lines.append("No active intention.")
        return "\n".join(lines)

    def execute(self, line: str) -> str | None:
        """Execute one request; None means quit. Queries and inspections are pure."""
        line = line.strip()
        if not line:
            return ""
        if not line.startswith(":"):
            return format_query_results(self.agent.query(line, max_contexts=self.max_hypotheses))
        parts = line.split(maxsplit=1)
        command, argument = parts[0], parts[1].strip() if len(parts) > 1 else ""
        no_arguments = {":help", ":quit", ":preview", ":status", ":beliefs", ":trace"}
        if command in no_arguments and argument:
            raise KGodelError(f"{command} does not take an argument.")
        if command == ":quit":
            return None
        if command == ":help":
            return HELP
        if command == ":status":
            return self.status()
        if command == ":preview":
            return format_decision(self.agent.deliberate(max_hypotheses=self.max_hypotheses))
        if command == ":beliefs":
            return "\n".join(f"{literal} [{proof.source}]" for literal, proof in
                             sorted(self.agent.knowledge.facts.items(), key=lambda item: str(item[0]))) or "No base beliefs."
        if command in (":query", ":explain"):
            if not argument:
                raise KGodelError(f"{command} requires a query expression.")
            return format_query_results(self.agent.query(argument, max_contexts=self.max_hypotheses),
                                        explain=command == ":explain")
        if command in (":step", ":run"):
            if argument and (not argument.isascii() or not argument.isdecimal()):
                raise KGodelError("The operation budget must be a nonnegative integer.")
            try:
                budget = int(argument) if argument else (1 if command == ":step" else 50)
            except ValueError as error:
                raise KGodelError("The operation budget is too large to read.") from error
            previous = len(self.agent.events)
            previous_intentions = len(self.agent.intention_events)
            result = self.agent.run(budget, max_hypotheses=self.max_hypotheses)
            self.last_result = result
            lines = [f"{event['step']}. {event['operation']} {event['argument']}: {event['detail']}"
                     for event in result["events"][previous:]]
            for change in result["intention_events"][previous_intentions:]:
                if change["status"] not in ("committed", "completed"):
                    lines.append(f"Released intention {change['id']}: {change['status']}.")
            lines.append(f"Result: {result['status']}. {result['reason']}")
            if result["active_intention"]:
                active = result["active_intention"]
                lines.append(f"Next: {active['plan']} step {active['next_step']} of {active['total_steps']}.")
            return "\n".join(lines)
        if command == ":checkpoint":
            if len(argument) >= 2 and argument[0] == argument[-1] and argument[0] in "\"'":
                argument = argument[1:-1]
            if not argument:
                raise KGodelError(":checkpoint requires a file path.")
            save_session(self.agent, argument)
            return f"Saved resumable session to {argument}."
        if command in (":trace", ":save"):
            if self.last_result is None:
                raise KGodelError("No execution record yet. Use :step or :run first.")
            if command == ":trace":
                return format_trace(self.last_result)
            if not argument:
                raise KGodelError(":save requires a file path.")
            if len(argument) >= 2 and argument[0] == argument[-1] and argument[0] in "\"'":
                argument = argument[1:-1]
            if not argument:
                raise KGodelError(":save requires a file path.")
            target = Path(argument)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(self.last_result, indent=2) + "\n", encoding="utf-8")
            return f"Saved execution record to {target}."
        raise KGodelError(f"Unknown command {command!r}. Use :help to see available commands.")


def run_shell(agent: Agent, *, max_hypotheses: int = 64) -> int:
    session = ShellSession(agent, max_hypotheses=max_hypotheses)
    print(f"KGodel {__version__} | interactive agent {agent.program.name}")
    print("Use :help for commands. Queries are pure; :step and :run execute simulator operations.")
    try:
        while True:
            try:
                line = input("kgodel> ")
            except EOFError:
                print()
                return 0
            try:
                response = session.execute(line)
                if response is None:
                    return 0
                if response:
                    print(response)
            except (KGodelError, OSError) as error:
                print(f"KGodel error: {error}")
    except KeyboardInterrupt:
        print("\nSession interrupted.")
        return 130

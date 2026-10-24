from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .logic import Inference, Knowledge
from .model import KGodelError, Proof
from .parser import parse, parse_query
from .runtime import Agent, RouteWorld, format_trace


def save(path: str, content: str):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kgodel", description="KGodel experimental agent logic language")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Parse a program and validate its initial knowledge")
    check.add_argument("program")
    for name in ("query", "explain"):
        command = commands.add_parser(name, help="Query initial beliefs without executing any actions")
        command.add_argument("program")
        command.add_argument("query")
    run = commands.add_parser("run", help="Run an agent in the local route simulator")
    run.add_argument("program")
    run.add_argument("--world", help="World JSON; defaults to the program's .world.json companion")
    run.add_argument("--max-steps", type=int, default=50)
    run.add_argument("--trace-json", help="Save the structured decision and proof record")
    run.add_argument("--trace-text", help="Save the human-readable decision record")
    args = parser.parse_args(argv)
    try:
        program_path = Path(args.program)
        program = parse(program_path.read_text(encoding="utf-8-sig"))
        if args.command == "run":
            world_path = Path(args.world) if args.world else program_path.with_suffix(".world.json")
            world = RouteWorld.from_json(world_path.read_text(encoding="utf-8-sig"))
            result = Agent(program, world).run(args.max_steps)
            rendered = format_trace(result)
            print(rendered)
            if args.trace_json:
                save(args.trace_json, json.dumps(result, indent=2))
            if args.trace_text:
                save(args.trace_text, rendered)
            return 0 if result["status"] == "achieved" else 1

        logic = Inference(Knowledge(program.beliefs), program.rules)
        if args.command == "check":
            print(f"Valid: agent {program.name}; {len(program.beliefs)} beliefs, "
                  f"{len(program.rules)} rules, {len(program.goals)} goals, {len(program.plans)} plans.")
            return 0
        query = parse_query(args.query)
        if query.atom.variables:
            solutions = list(logic.solve((query,)))
            if not solutions:
                print("No supported bindings. This does not establish explicit falsity.")
            for bindings, evidence in solutions:
                print(", ".join(f"{name} = {value}" for name, value in sorted(bindings.items())))
                if args.command == "explain":
                    for proof in evidence:
                        if isinstance(proof, Proof):
                            print("\n".join(proof.lines()))
        else:
            status = logic.status(query)
            print(f"{status}: {query}")
            if args.command == "explain":
                proof = logic.explanation(query if status == "true" else query.opposite())
                if proof:
                    print("\n".join(proof.lines()))
                else:
                    print("Neither the statement nor its explicit negation has supporting evidence.")
        return 0
    except (KGodelError, OSError) as error:
        print(f"KGodel error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .abduction import find_explanations, format_abduction
from .comparison import compare_agents, format_comparison
from .demos import DEFAULT_DEMO, DEMOS, load_demo
from .diagnostics import diagnose, format_diagnostics
from .logic import Inference, Knowledge
from .loading import format_imports, load_project
from .model import KGodelError
from .objects import ObjectSpace, format_objects
from .parser import parse_abduction, parse_queries, parse_query
from .planning import deliberate, format_decision
from .projects import TEMPLATES, create_project
from .querying import evaluate_queries, format_query_results
from .runtime import Agent, RouteWorld, format_trace
from .sessions import load_session, save_session
from .shell import run_shell


def save(path: str, content: str):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content + "\n", encoding="utf-8")


def validate_outputs(args: argparse.Namespace, *, sources=()):
    """Reject path aliases before execution or export can damage an input."""
    inputs = [(name, Path(value)) for name in ("program", "world", "file", "session", "resume", "before", "after")
              if (value := getattr(args, name, None))]
    inputs.extend(("module", Path(value)) for value in sources)
    if args.command == "run" and not args.world:
        inputs.append(("world", Path(args.program).with_suffix(".world.json")))
    outputs = [(name, Path(value)) for name in ("result_json", "trace_json", "trace_text", "checkpoint")
               if (value := getattr(args, name, None))]

    def same(left, right):
        return left.resolve() == right.resolve() or (left.exists() and right.exists() and left.samefile(right))

    for index, (name, target) in enumerate(outputs):
        for source_name, source in inputs:
            if same(target, source) and not (
                    args.command == "resume" and name == "checkpoint" and source_name == "session"):
                raise KGodelError("Output must not overwrite an input file.")
        if any(same(target, other) for _, other in outputs[:index]):
            raise KGodelError("Output files must use distinct paths.")


def protect_sources(args, project):
    validate_outputs(args, sources=(project.root / source.path for source in project.sources))


def execution_options(command: argparse.ArgumentParser):
    command.add_argument("--max-steps", type=int, default=50)
    command.add_argument("--max-hypotheses", type=int, default=64,
                         help="Maximum hypothetical contexts per decision (default: 64)")
    command.add_argument("--trace-json", help="Save the structured decision and proof record")
    command.add_argument("--trace-text", help="Save the human-readable decision record")
    command.add_argument("--checkpoint", help="Save a resumable session after this run")


def execute_agent(agent: Agent, args: argparse.Namespace) -> int:
    result = agent.run(args.max_steps, max_hypotheses=args.max_hypotheses)
    rendered = format_trace(result)
    print(rendered)
    if args.trace_json:
        save(args.trace_json, json.dumps(result, indent=2))
    if args.trace_text:
        save(args.trace_text, rendered)
    if args.checkpoint:
        save_session(agent, args.checkpoint)
    return 0 if result["status"] == "achieved" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kgodel", description="KGodel experimental agent logic language")
    parser.add_argument("--version", action="version", version=f"KGodel {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a starter project in a new folder")
    init.add_argument("directory", help="New directory; its parent must exist")
    init.add_argument("--template", choices=TEMPLATES, default="route")
    doctor = commands.add_parser("doctor", help="Check this Python installation and a bundled simulation")
    doctor.add_argument("--json", action="store_true", help="Print machine-readable diagnostics")
    demo = commands.add_parser("demo", help="Run a bundled experiment from any working directory")
    demo.add_argument("name", nargs="?", choices=DEMOS, help=f"Default: {DEFAULT_DEMO}")
    demo.add_argument("--list", action="store_true", help="List experiments without running one")
    execution_options(demo)
    shell = commands.add_parser("shell", help="Interact with a live simulated agent")
    source = shell.add_mutually_exclusive_group(required=True)
    source.add_argument("program", nargs="?")
    source.add_argument("--demo", choices=DEMOS, help="Use a bundled experiment")
    source.add_argument("--resume", metavar="SESSION", help="Open a saved session without advancing it")
    shell.add_argument("--world", help="World JSON for a program file")
    shell.add_argument("--max-hypotheses", type=int, default=64,
                       help="Maximum hypothetical contexts per request or decision (default: 64)")
    check = commands.add_parser("check", help="Parse a program and validate its initial knowledge")
    check.add_argument("program")
    imports = commands.add_parser("imports", help="Inspect and validate a program's local module dependencies")
    imports.add_argument("program")
    imports.add_argument("--result-json", help="Save dependency paths and source hashes")
    objects = commands.add_parser("objects", help="Inspect classes, inherited methods, and object configuration")
    objects.add_argument("program")
    preview = commands.add_parser("deliberate", help="Preview plan selection without loading a world")
    preview.add_argument("program")
    preview.add_argument("--max-hypotheses", type=int, default=64)
    preview.add_argument("--result-json", help="Save considered plans and conditional evidence")
    for name in ("query", "explain"):
        command = commands.add_parser(name, help="Query initial beliefs without executing any actions")
        command.add_argument("program")
        request = command.add_mutually_exclusive_group(required=True)
        request.add_argument("query", nargs="?", help="A query with comma/semicolon, prove expression, or suppose block")
        request.add_argument("--file", help="Read a sequence of queries from a .kgq file")
        command.add_argument("--result-json", help="Save query answers, assumptions, and proofs")
    run = commands.add_parser("run", help="Run an agent in the local route simulator")
    run.add_argument("program")
    run.add_argument("--world", help="World JSON; defaults to the program's .world.json companion")
    execution_options(run)
    resume = commands.add_parser("resume", help="Continue a saved session at its next unfinished operation")
    resume.add_argument("session")
    execution_options(resume)
    compare = commands.add_parser("compare", help="Compare saved beliefs, proofs, plans, and world state")
    compare.add_argument("before", help="Baseline checkpoint")
    compare.add_argument("after", help="Checkpoint to compare with the baseline")
    compare.add_argument("--query", action="append", default=[], help="Ground literal to compare; repeatable")
    compare.add_argument("--explain", action="store_true", help="Print supporting or opposing proof trees")
    compare.add_argument("--max-facts", type=int, default=10000)
    compare.add_argument("--max-work", type=int, default=200000)
    compare.add_argument("--result-json", help="Save the comparison report")
    abduce = commands.add_parser("abduce", help="Find minimal assumptions that would support a ground query")
    source = abduce.add_mutually_exclusive_group(required=True)
    source.add_argument("--program", help="Inspect initial knowledge without loading a world")
    source.add_argument("--demo", choices=DEMOS, help="Inspect a bundled experiment without running it")
    source.add_argument("--resume", metavar="SESSION", help="Inspect current beliefs from a checkpoint")
    request = abduce.add_mutually_exclusive_group(required=True)
    request.add_argument("query", nargs="?", help="Ground literal to explain hypothetically")
    request.add_argument("--file", help="Read GOAL from (CANDIDATE, ...) from a .kga file")
    abduce.add_argument("--assume", action="append", default=[], help="Candidate ground assumption; repeatable")
    abduce.add_argument("--max-assumptions", type=int, default=3, help="Maximum assumptions per explanation (default: 3)")
    abduce.add_argument("--max-contexts", type=int, default=256, help="Maximum hypothetical contexts (default: 256)")
    abduce.add_argument("--max-solutions", type=int, default=20)
    abduce.add_argument("--max-facts", type=int, default=10000)
    abduce.add_argument("--max-work", type=int, default=200000)
    abduce.add_argument("--explain", action="store_true", help="Include full conditional proofs")
    abduce.add_argument("--result-json", help="Save explanations, conflicts, limits, and search coverage")
    args = parser.parse_args(argv)
    try:
        validate_outputs(args)
        if args.command == "doctor":
            report = diagnose()
            print(json.dumps(report, indent=2) if args.json else format_diagnostics(report))
            return 2 if report["status"] == "error" else (1 if report["status"] == "warning" else 0)
        if args.command == "init":
            target = create_project(args.directory, args.template)
            print(f"Created {args.template} project: {target}\nOpen its README.md for commands and exercises.")
            return 0
        if args.command == "abduce":
            if args.file and args.assume:
                parser.error("abduce --file cannot be combined with --assume")
            if args.program:
                project = load_project(args.program)
                protect_sources(args, project)
                program = project.program
                knowledge = Knowledge(program.beliefs)
            else:
                agent = load_session(args.resume) if args.resume else load_demo(args.demo)
                program, knowledge = agent.program, agent.knowledge
            if args.file:
                goal, candidates = parse_abduction(Path(args.file).read_text(encoding="utf-8-sig"))
            else:
                goal, candidates = parse_query(args.query), tuple(parse_query(item) for item in args.assume)
            report = find_explanations(program, knowledge, goal, candidates,
                                       max_assumptions=args.max_assumptions, max_contexts=args.max_contexts,
                                       max_solutions=args.max_solutions, max_facts=args.max_facts, max_work=args.max_work)
            print(format_abduction(report, explain=args.explain))
            if args.result_json:
                save(args.result_json, json.dumps(report, indent=2))
            if report["status"] in {"error", "inconsistent"}:
                return 2
            return 0 if report["status"] == "complete" and report["solutions"] else 1
        if args.command == "compare":
            report = compare_agents(load_session(args.before), load_session(args.after), queries=args.query,
                                    max_facts=args.max_facts, max_work=args.max_work)
            print(format_comparison(report, explain=args.explain))
            if args.result_json:
                save(args.result_json, json.dumps(report, indent=2))
            return 0 if report["status"] == "ok" else 1
        if args.command == "demo":
            if args.list:
                if args.name or args.trace_json or args.trace_text or args.checkpoint:
                    parser.error("demo --list cannot be combined with a demo name or output files")
                for name, (_, description) in DEMOS.items():
                    print(f"{name}: {description}")
                return 0
            return execute_agent(load_demo(args.name or DEFAULT_DEMO), args)
        if args.command == "resume":
            return execute_agent(load_session(args.session), args)
        if args.command == "shell" and (args.demo or args.resume):
            if args.world:
                parser.error("--world can only be used with a program file")
            agent = load_session(args.resume) if args.resume else load_demo(args.demo)
            return run_shell(agent, max_hypotheses=args.max_hypotheses)
        program_path = Path(args.program)
        project = load_project(program_path)
        protect_sources(args, project)
        program = project.program
        if args.command == "imports":
            print(format_imports(project))
            if args.result_json:
                save(args.result_json, json.dumps(project.as_dict(), indent=2))
            return 0
        if args.command == "objects":
            print(format_objects(ObjectSpace(program).describe()))
            return 0
        if args.command in ("run", "shell"):
            world_path = Path(args.world) if args.world else program_path.with_suffix(".world.json")
            world = RouteWorld.from_json(world_path.read_text(encoding="utf-8-sig"))
            agent = Agent(program, world)
            if args.command == "shell":
                return run_shell(agent, max_hypotheses=args.max_hypotheses)
            return execute_agent(agent, args)

        if args.command == "deliberate":
            report = deliberate(program, Knowledge(program.beliefs),
                                max_hypotheses=args.max_hypotheses).report
            print(format_decision(report))
            if args.result_json:
                save(args.result_json, json.dumps(report, indent=2))
            return {"selected": 0, "achieved": 0, "stuck": 1, "reasoning_error": 2}[report["status"]]

        if args.command == "check":
            Inference(Knowledge(program.beliefs), program.effective_rules)
            print(f"Valid: agent {program.name}; {len(program.beliefs)} beliefs, "
                  f"{len(program.rules)} rules, {len(program.goals)} goals, {len(program.plans)} plans; "
                  f"{len(program.classes)} classes, {len(program.objects)} objects.")
            return 0
        source = Path(args.file).read_text(encoding="utf-8-sig") if args.file else args.query
        queries = parse_queries(source)
        ObjectSpace(program).validate_queries(queries)
        report = evaluate_queries(Knowledge(program.beliefs), program.effective_rules, queries)
        print(format_query_results(report, explain=args.command == "explain"))
        if args.result_json:
            save(args.result_json, json.dumps(report, indent=2))
        return {"ok": 0, "inconsistent": 1, "error": 2}[report["status"]]
    except (KGodelError, OSError, UnicodeError) as error:
        print(f"KGodel error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

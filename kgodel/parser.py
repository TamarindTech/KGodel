"""Parser for KGodel's deliberately small, function-free first version."""

from __future__ import annotations

import json
import re

from .model import (Atom, KGodelError, Literal, Plan, Program, ProveQuery, Query, Rule,
                    SupposeQuery, Unknown, Var, query_variables)


TOKEN = re.compile(r'\s+|%[^\n]*|//[^\n]*|:-|[A-Za-z_][A-Za-z0-9_]*|[0-9]+|"(?:\\.|[^"\\])*"|[{}(),.]')


class Parser:
    def __init__(self, source: str):
        self.source = source
        self.tokens: list[tuple[str, int]] = []
        position = 0
        while position < len(source):
            token = TOKEN.match(source, position)
            if not token:
                self.fail(f"Unexpected character {source[position]!r}", position)
            value = token.group()
            if not value.isspace() and not value.startswith(("%", "//")):
                self.tokens.append((value, position))
            position = token.end()
        self.index = 0

    def fail(self, message: str, position: int | None = None):
        if position is None:
            position = self.tokens[self.index][1] if self.index < len(self.tokens) else len(self.source)
        line = self.source.count("\n", 0, position) + 1
        column = position - self.source.rfind("\n", 0, position)
        raise KGodelError(f"Line {line}, column {column}: {message}.")

    def peek(self) -> str:
        return self.tokens[self.index][0] if self.index < len(self.tokens) else "<end>"

    def take(self, expected: str | None = None) -> str:
        value = self.peek()
        if expected is not None and value != expected:
            self.fail(f"Expected {expected!r}, found {value!r}")
        if value == "<end>":
            self.fail("Unexpected end of input")
        self.index += 1
        return value

    def accept(self, value: str) -> bool:
        if self.peek() == value:
            self.take()
            return True
        return False

    def identifier(self) -> str:
        if not re.fullmatch(r"[a-z][A-Za-z0-9_]*", self.peek()):
            self.fail("Expected a lowercase name")
        return self.take()

    def term(self) -> str | Var:
        value = self.peek()
        if value.startswith('"'):
            self.take()
            try:
                return json.loads(value)
            except json.JSONDecodeError as error:
                self.fail(f"Invalid quoted constant: {error.msg}")
        if re.fullmatch(r"[A-Z][A-Za-z0-9_]*", value):
            return Var(self.take())
        return self.identifier()

    def atom(self) -> Atom:
        name = self.identifier()
        arguments = []
        if self.accept("("):
            if self.peek() != ")":
                arguments.append(self.term())
                while self.accept(","):
                    arguments.append(self.term())
            self.take(")")
        return Atom(name, tuple(arguments))

    def literal(self) -> Literal:
        negative = self.accept("not")
        return Literal(self.atom(), negative)

    def guard(self) -> Literal | Unknown:
        if self.accept("unknown"):
            self.take("(")
            atom = self.atom()
            self.take(")")
            return Unknown(atom)
        return self.literal()

    def plan(self) -> Plan:
        name = self.identifier()
        parameters = []
        if self.accept("("):
            if self.peek() != ")":
                while True:
                    parameter = self.term()
                    if not isinstance(parameter, Var):
                        self.fail("Plan parameters must be variables")
                    parameters.append(parameter.name)
                    if not self.accept(","):
                        break
            self.take(")")
        self.take("for")
        target = self.atom()
        priority = 0
        if self.accept("priority"):
            value = self.peek()
            if not value.isascii() or not value.isdigit() or len(value) > 7 or int(value) > 1000000:
                self.fail("Plan priority must be an integer from 0 to 1000000")
            priority = int(self.take())
        self.take("{")
        self.take("when")
        guards = [self.guard()]
        while self.accept(","):
            guards.append(self.guard())
        self.take(".")
        hypotheses = []
        while self.peek() == "suppose":
            hypotheses.append(self.hypothesis(allow_variables=True))
        operation = self.take()
        if operation not in ("act", "observe"):
            self.fail("A plan must contain one 'act' or 'observe' operation")
        argument = self.atom()
        self.take(".")
        self.take("}")

        if len(parameters) != len(set(parameters)):
            self.fail(f"Duplicate parameters in plan {name}")
        used = target.variables | argument.variables
        for guard in guards:
            used |= guard.atom.variables
        hypothetical_variables = set().union(*(query_variables(query) for query in hypotheses))
        used |= hypothetical_variables
        if used != set(parameters):
            self.fail(f"Plan {name} must declare exactly its variables: {', '.join(sorted(used)) or '(none)'}")
        bound = set(target.variables)
        for guard in guards:
            if isinstance(guard, Literal):
                bound |= guard.atom.variables
        needed = set(argument.variables) | hypothetical_variables
        for guard in guards:
            if isinstance(guard, Unknown):
                needed |= guard.atom.variables
        if not needed <= bound:
            self.fail(f"Plan {name} has unbound variables: {', '.join(sorted(needed - bound))}")
        return Plan(name, tuple(parameters), target, tuple(guards), operation, argument,
                    priority, tuple(hypotheses))

    def program(self) -> Program:
        self.take("agent")
        name = self.identifier()
        self.take("{")
        beliefs, rules, goals, plans = [], [], [], []
        while self.peek() != "}":
            kind = self.take()
            if kind == "belief":
                belief = self.literal()
                if belief.atom.variables:
                    self.fail("Beliefs must be ground: variables are not allowed")
                beliefs.append(belief)
                self.take(".")
            elif kind == "goal":
                goal = self.atom()
                if goal.variables:
                    self.fail("Goals must be ground in this version")
                goals.append(goal)
                self.take(".")
            elif kind == "rule":
                head = self.literal()
                self.take(":-")
                body = [self.literal()]
                while self.accept(","):
                    body.append(self.literal())
                self.take(".")
                body_variables = set().union(*(literal.atom.variables for literal in body))
                if not head.atom.variables <= body_variables:
                    self.fail("Every rule-head variable must occur in the rule body")
                rules.append(Rule(f"rule_{len(rules) + 1}", head, tuple(body)))
            elif kind == "plan":
                plan = self.plan()
                if any(existing.name == plan.name for existing in plans):
                    self.fail(f"Duplicate plan name {plan.name}")
                plans.append(plan)
            else:
                self.fail(f"Expected belief, rule, goal, or plan; found {kind!r}")
        self.take("}")
        if self.peek() != "<end>":
            self.fail("Only one agent is supported in this version")
        return Program(name, tuple(beliefs), tuple(rules), tuple(goals), tuple(plans))

    def hypothesis(self, *, depth: int = 0, allow_variables: bool = False) -> SupposeQuery:
        if depth >= 16:
            self.fail("Hypothesis nesting limit exceeded (16)")
        self.take("suppose")
        self.take("(")
        assumptions = [self.literal()]
        while self.accept(","):
            assumptions.append(self.literal())
        self.take(")")
        if not allow_variables and any(literal.atom.variables for literal in assumptions):
            self.fail("Assumptions must be ground")
        self.take("{")
        body = self.queries(nested=True, depth=depth + 1, allow_variables=allow_variables)
        self.take("}")
        self.accept(".")
        return SupposeQuery(tuple(assumptions), body)

    def queries(self, *, nested: bool = False, depth: int = 0,
                allow_variables: bool = False) -> tuple[Query, ...]:
        statements = []
        end = "}" if nested else "<end>"
        while self.peek() != end:
            if self.peek() == "suppose":
                statements.append(self.hypothesis(depth=depth, allow_variables=allow_variables))
            else:
                if self.accept("prove"):
                    self.take("(")
                    literal = self.literal()
                    self.take(")")
                else:
                    literal = self.literal()
                statements.append(ProveQuery(literal))
                if not self.accept(".") and (nested or self.peek() != "<end>"):
                    self.fail("Expected '.' after a query")
        if not statements:
            self.fail("Expected at least one query")
        return tuple(statements)


def parse(source: str) -> Program:
    return Parser(source).program()


def parse_query(source: str) -> Literal:
    parser = Parser(source)
    query = parser.literal()
    parser.accept(".")
    if parser.peek() != "<end>":
        parser.fail("Expected the end of the query")
    return query


def parse_queries(source: str) -> tuple[Query, ...]:
    """Parse a bare query, a prove expression, or a sequence of scoped queries."""
    return Parser(source).queries()

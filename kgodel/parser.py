"""Parser for KGodel's deliberately small, function-free first version."""

from __future__ import annotations

import json
import re

from .model import (Atom, ClassDefinition, ExpressionQuery, GoalExpression, KGodelError, Literal, Method, ObjectDefinition, Plan,
                    PlanStep, Program, ProveQuery, Query, Rule, SelfRef, SlotRef, SuperRef,
                    SupposeQuery, Term, Unknown, Var, query_variables)


TOKEN = re.compile(r"\s+|%[^\n]*|//[^\n]*|:-|\?-|[A-Za-z_][A-Za-z0-9_]*|[0-9]+"
                   r'''|"(?:\\.|[^"\\])*"|'(?:\\.|''|[^'\\])*'|[{}(),;.\[\]:=@^]''')


class Parser:
    def __init__(self, source: str, *, allow_internal: bool = False, legacy_super: bool = False):
        self.source = source
        self.allow_internal = allow_internal
        self.legacy_super = legacy_super
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
        self.in_method = False
        self.expression_nodes = 0

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

    def quoted_atom(self) -> str:
        value = self.take()
        if value.startswith("'"):
            result, index = [], 1
            escapes = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
                       "\\": "\\", "'": "'", '"': '"'}
            while index < len(value) - 1:
                char = value[index]
                if char == "\\":
                    index += 1
                    if value[index] not in escapes:
                        self.fail(f"Unsupported quoted-atom escape \\{value[index]}")
                    result.append(escapes[value[index]])
                elif char == "'":
                    result.append("'")
                    index += 1  # The tokenizer guarantees a doubled apostrophe.
                else:
                    result.append(char)
                index += 1
            return "".join(result)
        self.fail("Expected a single-quoted constant")

    def accept(self, value: str) -> bool:
        if self.peek() == value:
            self.take()
            return True
        return False

    def identifier(self) -> str:
        if not re.fullmatch(r"[a-z][A-Za-z0-9_]*", self.peek()):
            self.fail("Expected a lowercase name")
        return self.take()

    def term(self) -> Term:
        if self.accept("@"):
            if not self.in_method:
                self.fail("Instance variable access is only allowed inside methods")
            return SlotRef(self.identifier())
        if self.in_method and self.accept("self"):
            return SelfRef()
        value = self.peek()
        if value.startswith("'"):
            return self.quoted_atom()
        if value.startswith('"'):
            self.take()
            try:
                return json.loads(value)
            except json.JSONDecodeError as error:
                self.fail(f"Invalid quoted constant: {error.msg}")
        if re.fullmatch(r"[A-Z_][A-Za-z0-9_]*", value):
            return Var(self.take())
        return self.identifier()

    def atom(self) -> Atom:
        if self.accept("["):
            receiver = (SuperRef() if self.in_method and not self.legacy_super and self.accept("super")
                        else self.term())
            lookup_class = None
            if self.accept("^"):
                if not self.allow_internal:
                    self.fail("Superclass lookup annotations are reserved for stored proofs")
                lookup_class = self.class_name()
            first = self.identifier()
            selector, arguments = first, []
            if self.accept(":"):
                selector += ":"
                arguments.append(self.term())
                while self.peek() != "]":
                    selector += self.identifier() + ":"
                    self.take(":")
                    arguments.append(self.term())
            self.take("]")
            return Atom(selector, tuple(arguments), receiver, lookup_class)
        name = self.identifier()
        arguments = []
        if self.accept("("):
            if self.peek() != ")":
                arguments.append(self.term())
                while self.accept(","):
                    arguments.append(self.term())
            self.take(")")
        return Atom(name, tuple(arguments))

    def class_name(self) -> str:
        if not re.fullmatch(r"[A-Z][A-Za-z0-9_]*", self.peek()):
            self.fail("Class names must start with an uppercase letter")
        return self.take()

    def class_definition(self) -> ClassDefinition:
        name = self.class_name()
        parent = self.class_name() if self.accept("extends") else None
        self.take("{")
        slots, methods = [], []
        while self.peek() != "}":
            kind = self.take()
            if kind == "slot":
                slots.append(self.identifier())
                self.take(".")
                continue
            if kind != "method":
                self.fail("Expected slot or method in a class")
            negative = self.accept("not")
            selector = self.identifier()
            parameters = []
            if self.accept(":"):
                selector += ":"
                while True:
                    parameter = self.term()
                    if not isinstance(parameter, Var) or parameter.name == "_":
                        self.fail("Method parameters must be variables")
                    parameters.append(parameter.name)
                    if self.peek() == "{":
                        break
                    selector += self.identifier() + ":"
                    self.take(":")
            self.take("{")
            self.in_method = True
            body = []
            while self.peek() != "}":
                body.append(self.literal())
                self.take(".")
            self.in_method = False
            self.take("}")
            if not body:
                self.fail("A method requires at least one logical condition")
            if len(parameters) != len(set(parameters)):
                self.fail("Method parameter names must be unique")
            bound = set().union(*(literal.atom.variables for literal in body))
            if not set(parameters) <= bound:
                self.fail("Every method parameter must occur in its body")
            methods.append(Method(selector, tuple(parameters), tuple(body), negative))
        self.take("}")
        return ClassDefinition(name, parent, tuple(slots), tuple(methods))

    def object_definition(self) -> ObjectDefinition:
        name = self.identifier()
        self.take(":")
        class_name = self.class_name()
        self.take("{")
        slots = []
        while self.peek() != "}":
            slot = self.identifier()
            self.take("=")
            value = self.term()
            if not isinstance(value, str):
                self.fail("Instance variables must be initialized with constants")
            slots.append((slot, value))
            self.take(".")
        self.take("}")
        return ObjectDefinition(name, class_name, tuple(slots))

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
                    if not isinstance(parameter, Var) or parameter.name == "_":
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
        steps = []
        while self.peek() != "}":
            requirements = []
            if self.accept("require"):
                requirements.append(self.guard())
                while self.accept(","):
                    requirements.append(self.guard())
                self.take(".")
            operation = self.take()
            if operation not in ("act", "observe"):
                self.fail("Expected an 'act' or 'observe' operation after optional 'require' guards")
            argument = self.atom()
            self.take(".")
            steps.append(PlanStep(operation, argument, tuple(requirements)))
        if not steps:
            self.fail("A plan must contain at least one 'act' or 'observe' operation")
        self.take("}")

        if len(parameters) != len(set(parameters)):
            self.fail(f"Duplicate parameters in plan {name}")
        step_variables = set()
        for step in steps:
            step_variables |= step.argument.variables
            for requirement in step.requirements:
                step_variables |= requirement.atom.variables
        used = target.variables | step_variables
        for guard in guards:
            used |= guard.atom.variables
        hypothetical_variables = set().union(*(query_variables(query) for query in hypotheses))
        used |= hypothetical_variables
        if ("_" in target.variables | step_variables | hypothetical_variables
                or any(isinstance(guard, Unknown) and "_" in guard.atom.variables for guard in guards)):
            self.fail("Anonymous variables are only allowed in signed plan entry guards")
        used.discard("_")
        if used != set(parameters):
            self.fail(f"Plan {name} must declare exactly its variables: {', '.join(sorted(used)) or '(none)'}")
        bound = set(target.variables)
        for guard in guards:
            if isinstance(guard, Literal):
                bound |= guard.atom.variables
        needed = step_variables | hypothetical_variables
        for guard in guards:
            if isinstance(guard, Unknown):
                needed |= guard.atom.variables
        if not needed <= bound:
            self.fail(f"Plan {name} has unbound variables: {', '.join(sorted(needed - bound))}")
        return Plan(name, tuple(parameters), target, tuple(guards), tuple(steps),
                    priority, tuple(hypotheses))

    def rule_definition(self, head: Literal, number: int) -> Rule:
        self.take(":-")
        body = [self.literal()]
        while self.accept(","):
            body.append(self.literal())
        self.take(".")
        body_variables = set().union(*(literal.atom.variables for literal in body))
        if "_" in head.atom.variables:
            self.fail("Anonymous variables are not allowed in rule heads")
        if not head.atom.variables <= body_variables:
            self.fail("Every rule-head variable must occur in the rule body")
        return Rule(f"rule_{number}", head, tuple(body))

    def program(self) -> Program:
        self.take("agent")
        name = self.identifier()
        self.take("{")
        beliefs, rules, goals, plans, classes, objects = [], [], [], [], [], []
        while self.peek() != "}":
            kind = self.take()
            if kind == "class":
                classes.append(self.class_definition())
            elif kind == "object":
                objects.append(self.object_definition())
            elif kind == "belief":
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
                rules.append(self.rule_definition(head, len(rules) + 1))
            elif kind == "plan":
                plan = self.plan()
                if any(existing.name == plan.name for existing in plans):
                    self.fail(f"Duplicate plan name {plan.name}")
                plans.append(plan)
            else:
                self.index -= 1
                head = self.literal()
                if self.peek() == ":-":
                    rules.append(self.rule_definition(head, len(rules) + 1))
                else:
                    if head.atom.variables:
                        self.fail("Facts must be ground: variables are not allowed")
                    self.take(".")
                    beliefs.append(head)
        self.take("}")
        if self.peek() != "<end>":
            self.fail("Only one agent is supported in this version")
        program = Program(name, tuple(beliefs), tuple(rules), tuple(goals), tuple(plans), tuple(classes), tuple(objects))
        from .objects import ObjectSpace
        ObjectSpace(program).validate_program()
        return program

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
            self.accept("?-")
            if self.peek() == "suppose":
                statements.append(self.hypothesis(depth=depth, allow_variables=allow_variables))
            else:
                self.expression_nodes = 0
                if self.accept("prove"):
                    self.take("(")
                    expression = self.goal_expression()
                    self.take(")")
                else:
                    expression = self.goal_expression()
                statements.append(ProveQuery(expression) if isinstance(expression, Literal) else ExpressionQuery(expression))
                if not self.accept(".") and (nested or self.peek() != "<end>"):
                    self.fail("Expected '.' after a query")
        if not statements:
            self.fail("Expected at least one query")
        return tuple(statements)

    def goal_expression(self, depth: int = 0) -> Literal | GoalExpression:
        if depth >= 64:
            self.fail("Query grouping depth exceeds 64")
        alternatives = []
        while True:
            conjunction = []
            while True:
                if self.accept("("):
                    item = self.goal_expression(depth + 1)
                    self.take(")")
                else:
                    self.expression_nodes += 1
                    if self.expression_nodes > 256:
                        self.fail("Query expression size exceeds 256 literals")
                    item = self.literal()
                conjunction.append(item)
                if not self.accept(","):
                    break
            alternatives.append(conjunction[0] if len(conjunction) == 1 else GoalExpression("and", tuple(conjunction)))
            if not self.accept(";"):
                break
        expression = alternatives[0] if len(alternatives) == 1 else GoalExpression("or", tuple(alternatives))
        if depth == 0:
            pending = [(expression, 0)]
            while pending:
                item, level = pending.pop()
                if isinstance(item, GoalExpression):
                    if level >= 32:
                        self.fail("Query expression depth exceeds 32")
                    pending.extend((child, level + 1) for child in item.operands)
        return expression


def parse(source: str, *, legacy_super: bool = False) -> Program:
    return Parser(source, legacy_super=legacy_super).program()


def parse_query(source: str, *, allow_internal: bool = False) -> Literal:
    parser = Parser(source, allow_internal=allow_internal)
    query = parser.literal()
    parser.accept(".")
    if parser.peek() != "<end>":
        parser.fail("Expected the end of the query")
    return query


def parse_queries(source: str) -> tuple[Query, ...]:
    """Parse a bare query, a prove expression, or a sequence of scoped queries."""
    return Parser(source).queries()


def parse_abduction(source: str) -> tuple[Literal, tuple[Literal, ...]]:
    """Parse GOAL from (CANDIDATE, ...), for the shell and .kga files."""
    parser = Parser(source)
    goal = parser.literal()
    parser.take("from")
    parser.take("(")
    candidates = []
    if parser.peek() != ")":
        candidates.append(parser.literal())
        while parser.accept(","):
            candidates.append(parser.literal())
    parser.take(")")
    parser.accept(".")
    if parser.peek() != "<end>":
        parser.fail("Expected the end of the abduction request")
    return goal, tuple(candidates)

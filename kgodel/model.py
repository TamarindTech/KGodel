from __future__ import annotations

from dataclasses import dataclass
import json
import re


class KGodelError(Exception):
    """A source, knowledge, or execution error that can be shown to the user."""


class KnowledgeConflict(KGodelError):
    """Both polarities of a statement are supported in the same context."""


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class SlotRef:
    name: str


@dataclass(frozen=True)
class SelfRef:
    pass


@dataclass(frozen=True)
class SuperRef:
    """A method receiver whose lookup starts above the defining class."""


Term = str | Var | SlotRef | SelfRef | SuperRef
Bindings = dict[str, str]


def render_term(term: Term) -> str:
    if isinstance(term, Var):
        return term.name
    if isinstance(term, SlotRef):
        return "@" + term.name
    if isinstance(term, SelfRef):
        return "self"
    if isinstance(term, SuperRef):
        return "super"
    return term if re.fullmatch(r"[a-z][A-Za-z0-9_]*", term) else json.dumps(term)


@dataclass(frozen=True)
class Atom:
    name: str
    args: tuple[Term, ...] = ()
    receiver: Term | None = None
    # Compiler-only namespace: parent support must not satisfy a normal send.
    lookup_class: str | None = None

    def __str__(self) -> str:
        return self.render()

    def render(self, *, in_method: bool = False) -> str:
        def term_text(term):
            # Quote literal receiver names that have special method meanings.
            # Ordinary literals retain their old checkpoint fingerprint spelling.
            if in_method and isinstance(term, str) and term in {"self", "super"}:
                return json.dumps(term)
            return render_term(term)

        if self.receiver is not None:
            message = self.name if not self.args else " ".join(
                f"{part}: {term_text(value)}" for part, value in zip(self.name.split(":"), self.args))
            lookup = f" ^{self.lookup_class}" if self.lookup_class else ""
            return f"[{term_text(self.receiver)}{lookup} {message}]"
        return self.name + ("(" + ", ".join(map(term_text, self.args)) + ")" if self.args else "")

    @property
    def variables(self) -> set[str]:
        return {term.name for term in (*self.args, self.receiver) if isinstance(term, Var)}

    def ground(self, bindings: Bindings) -> Atom:
        try:
            terms = (*self.args, self.receiver)
            if any(isinstance(term, (SlotRef, SelfRef, SuperRef)) for term in terms):
                raise KGodelError("Method references must be resolved before inference.")
            if "_" in self.variables:
                raise KGodelError("Anonymous variables cannot be grounded into facts or operations.")
            return Atom(self.name, tuple(bindings[t.name] if isinstance(t, Var) else t for t in self.args),
                        bindings[self.receiver.name] if isinstance(self.receiver, Var) else self.receiver,
                        self.lookup_class)
        except KeyError as error:
            raise KGodelError(f"Unbound variable {error.args[0]} in {self}.") from error


@dataclass(frozen=True)
class Literal:
    atom: Atom
    negative: bool = False

    def __str__(self) -> str:
        return ("not " if self.negative else "") + str(self.atom)

    def opposite(self) -> Literal:
        return Literal(self.atom, not self.negative)

    def ground(self, bindings: Bindings) -> Literal:
        return Literal(self.atom.ground(bindings), self.negative)


@dataclass(frozen=True)
class Unknown:
    atom: Atom

    def __str__(self) -> str:
        return f"unknown({self.atom})"


@dataclass(frozen=True)
class Rule:
    name: str
    head: Literal
    body: tuple[Literal, ...]


@dataclass(frozen=True)
class PlanStep:
    operation: str
    argument: Atom
    requirements: tuple[Literal | Unknown, ...] = ()


@dataclass(frozen=True)
class Plan:
    name: str
    parameters: tuple[str, ...]
    target: Atom
    guards: tuple[Literal | Unknown, ...]
    steps: tuple[PlanStep, ...]
    priority: int = 0
    hypotheses: tuple[SupposeQuery, ...] = ()

    @property
    def operation(self) -> str:
        return self.steps[0].operation

    @property
    def argument(self) -> Atom:
        return self.steps[0].argument


@dataclass(frozen=True)
class Method:
    selector: str
    parameters: tuple[str, ...]
    body: tuple[Literal, ...]
    negative: bool = False


@dataclass(frozen=True)
class ClassDefinition:
    name: str
    parent: str | None
    slots: tuple[str, ...]
    methods: tuple[Method, ...]


@dataclass(frozen=True)
class ObjectDefinition:
    name: str
    class_name: str
    slots: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Program:
    name: str
    beliefs: tuple[Literal, ...]
    rules: tuple[Rule, ...]
    goals: tuple[Atom, ...]
    plans: tuple[Plan, ...]
    classes: tuple[ClassDefinition, ...] = ()
    objects: tuple[ObjectDefinition, ...] = ()

    @property
    def effective_rules(self) -> tuple[Rule, ...]:
        from .objects import ObjectSpace
        return self.rules + ObjectSpace(self).compile_rules() if self.classes or self.objects else self.rules


@dataclass(frozen=True)
class ProveQuery:
    literal: Literal


@dataclass(frozen=True)
class GoalExpression:
    operator: str
    operands: tuple[Literal | GoalExpression, ...]

    def __post_init__(self):
        if self.operator not in {"and", "or"} or len(self.operands) < 2:
            raise KGodelError("A goal expression needs an and/or operator and at least two operands.")

    def __str__(self) -> str:
        separator = ", " if self.operator == "and" else "; "
        return "(" + separator.join(map(str, self.operands)) + ")"

    @property
    def variables(self) -> set[str]:
        return set().union(*(item.atom.variables if isinstance(item, Literal) else item.variables
                             for item in self.operands))

    def ground(self, bindings: Bindings) -> GoalExpression:
        return GoalExpression(self.operator, tuple(item.ground(bindings) for item in self.operands))


@dataclass(frozen=True)
class ExpressionQuery:
    expression: GoalExpression


@dataclass(frozen=True)
class SupposeQuery:
    assumptions: tuple[Literal, ...]
    body: tuple[ProveQuery | ExpressionQuery | SupposeQuery, ...]


Query = ProveQuery | ExpressionQuery | SupposeQuery


def expression_literals(expression: Literal | GoalExpression):
    if isinstance(expression, Literal):
        yield expression
    else:
        for operand in expression.operands:
            yield from expression_literals(operand)


def query_variables(query: Query) -> set[str]:
    if isinstance(query, ProveQuery):
        return query.literal.atom.variables
    if isinstance(query, ExpressionQuery):
        return query.expression.variables
    variables = set().union(*(literal.atom.variables for literal in query.assumptions))
    for child in query.body:
        variables |= query_variables(child)
    return variables


def ground_query(query: Query, bindings: Bindings) -> Query:
    if isinstance(query, ProveQuery):
        return ProveQuery(query.literal.ground(bindings))
    if isinstance(query, ExpressionQuery):
        return ExpressionQuery(query.expression.ground(bindings))
    return SupposeQuery(tuple(literal.ground(bindings) for literal in query.assumptions),
                        tuple(ground_query(child, bindings) for child in query.body))


def match(pattern: Atom, value: Atom, bindings: Bindings | None = None) -> Bindings | None:
    """Match a possibly variable pattern against a ground atom."""
    if (pattern.name != value.name or len(pattern.args) != len(value.args)
            or pattern.lookup_class != value.lookup_class
            or (pattern.receiver is None) != (value.receiver is None)):
        return None
    result = dict(bindings or {})
    expected_terms = pattern.args + ((pattern.receiver,) if pattern.receiver is not None else ())
    actual_terms = value.args + ((value.receiver,) if value.receiver is not None else ())
    for expected, actual in zip(expected_terms, actual_terms):
        if isinstance(actual, Var):
            raise KGodelError("Matching requires a ground value.")
        if isinstance(expected, Var):
            if expected.name == "_":
                continue  # Every anonymous occurrence matches independently.
            if expected.name in result and result[expected.name] != actual:
                return None
            result[expected.name] = actual
        elif expected != actual:
            return None
    return result


@dataclass(frozen=True)
class Proof:
    conclusion: Literal
    source: str
    premises: tuple[Proof, ...] = ()

    def as_dict(self) -> dict:
        return {
            "conclusion": str(self.conclusion),
            "source": self.source,
            "premises": [p.as_dict() for p in self.premises],
        }

    def lines(self, depth: int = 0) -> list[str]:
        lines = ["  " * depth + f"{self.conclusion} [{self.source}]"]
        for premise in self.premises:
            lines.extend(premise.lines(depth + 1))
        return lines

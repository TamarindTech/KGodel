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


Term = str | Var
Bindings = dict[str, str]


def render_term(term: Term) -> str:
    if isinstance(term, Var):
        return term.name
    return term if re.fullmatch(r"[a-z][A-Za-z0-9_]*", term) else json.dumps(term)


@dataclass(frozen=True)
class Atom:
    name: str
    args: tuple[Term, ...] = ()

    def __str__(self) -> str:
        return self.name + ("(" + ", ".join(map(render_term, self.args)) + ")" if self.args else "")

    @property
    def variables(self) -> set[str]:
        return {term.name for term in self.args if isinstance(term, Var)}

    def ground(self, bindings: Bindings) -> Atom:
        try:
            return Atom(self.name, tuple(bindings[t.name] if isinstance(t, Var) else t for t in self.args))
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
class Plan:
    name: str
    parameters: tuple[str, ...]
    target: Atom
    guards: tuple[Literal | Unknown, ...]
    operation: str
    argument: Atom
    priority: int = 0
    hypotheses: tuple[SupposeQuery, ...] = ()


@dataclass(frozen=True)
class Program:
    name: str
    beliefs: tuple[Literal, ...]
    rules: tuple[Rule, ...]
    goals: tuple[Atom, ...]
    plans: tuple[Plan, ...]


@dataclass(frozen=True)
class ProveQuery:
    literal: Literal


@dataclass(frozen=True)
class SupposeQuery:
    assumptions: tuple[Literal, ...]
    body: tuple[ProveQuery | SupposeQuery, ...]


Query = ProveQuery | SupposeQuery


def query_variables(query: Query) -> set[str]:
    if isinstance(query, ProveQuery):
        return query.literal.atom.variables
    variables = set().union(*(literal.atom.variables for literal in query.assumptions))
    for child in query.body:
        variables |= query_variables(child)
    return variables


def ground_query(query: Query, bindings: Bindings) -> Query:
    if isinstance(query, ProveQuery):
        return ProveQuery(query.literal.ground(bindings))
    return SupposeQuery(tuple(literal.ground(bindings) for literal in query.assumptions),
                        tuple(ground_query(child, bindings) for child in query.body))


def match(pattern: Atom, value: Atom, bindings: Bindings | None = None) -> Bindings | None:
    """Match a possibly variable pattern against a ground atom."""
    if pattern.name != value.name or len(pattern.args) != len(value.args):
        return None
    result = dict(bindings or {})
    for expected, actual in zip(pattern.args, value.args):
        if isinstance(actual, Var):
            raise KGodelError("Matching requires a ground value.")
        if isinstance(expected, Var):
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

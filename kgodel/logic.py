"""Pure inference and explicit belief revision; no environment calls live here."""

from __future__ import annotations

from .model import Bindings, KGodelError, KnowledgeConflict, Literal, Proof, Rule, Unknown, match


class Knowledge:
    def __init__(self, beliefs: tuple[Literal, ...] = ()):
        self.facts: dict[Literal, Proof] = {}
        for belief in beliefs:
            if belief.atom.variables:
                raise KGodelError("Beliefs must be ground.")
            if belief.opposite() in self.facts:
                raise KnowledgeConflict(f"Conflicting initial beliefs: {belief} and {belief.opposite()}.")
            self.facts[belief] = Proof(belief, "program")

    def copy(self) -> Knowledge:
        child = Knowledge()
        # Proofs and their premises are immutable; only the fact dictionary is copied.
        child.facts = dict(self.facts)
        return child

    def assuming(self, assumptions: tuple[Literal, ...], scope: str) -> Knowledge:
        """Build an additive hypothesis without modifying the parent context."""
        if not assumptions:
            raise KGodelError("A hypothesis requires at least one assumption.")
        child = self.copy()
        for literal in assumptions:
            if literal.atom.variables:
                raise KGodelError("Assumptions must be ground.")
            if literal.opposite() in child.facts:
                raise KnowledgeConflict(f"Assumption {literal} contradicts {literal.opposite()}.")
            # Existing support remains authoritative when an assumption is redundant.
            child.facts.setdefault(literal, Proof(literal, f"assumption:{scope}"))
        return child

    def observe(self, literal: Literal, source: str) -> dict:
        if literal.atom.variables:
            raise KGodelError("Observations must be ground.")
        previous = self.facts.pop(literal.opposite(), None)
        existed = literal in self.facts
        self.facts[literal] = Proof(literal, source)
        return {
            "accepted": str(literal),
            "source": source,
            "retracted": str(previous.conclusion) if previous else None,
            "changed": previous is not None or not existed,
        }

    def fingerprint(self) -> tuple[str, ...]:
        return tuple(sorted(map(str, self.facts)))


class Inference:
    def __init__(self, knowledge: Knowledge, rules: tuple[Rule, ...], *, max_facts: int = 10000,
                 max_work: int = 200000):
        self.proofs = dict(knowledge.facts)
        self.max_work = max_work
        self.work = 0
        if len(self.proofs) > max_facts:
            raise KGodelError("Inference fact limit exceeded.")
        changed = True
        while changed:
            changed = False
            for rule in rules:
                # Materialize against the current snapshot before extending it.
                for bindings, evidence in list(self.solve(rule.body)):
                    conclusion = rule.head.ground(bindings)
                    if conclusion.opposite() in self.proofs:
                        raise KnowledgeConflict(f"Knowledge conflict: {conclusion} contradicts {conclusion.opposite()}.")
                    if conclusion not in self.proofs:
                        if len(self.proofs) >= max_facts:
                            raise KGodelError("Inference fact limit exceeded.")
                        premises = tuple(item for item in evidence if isinstance(item, Proof))
                        self.proofs[conclusion] = Proof(conclusion, rule.name, premises)
                        changed = True

    def solve(self, guards: tuple[Literal | Unknown, ...], initial: Bindings | None = None):
        rows: list[tuple[Bindings, tuple[Proof | dict, ...]]] = [(dict(initial or {}), ())]
        # Explicit signed literals bind variables. Unknown only tests a ground atom.
        for guard in (item for item in guards if isinstance(item, Literal)):
            candidates = [(literal, proof) for literal, proof in self.proofs.items()
                          if literal.negative == guard.negative
                          and literal.atom.name == guard.atom.name
                          and (literal.atom.receiver is None) == (guard.atom.receiver is None)
                          and len(literal.atom.args) == len(guard.atom.args)]
            candidates.sort(key=lambda item: str(item[0]))
            next_rows = []
            for bindings, evidence in rows:
                for literal, proof in candidates:
                    self.work += 1
                    if self.work > self.max_work:
                        raise KGodelError("Inference work limit exceeded; this is not a logical false result.")
                    matched = match(guard.atom, literal.atom, bindings)
                    if matched is not None:
                        next_rows.append((matched, evidence + (proof,)))
            rows = next_rows
        for guard in (item for item in guards if isinstance(item, Unknown)):
            next_rows = []
            for bindings, evidence in rows:
                atom = guard.atom.ground(bindings)
                if Literal(atom) not in self.proofs and Literal(atom, True) not in self.proofs:
                    next_rows.append((bindings, evidence + ({"unknown": str(atom)},)))
            rows = next_rows
        yield from rows

    def status(self, literal: Literal) -> str:
        if literal.atom.variables:
            raise KGodelError("Truth status requires a ground query; use solve for variables.")
        if literal in self.proofs:
            return "true"
        if literal.opposite() in self.proofs:
            return "false"
        return "unknown"

    def explanation(self, literal: Literal) -> Proof | None:
        return self.proofs.get(literal)

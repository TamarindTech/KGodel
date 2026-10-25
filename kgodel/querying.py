"""Evaluate pure, scoped queries against snapshots of accepted knowledge."""

from __future__ import annotations

from .logic import Inference, Knowledge
from .model import (ExpressionQuery, GoalExpression, KGodelError, KnowledgeConflict, Literal,
                    Proof, ProveQuery, Query, Rule, render_term)


def assumptions_used(proof: Proof | dict | None) -> list[dict]:
    found = set()
    pending = [proof] if proof else []
    while pending:
        item = pending.pop()
        source = item.source if isinstance(item, Proof) else item["source"]
        conclusion = str(item.conclusion) if isinstance(item, Proof) else item["conclusion"]
        if source.startswith("assumption:"):
            found.add((source.removeprefix("assumption:"), conclusion))
        pending.extend(item.premises if isinstance(item, Proof) else item["premises"])
    return [{"scope": scope, "literal": literal} for scope, literal in sorted(found)]


class _Evaluator:
    def __init__(self, rules: tuple[Rule, ...], max_depth: int, max_contexts: int,
                 max_facts: int, max_work: int):
        self.rules = rules
        self.max_depth = max_depth
        self.max_contexts = max_contexts
        self.limits = {"max_facts": max_facts, "max_work": max_work}
        self.contexts = 0

    def evaluate(self, queries: tuple[Query, ...], knowledge: Knowledge, logic: Inference,
                 scope: str = "base", depth: int = 0) -> list[dict]:
        results = []
        for query in queries:
            if isinstance(query, (ProveQuery, ExpressionQuery)):
                expression = query.literal if isinstance(query, ProveQuery) else query.expression
                try:
                    results.append(self.prove(query, logic, scope))
                except KGodelError as error:
                    results.append({"kind": "query", "scope": scope, "query": str(expression),
                                    "status": "error", "error": str(error)})
                continue

            self.contexts += 1
            child_scope = f"hypothesis_{self.contexts}"
            result = {"kind": "suppose", "scope": child_scope, "parent_scope": scope,
                      "assumptions": list(map(str, query.assumptions)), "results": []}
            try:
                if depth >= self.max_depth:
                    raise KGodelError(f"Hypothesis nesting limit exceeded ({self.max_depth}).")
                if self.contexts > self.max_contexts:
                    raise KGodelError(f"Hypothesis context limit exceeded ({self.max_contexts}).")
                child = knowledge.assuming(query.assumptions, child_scope)
                child_logic = Inference(child, self.rules, **self.limits)
                result["results"] = self.evaluate(query.body, child, child_logic, child_scope, depth + 1)
                result["status"] = "evaluated"
            except KnowledgeConflict as error:
                result.update(status="inconsistent", error=str(error))
            except KGodelError as error:
                result.update(status="error", error=str(error))
            results.append(result)
        return results

    @staticmethod
    def prove(query: ProveQuery | ExpressionQuery, logic: Inference, scope: str) -> dict:
        expression = query.literal if isinstance(query, ProveQuery) else query.expression
        variables = expression.atom.variables if isinstance(expression, Literal) else expression.variables
        result = {"kind": "query", "scope": scope, "query": str(expression)}
        if variables:
            answers, seen = [], set()
            for bindings, proof in solve_expression(expression, logic):
                key = tuple(sorted(bindings.items()))
                if key in seen:
                    continue
                seen.add(key)
                answers.append({"bindings": bindings, "proof": proof,
                                "assumptions_used": assumptions_used(proof)})
            result.update(status="answers" if answers else "no_answers", answers=answers)
        else:
            status, proof = expression_status(expression, logic)
            result.update(status=status, proof=proof,
                          assumptions_used=assumptions_used(proof))
        return result


def expression_proof(expression: GoalExpression, premises: list[dict], *, opposing=False) -> dict:
    return {"conclusion": ("not " if opposing else "") + str(expression),
            "source": "query:" + expression.operator, "premises": premises}


def solve_expression(expression: Literal | GoalExpression, logic: Inference, initial=None):
    """Join conjunctions and enumerate independent alternatives without DNF expansion."""
    if isinstance(expression, Literal):
        for bindings, evidence in logic.solve((expression,), initial):
            yield bindings, evidence[0].as_dict()
    elif expression.operator == "or":
        for operand in expression.operands:
            for bindings, proof in solve_expression(operand, logic, initial):
                yield bindings, expression_proof(expression, [proof])
    else:
        rows = [(dict(initial or {}), [])]
        for operand in expression.operands:
            next_rows = []
            for bindings, premises in rows:
                for extended, proof in solve_expression(operand, logic, bindings):
                    next_rows.append((extended, premises + [proof]))
            rows = next_rows
            if not rows:
                break
        for bindings, premises in rows:
            yield bindings, expression_proof(expression, premises)


def expression_status(expression: Literal | GoalExpression, logic: Inference) -> tuple[str, dict | None]:
    """Three-valued truth for ground expressions, retaining explicit opposition."""
    if isinstance(expression, Literal):
        status = logic.status(expression)
        proof = logic.explanation(expression if status == "true" else expression.opposite())
        return status, proof.as_dict() if proof else None
    children = [expression_status(operand, logic) for operand in expression.operands]
    decisive = "false" if expression.operator == "and" else "true"
    for status, proof in children:
        if status == decisive:
            return status, expression_proof(expression, [proof], opposing=status == "false")
    if all(status != "unknown" for status, _ in children):
        status = "true" if expression.operator == "and" else "false"
        return status, expression_proof(expression, [proof for _, proof in children], opposing=status == "false")
    return "unknown", None


def evaluate_queries(knowledge: Knowledge, rules: tuple[Rule, ...], queries: tuple[Query, ...], *,
                     max_depth: int = 16, max_contexts: int = 64, max_facts: int = 10000,
                     max_work: int = 200000) -> dict:
    """Return conditional answers; neither accepted beliefs nor an environment is mutated."""
    if min(max_depth, max_contexts, max_facts, max_work) < 0:
        raise KGodelError("Query limits must be nonnegative.")
    snapshot = knowledge.copy()
    logic = Inference(snapshot, rules, max_facts=max_facts, max_work=max_work)
    evaluator = _Evaluator(rules, max_depth, max_contexts, max_facts, max_work)
    results = evaluator.evaluate(queries, snapshot, logic)
    statuses = set()
    pending = list(results)
    while pending:
        result = pending.pop()
        statuses.add(result["status"])
        pending.extend(result.get("results", ()))
    status = "error" if "error" in statuses else "inconsistent" if "inconsistent" in statuses else "ok"
    return {"status": status, "results": results}


def format_query_results(report: dict, *, explain: bool = False) -> str:
    lines = []

    def proof_lines(proof: dict, indent: str):
        lines.append(f"{indent}{proof['conclusion']} [{proof['source']}]")
        for premise in proof["premises"]:
            proof_lines(premise, indent + "  ")

    def dependencies(answer: dict, indent: str):
        if explain and answer.get("proof"):
            proof_lines(answer["proof"], indent)
        elif answer.get("assumptions_used"):
            for assumption in answer["assumptions_used"]:
                lines.append(f"{indent}Depends on {assumption['literal']} [{assumption['scope']}].")

    def render(result: dict, indent: str = ""):
        status = result["status"]
        if result["kind"] == "suppose":
            lines.append(f"{indent}Suppose {', '.join(result['assumptions'])} [{result['scope']}]:")
            if status in ("inconsistent", "error"):
                lines.append(f"{indent}  {status}: {result['error']}")
            for child in result["results"]:
                render(child, indent + "  ")
            lines.append(f"{indent}End {result['scope']}; temporary assumptions discarded.")
        elif status == "error":
            lines.append(f"{indent}error: {result['query']}: {result['error']}")
        elif status in ("answers", "no_answers"):
            if not result["answers"]:
                lines.append(f"{indent}No supported bindings. This does not establish explicit falsity.")
            for answer in result["answers"]:
                lines.append(indent + ", ".join(f"{key} = {render_term(value)}"
                             for key, value in sorted(answer["bindings"].items()))
                             if answer["bindings"] else indent + "true (no named bindings)")
                dependencies(answer, indent + "  ")
        else:
            lines.append(f"{indent}{status}: {result['query']}")
            dependencies(result, indent + "  ")
            if explain and status == "unknown":
                lines.append(f"{indent}  Neither the statement nor its explicit negation has supporting evidence.")

    for result in report["results"]:
        render(result)
    return "\n".join(lines)

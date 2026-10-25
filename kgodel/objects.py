"""Smalltalk-inspired objects whose methods produce logical evidence.

Single inheritance selects the nearest definition of a selector. Methods are
instantiated for each receiver, so inherited self sends dispatch to overrides.
No method executes host code or simulator operations.
"""

from __future__ import annotations

from .model import (Atom, KGodelError, Literal, Program, ProveQuery, Rule, SelfRef,
                    SlotRef, Var, render_term)


class ObjectSpace:
    def __init__(self, program: Program):
        self.program = program
        self.classes = {item.name: item for item in program.classes}
        self.instances = {item.name: item for item in program.objects}
        if len(self.classes) != len(program.classes):
            raise KGodelError("Duplicate class name.")
        if len(self.instances) != len(program.objects):
            raise KGodelError("Duplicate object name.")
        self.slots: dict[str, tuple[str, ...]] = {}
        self.methods: dict[str, dict] = {}
        for name in self.classes:
            chain, seen = [], set()
            current = name
            while current is not None:
                if current not in self.classes:
                    raise KGodelError(f"Unknown superclass {current}.")
                if current in seen:
                    raise KGodelError(f"Inheritance cycle involving {current}.")
                if len(chain) >= 64:
                    raise KGodelError("Class inheritance depth exceeds 64.")
                seen.add(current)
                definition = self.classes[current]
                chain.append(definition)
                current = definition.parent
            slots, methods = [], {}
            for definition in reversed(chain):
                for slot in definition.slots:
                    if slot in slots:
                        raise KGodelError(f"Duplicate or shadowed instance variable {slot} in {definition.name}.")
                    slots.append(slot)
                local = {}
                for index, method in enumerate(definition.methods, 1):
                    for literal in method.body:
                        terms = (*literal.atom.args, literal.atom.receiver)
                        for term in terms:
                            if isinstance(term, SlotRef) and term.name not in slots:
                                raise KGodelError(f"Unknown instance variable @{term.name} in {definition.name}.")
                    local.setdefault(method.selector, []).append((definition.name, index, method))
                methods.update(local)
            self.slots[name], self.methods[name] = tuple(slots), methods
        for instance in program.objects:
            if instance.class_name not in self.classes:
                raise KGodelError(f"Unknown class {instance.class_name} for object {instance.name}.")
            values = dict(instance.slots)
            if len(values) != len(instance.slots):
                raise KGodelError(f"Duplicate instance variable initializer in {instance.name}.")
            if set(values) != set(self.slots[instance.class_name]):
                expected = ", ".join(self.slots[instance.class_name]) or "(none)"
                raise KGodelError(f"Object {instance.name} must initialize exactly these instance variables: {expected}.")

    def validate_atom(self, atom: Atom):
        if atom.receiver is None:
            return
        if isinstance(atom.receiver, Var):
            available = any(atom.name in self.methods[item.class_name] for item in self.instances.values())
            if not available:
                raise KGodelError(f"No object understands message {atom.name}.")
            return
        if atom.receiver not in self.instances:
            raise KGodelError(f"Unknown message receiver {render_term(atom.receiver)}.")
        instance = self.instances[atom.receiver]
        if atom.name not in self.methods[instance.class_name]:
            raise KGodelError(f"Object {instance.name} does not understand message {atom.name}.")

    def validate_queries(self, queries):
        for query in queries:
            if isinstance(query, ProveQuery):
                self.validate_atom(query.literal.atom)
            else:
                for literal in query.assumptions:
                    self.validate_atom(literal.atom)
                self.validate_queries(query.body)

    def compile_rules(self) -> tuple[Rule, ...]:
        rules = []
        for instance in self.program.objects:
            values = dict(instance.slots)

            def resolve(term):
                if isinstance(term, SelfRef):
                    return instance.name
                if isinstance(term, SlotRef):
                    return values[term.name]
                return term

            for clauses in self.methods[instance.class_name].values():
                for owner, index, method in clauses:
                    body = tuple(Literal(Atom(item.atom.name, tuple(resolve(t) for t in item.atom.args),
                                              resolve(item.atom.receiver)), item.negative) for item in method.body)
                    for literal in body:
                        self.validate_atom(literal.atom)
                    head = Literal(Atom(method.selector, tuple(Var(name) for name in method.parameters),
                                        instance.name), method.negative)
                    rules.append(Rule(f"method:{owner}>>{method.selector}@{instance.name}#{index}", head, body))
                    if len(rules) > 10000:
                        raise KGodelError("Instantiated method rule limit exceeded (10000).")
        return tuple(rules)

    def validate_program(self):
        self.compile_rules()
        for literal in self.program.beliefs:
            self.validate_atom(literal.atom)
        for rule in self.program.rules:
            self.validate_atom(rule.head.atom)
            for literal in rule.body:
                self.validate_atom(literal.atom)
        for goal in self.program.goals:
            self.validate_atom(goal)
        for plan in self.program.plans:
            self.validate_atom(plan.target)
            for guard in plan.guards:
                self.validate_atom(guard.atom)
            self.validate_queries(plan.hypotheses)
            for step in plan.steps:
                if step.argument.receiver is not None:
                    raise KGodelError("Messages are logical queries; act and observe require simulator predicates.")
                for guard in step.requirements:
                    self.validate_atom(guard.atom)

    def describe(self) -> dict:
        return {
            "classes": [{"name": item.name, "parent": item.parent, "slots": list(self.slots[item.name]),
                         "methods": [{"selector": selector, "defined_in": clauses[0][0], "clauses": len(clauses)}
                                     for selector, clauses in self.methods[item.name].items()]}
                        for item in self.program.classes],
            "objects": [{"name": item.name, "class": item.class_name, "slots": dict(item.slots),
                         "selectors": list(self.methods[item.class_name])} for item in self.program.objects],
        }


def format_objects(report: dict) -> str:
    if not report["classes"] and not report["objects"]:
        return "No classes or objects declared."
    lines = []
    for definition in report["classes"]:
        parent = f" extends {definition['parent']}" if definition["parent"] else ""
        lines.append(f"Class {definition['name']}{parent}; slots: {', '.join(definition['slots']) or '(none)' }.")
        for method in definition["methods"]:
            lines.append(f"  {method['selector']} [{method['defined_in']}; {method['clauses']} clause(s)]")
    for instance in report["objects"]:
        lines.append(f"Object {instance['name']} : {instance['class']}")
        for name, value in instance["slots"].items():
            lines.append(f"  {name} = {render_term(value)}")
    return "\n".join(lines)

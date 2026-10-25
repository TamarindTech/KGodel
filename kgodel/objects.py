"""Smalltalk-inspired objects whose methods produce logical evidence.

Single inheritance selects the nearest definition of a selector. Methods are
instantiated for each receiver, so inherited self sends dispatch to overrides.
No method executes host code or simulator operations.
"""

from __future__ import annotations

from .model import (Atom, ExpressionQuery, KGodelError, Literal, Program, ProveQuery, Rule, SelfRef,
                    SlotRef, SuperRef, Var, expression_literals, render_term)


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
        # A super send has a lexical owner, even when its method is inherited.
        # Validate every declaration, including classes with no instances yet.
        for definition in program.classes:
            for method in definition.methods:
                for literal in method.body:
                    atom = literal.atom
                    if atom.lookup_class is not None:
                        raise KGodelError("Superclass lookup annotations are reserved for stored proofs.")
                    if any(isinstance(term, SuperRef) for term in atom.args):
                        raise KGodelError("Super is only allowed as a method message receiver.")
                    if isinstance(atom.receiver, SuperRef):
                        self.super_start(definition.name, atom.name)
        for instance in program.objects:
            if instance.class_name not in self.classes:
                raise KGodelError(f"Unknown class {instance.class_name} for object {instance.name}.")
            values = dict(instance.slots)
            if len(values) != len(instance.slots):
                raise KGodelError(f"Duplicate instance variable initializer in {instance.name}.")
            if set(values) != set(self.slots[instance.class_name]):
                expected = ", ".join(self.slots[instance.class_name]) or "(none)"
                raise KGodelError(f"Object {instance.name} must initialize exactly these instance variables: {expected}.")

    def super_start(self, owner: str, selector: str) -> str:
        parent = self.classes[owner].parent
        if parent is None:
            raise KGodelError(f"Super send in {owner} requires a superclass.")
        if selector not in self.methods[parent]:
            raise KGodelError(f"Superclass of {owner} does not understand message {selector}.")
        return parent

    def validate_atom(self, atom: Atom):
        if atom.lookup_class is not None:
            raise KGodelError("Superclass lookup annotations are reserved for stored proofs.")
        if any(isinstance(term, SuperRef) for term in (*atom.args, atom.receiver)):
            raise KGodelError("Super is only allowed as a method message receiver.")
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
            elif isinstance(query, ExpressionQuery):
                for literal in expression_literals(query.expression):
                    self.validate_atom(literal.atom)
            else:
                for literal in query.assumptions:
                    self.validate_atom(literal.atom)
                self.validate_queries(query.body)

    def compile_rules(self) -> tuple[Rule, ...]:
        rules = []
        for instance in self.program.objects:
            values = dict(instance.slots)
            pending, requested = [], set()

            def resolve(term):
                if isinstance(term, SelfRef):
                    return instance.name
                if isinstance(term, SlotRef):
                    return values[term.name]
                return term

            def compile_clauses(clauses, lookup_class=None):
                for owner, index, method in clauses:
                    body = []
                    for item in method.body:
                        atom = item.atom
                        arguments = tuple(resolve(term) for term in atom.args)
                        if isinstance(atom.receiver, SuperRef):
                            parent = self.super_start(owner, atom.name)
                            target = (parent, atom.name)
                            if target not in requested:
                                requested.add(target)
                                pending.append(target)
                            resolved = Atom(atom.name, arguments, instance.name, parent)
                        else:
                            resolved = Atom(atom.name, arguments, resolve(atom.receiver))
                            self.validate_atom(resolved)
                        body.append(Literal(resolved, item.negative))
                    head = Literal(Atom(method.selector, tuple(Var(name) for name in method.parameters),
                                        instance.name, lookup_class), method.negative)
                    rules.append(Rule(f"method:{owner}>>{method.selector}@{instance.name}#{index}", head, tuple(body)))
                    if len(rules) > 10000:
                        raise KGodelError("Instantiated method rule limit exceeded (10000).")

            for clauses in self.methods[instance.class_name].values():
                compile_clauses(clauses)
            # Expand only ancestor selectors referenced by super. Repeated sends
            # share support; ordinary self sends still use the public namespace.
            cursor = 0
            while cursor < len(pending):
                parent, selector = pending[cursor]
                cursor += 1
                compile_clauses(self.methods[parent][selector], parent)
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

from __future__ import annotations
import re
from typing import Dict, Iterator, List, Optional, Set, Tuple
from .graph import Graph
from .rewrite import dpo
from .rule import Rule, RuleError
from .matcher import Match, match_rule, find_iso, Matches
from . import state

RULE_NAME_RE = re.compile('(-)?\\s*([a-zA-Z_][\\.a-zA-Z0-9_]*)')

class Goal:
    """Stores a single goal in a Chyp proof
    """
    formula: Rule
    assumptions: Dict[str, Rule]
    def __init__(self, formula: Rule, assumptions: Optional[Dict[str, Rule]]=None):
        self.formula = formula
        self.assumptions = assumptions if assumptions else dict()
    
    def copy(self) -> Goal:
        assumptions = {asm: r.copy() for asm,r in self.assumptions.items()}
        return Goal(self.formula.copy(), assumptions)

class ProofState:
    """Stores the current proof state in a Chyp proof

    The proof state consists of a list of goals, a local context, a pointer to the `State` and
    a `sequence` indicating where in the theory document this occurs (and hence which theorems
    should be accessible).
    """
    def __init__(self, state: state.State, sequence: int, goals: Optional[List[Goal]] = None):
        self.state = state
        self.sequence = sequence
        self.goals = goals if goals else []
        self.context: Dict[str, Rule] = dict()
        self.errors: Set[str] = set()
        self.line = -1

    def copy(self) -> ProofState:
        goals = [g.copy() for g in self.goals]
        context = { rn: r.copy() for rn, r in self.context.items() }
        errors = self.errors.copy()
        ps = ProofState(self.state, self.sequence, goals)
        ps.line = self.line
        ps.context = context
        ps.errors = errors
        return ps
    
    def snapshot(self, part: state.ProofStepPart) -> ProofState:
        goals = [g.copy() for g in self.goals]
        ps = ProofState(self.state, self.sequence, goals)
        ps.line = part.line
        return ps

    def error(self, message: str) -> None:
        if not message in self.errors:
            self.state.errors.append((self.state.file_name, self.line, message))
            self.errors.add(message)

    def num_goals(self) -> int:
        return len(self.goals)

    def global_rules(self) -> List[str]:
        return [name for name, j in self.state.rule_sequence.items() if j <= self.sequence]

    def lookup_rule(self, rule_expr: str, goal_i:int=0, local: Optional[bool]=None) -> Optional[Rule]:
        """Lookup a rule

        This takes a rule expression, which is a rule name preceeded optionally by '-', and attempts
        to look up the rule first in the local context (i.e. rules added locally by the tactic via
        `add_*_to_context` methods) then assumptions local to goal 'goal_i', then the global context (i.e.
        rules defined the past of this proof).

        There is an optional parameter `local`. If `local` is True, then only rules from the local context
        and assumptions local to the current goal are returned. If it is False, only rules from the global
        context are returned. If it is not given, both contexts are used, searching in the local context first.

        It returns the Rule object and a bool indicating whether '-' appeared in the rule expression, which
        indicates that the converse of the rule should be returned.
        """


        # TODO: Changed now that converses need to show up in the rule dictionaries, similarly other
        # TODO: base transformations on rules, would need some equivalence class of possibilities.
        rule_name = rule_expr

        loc = local is None or local == True
        glo = local is None or local == False

        rule: Optional[Rule] = None
        if loc:
            if rule_name in self.context:
                rule = self.context[rule_name]
            elif rule_name in self.goals[goal_i].assumptions:
                rule = self.goals[goal_i].assumptions[rule_name]

        if glo and not rule and rule_name in self.state.rule_sequence:
            seq = self.state.rule_sequence[rule_name]
            if seq >= self.sequence:
                self.error(f'Attempting to use rule {rule_name} before it is defined/proven ({seq} >= {self.sequence}).')
                return None
            rule = self.state.rules[rule_name]

        if not rule:
            self.error(f'Rule {rule_name} not defined.')
            return None

        return rule.copy()

    def add_rule_to_context(self, rule_name: str) -> None:
        """Copies the given global rule into the local context, allowing it to be modified by the tactic
        """
        rule = self.lookup_rule(rule_name, local=False)

        # TODO: Simply adds a global rule to a local context, wouldn't need the lookup here.
        if rule:
            self.context[rule_name] = rule

    def target_rule(self, target: str = ''):
        if target == '' and len(self.goals) > 0:
            return self.goals[0].formula
        elif target in self.context:
            return self.context[target]
        else:
            return None

    def replace_lhs(self, new_lhs: Graph) -> None:
        """Replace the LHS of the top goal with the given graph

        For old_lhs the current LHS of the top goal, this adds a new goal "old_lhs = new_lhs"
        to the top of the goal stack. Typically this goal will be closed straight away by another
        tactic like "rule" or "simp".
        """
        try:
            r = Rule(self.lhs(), new_lhs)
            self.target_rule().lhs = new_lhs
            g = self.goals[0].copy()
            g.formula = r
            self.goals.insert(0, g)
        except RuleError as e:
            self.error(str(e))

    def replace_rhs(self, new_rhs: Graph) -> None:
        """Replace the LHS of the top goal with the given graph

        For old_lhs the current LHS of the top goal, this adds a new goal "old_lhs = new_lhs"
        to the top of the goal stack. Typically this goal will be closed straight away by another
        tactic like "rule" or "simp".
        """
        try:
            r = Rule(self.rhs(), new_rhs)
            self.target_rule().rhs = new_rhs
            g = self.goals[0].copy()
            g.formula = r
            self.goals.insert(0, g)
        except RuleError as e:
            self.error(str(e))

    def rewrite_lhs(self, rule_expr: str, target: str='') -> Iterator[Tuple[Match,Match]]:
        """Rewrite the LHS of the goal or a rule in the local context using the provided rule

        If `target` is '', then the rewrite is applied to the goal, otherwise it is applied to the named
        rule in the local context.
        """

        # if not self.__goal_lhs: return None
        rule = self.lookup_rule(rule_expr)
        if not rule: return None

        if not self.target_rule(target).lhs:
            return None

        # TODO: Rewrites all matches of that rule
        # TODO: - What if there are multiple matches?
        #           - How to select which one is applied?
        #           - What if there's genuine overlap? (Now rewriting might hide possible matches)
        for m_g in Matches(rule.lhs, self.target_rule(target).lhs):
            for m_h in dpo(rule, m_g):
                self.target_rule(target).lhs = m_h.codomain.copy()
                yield (m_g, m_h)

    def rewrite_rhs(self, rule_expr: str, target: str='') -> Iterator[Tuple[Match,Match]]:
        """Rewrite the RHS of the goal or a rule in the local context using the provided rule

        If `target` is '', then the rewrite is applied to the goal, otherwise it is applied to the named
        rule in the local context.
        """

        # if not self.__goal_rhs: return None
        rule = self.lookup_rule(rule_expr)
        if not rule: return None

        target_graph = self.target_rule(target).rhs
        if not target_graph:
            return None

        for m_g in Matches(rule.lhs, target_graph):
            for m_h in dpo(rule, m_g):
                self.target_rule(target).rhs = m_h.codomain.copy()
                yield (m_g, m_h)

    def rewrite_lhs1(self, rule_expr: str, target: str='') -> bool:
        for _ in self.rewrite_lhs(rule_expr, target):
            return True
        return False

    def rewrite_rhs1(self, rule_expr: str, target: str='') -> bool:
        for _ in self.rewrite_rhs(rule_expr, target):
            return True
        return False

    # TODO Instead of rewriting the goal, goal should be a path to rewrite both LHS & RHS into the same state.

    def validate_goal(self, i:int=0) -> Optional[Match]:
        if i >= 0 and i < len(self.goals):
            g = self.goals[i]
            return find_iso(g.formula.lhs, g.formula.rhs)
            # if (self.__local_state.status != state.Part.INVALID and iso):
            #     self.__local_state.status = state.Part.VALID
            #     return iso
        return None
    def try_close_goal(self, i:int=0) -> bool:
        if i >= 0 and i < len(self.goals):
            g = self.goals[i]
            if find_iso(g.formula.lhs, g.formula.rhs) != None:
                self.goals.pop(i)
                return True
        return False


    def lhs(self) -> Optional[Graph]:
        g = self.target_rule().lhs
        return g.copy() if g else None

    def rhs(self) -> Optional[Graph]:
        g = self.target_rule().rhs
        return g.copy() if g else None

    def lhs_size(self) -> int:
        g = self.target_rule().lhs
        return g.num_edges() + g.num_vertices() if g else 0

    def rhs_size(self) -> int:
        g = self.target_rule().rhs
        return g.num_edges() + g.num_vertices() if g else 0

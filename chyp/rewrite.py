#     chyp - An interactive theorem prover for string diagrams 
#     Copyright (C) 2022 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
from typing import Set, List, Dict, Iterator, Any, Optional, Iterable, Tuple
from .graph import Graph
from .matcher import Match
from .rule import Rule


def dpo(rule: Rule, match: Match) -> Iterable[Match]:
    """Do double-pushout rewriting

    Given a rule r and match of rule.lhs into a graph, return a match
    of rule.rhs into the rewritten graph.
    """
    # if not rule.is_left_linear():
    #     raise NotImplementedError("Only left linear rules are supported for now")

    # store the vertices we have split for id's on the LHS
    in_map: Dict[int, int] = dict()
    out_map: Dict[int, int] = dict()

    # compute the pushout complement
    # TODO: Pushout complement: Anything not touched by the rule
    def pushout_complement():
        ctx = match.codomain.copy()
        for e in rule.lhs.edges():
            ctx.remove_edge(match.edge_map[e])
            # TODO: Does not allow for dangling parts of edges (this I would want to support)

        for v in rule.lhs.vertices():
            v1 = match.vertex_map[v]
            if not rule.lhs.is_boundary(v):
                ctx.remove_vertex(v1)
                continue

            # TODO: Why does the LHS of the rule hold a boundary?

            in_count = len(rule.lhs.vertex_data(v).in_indices)
            out_count = len(rule.lhs.vertex_data(v).out_indices)
            if in_count == 1 and out_count == 1:
                input_vertices, output_vertices = ctx.explode_vertex(v1)
                if len(input_vertices) == 1 and len(output_vertices) == 1:
                    in_map[v] = input_vertices[0]
                    out_map[v] = output_vertices[0]
                else:
                    raise NotImplementedError("Rewriting modulo Frobenius not yet supported.")
            elif in_count > 1 or out_count > 1:
                raise NotImplementedError("Rewriting modulo Frobenius not yet supported.")
        return ctx

    h = pushout_complement()

    # this will embed rule.rhs into h
    # TODO: Match is used separately here, and doesn't use any of match's functionality
    result = Match(rule.rhs, h)

    # first map the inputs, using the matching of the lhs
    for vl,vr in zip(rule.lhs.inputs(), rule.rhs.inputs()):
        result.vertex_map[vr] = in_map[vl] if vl in in_map else match.vertex_map[vl]

    # next map the outputs. if the same vertex is an input and an output in rule.rhs, then
    # merge them in h.
    for vl,vr in zip(rule.lhs.outputs(), rule.rhs.outputs()):
        vr1 = out_map[vl] if vl in out_map else match.vertex_map[vl]
        if vr in result.vertex_map:
            h.merge_vertices(result.vertex_map[vr], vr1)
        else:
            result.vertex_map[vr] = vr1

    # then map the interior to new, fresh vertices
    for v in rule.rhs.vertices():
        if not rule.rhs.is_boundary(v): # TODO; Boundaries are already mapped above
            vd = rule.rhs.vertex_data(v)
            v1 = h.add_vertex(
                vtype=vd.vtype, size=vd.size,
                x=vd.x, y=vd.y, value=vd.value)
            result.vertex_map[v] = v1
            result.vertex_image.add(v1)

    # now add the edges from rhs to h and connect them using vmap1
    for e in rule.rhs.edges():
        ed = rule.rhs.edge_data(e)
        e1 = h.add_edge([result.vertex_map[v] for v in ed.s],
                        [result.vertex_map[v] for v in ed.t],
                        ed.value, ed.x, ed.y, ed.fg, ed.bg, ed.hyper)
        result.edge_map[e] = e1
        result.edge_image.add(e1)

    return [result]

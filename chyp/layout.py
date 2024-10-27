#     chyp - An interactive theorem prover for string diagrams 
#     Copyright (C) 2022 - Aleks Kissinger
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
import cvxpy as cp
from cvxpy.expressions.variable import Variable
from cvxpy.expressions.constants.constant import Constant
from cvxpy.problems.objective import Minimize
from cvxpy.problems.problem import Problem

from .graph import Graph
from .term import layer_decomp

def convex_layout(g: Graph) -> None:
    """A layout based on `layer_decomp` and convex optimisation

    Vertices and edges are placed in layers according to `layer_decomp`. Their
    y-coordinates are chosen by convex optimation to try to make connections as
    straight as possible subject to the constraints that inputs and outputs must
    be in order and at least 1.0 apart, and edges must be in order and not overlapping.
    """
    e_layers = layer_decomp(g)

    # initialise x-coordinates and rough y-coordinates
    x = -(len(e_layers) + 1) * 1.5
    inp = list(g.inputs())
    for i, v in enumerate(inp):
        vd = g.vertex_data(v)
        vd.x = x + 1.5
        vd.y = i - (len(inp)-1)/2

    x += 3.0

    for e_layer in e_layers:
        v_layer = []
        for i, e in enumerate(e_layer):
            ed = g.edge_data(e)
            ed.x = x
            ed.y = 2 * i - (len(e_layer)-1)
            v_layer += ed.t

        for i, v in enumerate(v_layer):
            vd = g.vertex_data(v)
            vd.x = x + 0.7
            vd.y = i - (len(v_layer)-1)/2
        x += 3.0

    outp = list(g.outputs())
    for i, v in enumerate(outp):
        vd = g.vertex_data(v)
        vd.x = x - 1.5
        vd.y = i - (len(outp)-1)/2

    if g.num_vertices() == 0 or g.num_edges() == 0: return

    # solve for better y-coordinates using convex optimisation
    
    # variables for the y-coordinates of vertices/edges
    vy = Variable(g.num_vertices(), 'vy')
    ey = Variable(g.num_edges(), 'ey')

    # maintain a table from vertex/edge names to variable indices
    vtab = { v : i for i, v in enumerate(g.vertices()) }
    etab = { e : i for i, e in enumerate(g.edges()) }

    constr = []
    opt = []
    # opt = [Constant(0.1) * vy[i] for i in range(g.num_edges())]

    for vlist in (g.inputs(), g.outputs()):
        for i in range(len(vlist) - 1):
            v1 = vlist[i]
            v2 = vlist[i+1]
            constr.append(vy[vtab[v2]] - vy[vtab[v1]] >= Constant(1))
            opt.append(Constant(0.1) * (vy[vtab[v2]] - vy[vtab[v1]]))

    for e_layer in e_layers:
        for i in range(len(e_layer)):
            e1 = e_layer[i]
            if i+1 >= len(e_layer): break
            e2 = e_layer[i+1]
            dist = (g.edge_data(e1).box_size() + g.edge_data(e2).box_size()) * 0.5
            constr.append(ey[etab[e2]] - ey[etab[e1]] >= Constant(dist))
            opt.append(Constant(0.1) * (ey[etab[e2]] - ey[etab[e1]]))

    for v in g.vertices():
        pos1 = vy[vtab[v]]
        pos2 = vy[vtab[v]]
        if len(g.in_edges(v)) >= 1:
            e = next(iter(g.in_edges(v)))
            t = g.target(e)
            y_shift = Constant(0.0 if len(t) <= 1 else ((t.index(v) / (len(t) - 1)) - 0.5))
            pos1 = ey[etab[e]] + y_shift

        if len(g.out_edges(v)) >= 1:
            e = next(iter(g.out_edges(v)))
            s = g.source(e)
            y_shift = Constant(0.0 if len(s) <= 1 else ((s.index(v) / (len(s) - 1)) - 0.5))
            pos2 = ey[etab[e]] + y_shift

        opt.append(pos1 - pos2)


    # problem = Problem(Minimize(cp.sum_squares(cp.vstack(opt))), constr)
    problem = Problem(Minimize(cp.norm1(cp.vstack(opt))), constr)
    problem.solve()
    min = None
    max = None
    for v,i in vtab.items():
        if not vy.value is None:
            y = vy.value[i]
            if min is None or y < min: min = y
            if max is None or y > max: max = y
            g.vertex_data(v).y = y

    if not min is None and not max is None:
        yshift = (min + max) * 0.5
        for v in g.vertices():
            g.vertex_data(v).y -= yshift
    else:
        yshift = 0

    for e,i in etab.items():
        y = ey.value[i]
        ed = g.edge_data(e)
        ed.y = y - yshift
        for j,v in enumerate(ed.t):
            if not g.is_boundary(v):
                yshift_v = 0 if len(ed.t) <= 1 else ((j / (len(ed.t) - 1)) - 0.5)
                g.vertex_data(v).y = ed.y + yshift_v



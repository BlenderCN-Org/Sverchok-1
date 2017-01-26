# -*- coding: utf-8 -*-
# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import collections

import svrx
from svrx.core.data_tree import SvDataTree


class SvTreeDB:
    def __init__(self):
        self.data_trees = {}

    def print(self, ng):
        for link in ng.links:
            self.get(link.from_socket).print()

    def get(self, socket=None):
        ng_id = socket.id_data.name
        s_id = socket.socket_id
        if ng_id not in self.data_trees:
            self.data_trees[ng_id] = {}
        ng_trees = self.data_trees[ng_id]
        if s_id not in ng_trees:
            ng_trees[s_id] = SvDataTree(socket=socket)
        return ng_trees[s_id]

    def clean(self, ng):
        ng_id = ng.name
        self.data_trees[ng_id] = {}

data_trees = SvTreeDB()


def topo_sort(links, start):
    """
    links = {node: [node0, node1, ..., nodeN]}
    start, node to start from
    """
    weights = collections.defaultdict(lambda: -1)

    def visit(node, weight):
        weights[node] = max(weight, weights[node])
        for from_node in links[node]:
            visit(from_node, weight + 1)
    visit(start, 0)
    return sorted(weights.keys(), key=lambda n: -weights[n])


def DAG(ng):
    links = collections.defaultdict(list)

    # needs to preprocess certain things
    # 1. reroutes
    # 2. wifi node replacement

    for l in ng.links:
        if not l.is_valid:
            links = {}
            break
        links[l.to_node].append(l.from_node)

    from_nodes = {l.from_node for l in ng.links}
    starts = {l.to_node for l in ng.links if l.to_node not in from_nodes}

    nodes = starts.union(from_nodes)
    node_list = []

    for node in starts:
        node_list.extend(topo_sort(links, node))

    return node_list


def recurse_levels(f, in_levels, out_levels, in_trees, out_trees):
    def assign_tree(tree, level, data):
        if tree is None:
            return
        if level == 0:
            tree.data = data
            tree.level = 0
        elif level == 1:
            for d in data:
                print(d)
                tree.add_child(data=d).level = 0
            tree.level = 1

    # print(f.label, in_levels, out_levels, in_trees)
    if all(t.level == l for t, l in zip(in_trees, in_levels)):
        args = []
        for tree in in_trees:
            args.append(tree.data)
        results = f(*args)

        if len(out_trees) > 1:
            for out_tree, l, result in zip(out_trees, out_levels, results):
                assign_tree(out_tree, l, result)
        elif len(out_trees) == 1:  # results is a single socket
            assign_tree(out_trees[0], out_levels[0], results)
        else:  # no output
            pass
    else:
        inner_trees = []
        max_length = 1
        for tree, l in zip(in_trees, in_levels):
            if tree.level != l:
                inner_trees.append(tree.children)
                max_length = max(len(tree.children), max_length)
            else:
                inner_trees.append(None)

        for i in range(max_length):
            args = []
            for tree, inner_tree in zip(in_trees, inner_trees):
                print(tree, inner_tree)
                if inner_tree is None:
                    args.append(tree)
                else:
                    if i < len(inner_tree):
                        args.append(inner_tree[i])
                    else:
                        args.append(inner_tree[-1])
            outs = []
            for ot in out_trees:
                if ot:
                    print(i, max_length, len(ot.children))
                    outs.append(ot.add_child())
                else:
                    outs.append(None)

            recurse_levels(f, in_levels, out_levels, args, outs)


def exec_node_group(node_group):
    print("exec tree")
    data_trees.clean(node_group)
    for node in DAG(node_group):
        print("exec node", node.name)
        func = node.compile()
        out_trees = []
        in_trees = []
        in_levels = []

        for param, level in func.parameters:
            in_levels.append(level)
            if isinstance(param, int):
                socket = node.inputs[param]
                if socket.is_linked:
                    #  here a more intelligent loookup is needed
                    #  to support reroutes and wifi replacement
                    tree = data_trees.get(socket.links[0].from_socket)
                else:
                    tree = SvDataTree(socket)
            else:  # prop parameter
                tree = SvDataTree(node=node, prop=param)
            in_trees.append(tree)

        for socket in node.outputs:
            if socket.is_linked:
                out_trees.append(data_trees.get(socket))
            else:
                out_trees.append(None)

        recurse_levels(func, in_levels, func.returns, in_trees, out_trees)
        print("finished with node", node.name)
        for ot in out_trees:
            if ot:
                ot.set_level()
                ot.print()

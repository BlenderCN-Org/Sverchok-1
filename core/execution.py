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
from itertools import chain

import svrx
from svrx.core.data_tree import SvDataTree
from svrx.core.type_conversion import needs_conversion, get_conversion
from svrx.nodes.node_base import Stateful

import svrx.core.timings as timings
from svrx.core.timings import add_time, time_func, start_timing, show_timings
import svrx.ui.error as error


class SvTreeDB:
    """
    Data storage loookup for sockets
    """
    def __init__(self):
        self.data_trees = {}
        self.links = {}

    def set_links(self, ng, links):
        self.links[ng.name] = links

    def print(self, ng):
        for link in ng.links:
            self.get(link.from_socket).print()

    def get(self, socket):
        ng_id = socket.id_data.name
        if not socket.is_output:
            if ng_id in self.links:
                return self.get(self.links[ng_id][socket])
            else:
                return self.get(socket.other)

        if ng_id not in self.data_trees:
            self.data_trees[ng_id] = {}
        ng_trees = self.data_trees[ng_id]
        if socket not in ng_trees:
            ng_trees[socket] = SvDataTree(socket=socket)
        return ng_trees[socket]

    def clean(self, ng):
        ng_id = ng.name
        self.data_trees[ng_id] = {}


data_trees = SvTreeDB()


class VirtualNode:
    """
    Used to represent node that don't have real conterpart in the layout
    """
    bl_idname = "SvRxVirtualNode"

    def __init__(self, func, ng):
        self.func = func
        self.id_data = ng
        self.inputs = []
        for _, name, default in func.inputs_template:
            self.inputs.append(VirtualSocket(self,
                                             name=name,
                                             default=default['default_value'],
                                             output=False))
        self.outputs = [VirtualSocket(self) for _ in func.returns]
        self.name = "VNode<{}>".format(func.label)

    def compile(self):
        return self.func


class VirtualLink:
    bl_idname = "SvRxVirtualLink"

    def __init__(self, from_socket, to_socket):
        self.from_socket = from_socket
        self.from_node = from_socket.node
        self.to_node = to_socket.node
        self.to_socket = to_socket
        self.id_data = self.from_node.id_data

        if isinstance(from_socket, VirtualSocket):
            from_socket.is_linked = True

        if isinstance(to_socket, VirtualSocket):
            to_socket.is_linked = True
            to_socket.other = from_socket


class VirtualSocket:
    def __init__(self, node, name=None, default=None, output=True):
        self.name = name or "VirtualSocket"
        self.node = node
        self.id_data = node.id_data
        self.default_value = default
        self.is_linked = False
        self.required = False
        self.is_output = output


def topo_sort(links, starts):
    """
    links = {node: [node0, node1, ..., nodeN]}
    starts, nodes to start from
    return a topologiclly sorted list
    """
    weights = collections.defaultdict(lambda: -1)

    def visit(node, weight):
        weights[node] = max(weight, weights[node])
        for from_node in links[node]:
            visit(from_node, weight + 1)

    for start in starts:
        visit(start, 0)
    return sorted(weights.keys(), key=lambda n: -weights[n])


def filter_reroute(ng):
    links = []
    for l in ng.links:
        if not l.is_valid:
            return []
        if l.to_node.bl_idname == 'NodeReroute':
            continue
        if l.from_node.bl_idname == 'NodeReroute':
            links.append(VirtualLink(l.to_socket.other, l.to_socket))
        else:
            links.append(l)

    return links


def compile_nodes(links, nodes):
    for link in links:
        if link.from_node not in nodes:
            nodes[link.from_node] = link.from_node.compile()
        if link.to_node not in nodes:
            nodes[link.to_node] = link.to_node.compile()


def verify_links(links, nodes, socket_links, real_nodes=False):
    skip = set()

    for i in range(len(links)):
        link = links[i]

        to_func = nodes[link.to_node]
        from_func = nodes[link.from_node]
        from_type = from_func.returns[link.from_socket.index][0]

        to_type = None
        socket_index = link.to_socket.index
        for index, _, s_type in to_func.parameters:
            if index == socket_index:
                to_type = s_type
        if needs_conversion(from_type, to_type):
            skip.add(i)
            func, to_index, from_index = get_conversion(from_type, to_type)
            ng = link.id_data
            if real_nodes:
                node = ng.nodes.new(func.bl_idname)
                node.hide = True
                node.select = False
                nodes[node] = node.compile()
                node.location = (link.from_node.location + link.to_node.location) * .5
                for idx in to_index:
                    links.append(ng.links.new(link.from_socket, node.inputs[idx]))
                links.append(ng.links.new(node.outputs[from_index], link.to_socket))
            else:
                node = VirtualNode(func, ng)
                nodes[node] = func
                for idx in to_index:
                    links.append(VirtualLink(link.from_socket, node.inputs[idx]))
                links.append(VirtualLink(node.outputs[from_index], link.to_socket))

    real_links = collections.defaultdict(list)

    for idx, link in enumerate(links):
        if idx in skip:
            continue
        real_links[link.to_node].append(link.from_node)
        socket_links[link.to_socket] = link.from_socket

    return real_links


def DAG(ng, nodes, socket_links):
    """
    preprocess the node layout in suitable way
    for topo_sort, removing reroutes and verifying
    type info
    """

    # needs to preprocess certain things
    # 1. reroutes, done
    # 2. type inf, done
    # 3. wifi node replacement

    links = filter_reroute(ng)
    compile_nodes(links, nodes)
    real_links = verify_links(links, nodes, socket_links, real_nodes=ng.rx_real_nodes)

    from_nodes = set(node for node in chain(*real_links.values()))
    starts = {node for node in real_links.keys() if node not in from_nodes}

    node_list = topo_sort(real_links, starts)
    return node_list


def recurse_levels(f, in_levels, out_levels, in_trees, out_trees):
    """
    does the exec for each node by recursively matching input trees
    and building output tree
    """

    if all(t.level == l for t, l in zip(in_trees, in_levels)):
        """
        All tree levels a correct, build arguments for node func
        call it and store results
        """
        args = []
        for tree in in_trees:
            if tree.level == 0:
                args.append(tree.data)
            else:
                args.append(list(tree))
        results = f(*args)
        if len(out_trees) > 1:
            if any(l > 0 for l in out_levels):
                results = zip(*results)
            for out_tree, l, result in zip(out_trees, out_levels, results):
                if out_tree:
                    out_tree.assign(l, result)
        elif len(out_trees) == 1 and out_trees[0]:  # results is a single socket
            out_trees[0].assign(out_levels[0], results)
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
                    outs.append(ot.add_child())
                else:
                    outs.append(None)

            recurse_levels(f, in_levels, out_levels, args, outs)


def collect_inputs(func, node):
    in_trees = []
    in_levels = []
    for param, level, data_type in func.parameters:
        in_levels.append(level)
        #  int refers to socket index, str to a property name on the node
        if isinstance(param, int):
            socket = node.inputs[param]
            if socket.is_linked:
                tree = data_trees.get(socket)
            elif socket.required:
                print("Warning Required socket not connected", node.name)
                msg = "Required socket not connected {}: {}".format(node.name, socket.name)
                raise SyntaxError(msg)
            else:
                tree = SvDataTree(socket)
        else:  # prop parameter
            tree = SvDataTree(node=node, prop=param)
        in_trees.append(tree)
    return in_trees, in_levels


def exec_node_group(node_group):
    data_trees.clean(node_group)
    error.clear(node_group)
    nodes = {}
    socket_links = {}
    do_timings = node_group.do_timings_text or node_group.do_timings_graphics
    if do_timings:
        timings.start_timing()

    add_time(node_group.name)
    add_time("DAG")
    dag_list = DAG(node_group, nodes, socket_links)
    data_trees.set_links(node_group, socket_links)
    add_time("DAG")
    try:
        for node in dag_list:

            func = nodes[node]
            add_time(node.bl_idname + ": " + node.name)

            if isinstance(func, Stateful):
                add_time(func.label)
                func.start()
                add_time(func.label)

            in_trees, in_levels = collect_inputs(func, node)

            out_trees = []
            for socket in node.outputs:
                if socket.is_linked:
                    out_trees.append(data_trees.get(socket))
                else:
                    out_trees.append(None)

            out_levels = [l for _, l in func.returns]

            if do_timings:
                recurse_levels(time_func(func), in_levels, out_levels, in_trees, out_trees)
            else:
                recurse_levels(func, in_levels, out_levels, in_trees, out_trees)

            for ot in out_trees:
                if ot:
                    ot.set_level()

            if isinstance(func, Stateful):
                add_time(func.label)
                func.stop()
                add_time(func.label)

            add_time(node.bl_idname + ": " + node.name)
        add_time(node_group.name)

        if do_timings:
            show_timings(node_group)
    except Exception as err:
        error.show(node, err)

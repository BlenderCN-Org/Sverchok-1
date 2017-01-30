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
import bpy
from bpy.props import EnumProperty, StringProperty

import inspect

import svrx

"""
For a node to exist there needs to be two things:

1) A function signature
2) A class representation of said signature for the node

For many cases 2 can ge generated from 1 but there is also
the possible to suppply parts of 2 like draw function or write the whole
thing for some complex cases

For certain cases a function signature that may need a dynamic function signature
which cannot be resolved easily we may need to add a way to directly generate
the internal "compiled" representation of a function signature.

That however isn't the first priority

"""

import svrx
from svrx.typing import SvRxBaseType, SvRxBaseTypeP, Required


class NodeBase:

    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname in {'SvRxTree'}

    def init(self, context):
        self.adjust_sockets()

    def compile(self):
        return _node_funcs[self.bl_idname]

    def draw_buttons(self, context, layout):
        props = self.compile().properties

        for name in props.keys():
            layout.prop(self, name)

    def adjust_sockets(self):
        func = self.compile()
        inputs_template = func.inputs_template
        for socket, socket_data in zip(self.inputs, inputs_template):
            socket.replace_socket(*socket_data)

        diff = len(self.inputs) - len(inputs_template)

        if diff > 0:
            for i in range(diff):
                self.inputs.remove(self.inputs[-1])
        elif diff < 0:
            print(inputs_template[diff:])
            for bl_id, name, default in inputs_template[diff:]:
                print(bl_id, name, default)
                s = self.inputs.new(bl_id, name)
                if default is not None:
                    s.default_value = default

        outputs_template = func.outputs_template

        for socket, socket_data in zip(self.outputs, outputs_template):
            socket.replace_socket(*socket_data)

        diff = len(self.outputs) - len(outputs_template)

        if diff > 0:
            for i in range(diff):
                self.outputs.remove(self.outputs[-1])
        elif diff < 0:
            for bl_id, name in outputs_template[diff:]:
                s = self.outputs.new(bl_id, name)
                s.default_value = default


_multi_storage = {}


class NodeDynSignature(NodeBase):

    def compile(self):
        func_dict, _ = _multi_storage[self.bl_idname]
        return func_dict[self.mode]

    def update_mode(self, context):
        self.adjust_sockets()
        self.id_data.update()

    def draw_buttons(self, context, layout):
        layout.prop(self, 'mode')
        super().draw_buttons(context, layout)


def add_multi(func):
    if not func.bl_idname in _multi_storage:
        _multi_storage[func.bl_idname] = ({}, [])
    func_dict, func_list = _multi_storage[func.bl_idname]
    func_list.append((func.label, func.label, func.label, func.id))
    func_dict[func.label] = func

def make_valid_identifier(name):
    """Create a valid python identifier from name for use a a part of class name"""
    if not name[0].isalpha():
        name = "Sv" + name
    return "".join(ch for ch in name if ch.isalnum() or ch == "_")


def class_factory(func):
    if hasattr(func, "cls_bases"):
        bases = func.cls_bases + (bpy.types.Node,)
    else:
        bases = (NodeBase, bpy.types.Node)

    cls_dict = {}
    cls_name = func.bl_idname
    cls_dict['bl_idname'] = func.bl_idname
    cls_dict['bl_label'] = func.label

    for name, prop in func.properties.items():
        cls_dict[name] = prop

    if hasattr(func, 'id'):
        func_dict, func_list = _multi_storage[func.bl_idname]
        default = func_list[0][0]
        cls_dict['mode'] = EnumProperty(items=func_list,
                                        default=default,
                                        update=NodeDynSignature.update_mode)
        cls_dict['bl_label'] = func.multi_label

    for name in {"draw_buttons", "draw_buttons_ext", "update", "draw_label"}:
        attr = getattr(func, name, None)
        if callable(attr):
            cls_dict[name] = attr

    cls = type(cls_name, bases, cls_dict)
    func.cls = cls


def get_signature(func):
    """
    annotate the function with meta data from the signature
    """
    sig = inspect.signature(func)

    func.inputs_template = []
    func.outputs_template = []
    func.properties = {}
    func.parameters = []
    func.returns = []

    if not hasattr(func, "label"):
        func.label = func.__name__

    for name, parameter in sig.parameters.items():
        annotation = parameter.annotation

        level = 0
        if isinstance(annotation, type):
            annotation = annotation()

        if isinstance(annotation, list):
            annotation, level = parse_type(annotation)

        if isinstance(annotation, SvRxBaseType):  # Socket type parameter

            if parameter.default is None or parameter.default is Required:
                socket_settings = None
            else:
                socket_settings = parameter.default

            if annotation.name:
                socket_name = annotation.name
            else:
                socket_name = name

            func.inputs_template.append((annotation.bl_idname, socket_name, socket_settings))

            func.parameters.append((len(func.inputs_template) - 1, level))

        elif isinstance(annotation, SvRxBaseTypeP):
            if not (parameter.default == inspect.Signature.empty or parameter.default is None):
                annotation.add("default", parameter.default)
            func.properties[name] = annotation.get_prop()
            print(func.properties[name], name, func.label)
            func.parameters.append((name, 0))
        else:
            raise SyntaxError

    print(sig.return_annotation)
    if sig.return_annotation is inspect.Signature.empty:
        return
    elif isinstance(sig.return_annotation, tuple):
        return_annotation = sig.return_annotation
    else:
        return_annotation = (sig.return_annotation, )

    for s_type in return_annotation:
        s_type, level = parse_type(s_type)
        socket_type = s_type.bl_idname
        if isinstance(s_type, SvRxBaseType):
            name = s_type.name
        else:
            name = s_type.__name__
        func.outputs_template.append((socket_type, name))
        func.returns.append(level)


def parse_type(s_type):
    """parse type into level, right now only supports one level
    """
    if isinstance(s_type, list):
        return s_type[0], 1
    else:
        return s_type, 0

_node_funcs = {}
_node_classes = {}

class NodeStateful(NodeBase):

    def compile(self):
        return _node_classes[self.bl_idname](self)

class Stateful:
    cls_bases = (NodeStateful,)

def stateful(cls):
    func = cls()
    get_signature(func)
    module_name = func.__module__.split(".")[-2]
    print(module_name)
    props = getattr(cls, 'properties', {})
    props.update(func.properties)

    class InnerStateful(cls, Stateful):
        category = module_name
        inputs_template = func.inputs_template.copy()
        outputs_template = func.outputs_template.copy()
        properties = props.copy()
        parameters = func.parameters.copy()
        returns = func.returns.copy()

    func_new = InnerStateful()
    class_factory(func_new)
    InnerStateful.node_cls = func_new.cls
    _node_classes[cls.bl_idname] = InnerStateful
    return InnerStateful



def node_func(*args, **values):
    def real_node_func(func):
        def annotate(func):
            for key, value in values.items():
                setattr(func, key, value)
        annotate(func)
        get_signature(func)

        if hasattr(func, 'id'):
            add_multi(func)
            if func.bl_idname in _node_funcs:
                func.categoy = 'SKIP'
                return func
            else:
                func.cls_bases = (NodeDynSignature,)
        class_factory(func)
        _node_funcs[func.bl_idname] = func
        module_name = func.__module__.split(".")[-2]
        func.category = module_name
        return func
    if args and callable(args[0]):
        return real_node_func(args[0])
    else:
        print(args, values)
        return real_node_func


def register():

    for func in _node_funcs.values():
        bpy.utils.register_class(func.cls)

    for cls in _node_classes.values():
        bpy.utils.register_class(cls.node_cls)



def unregister():
    for func in _node_funcs.values():
        bpy.utils.unregister_class(func.cls)

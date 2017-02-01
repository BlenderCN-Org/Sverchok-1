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

from svrx.typing import SvRxBaseType, SvRxBaseTypeP, Required
from svrx.nodes.classes import (NodeBase,
                                NodeDynSignature,
                                NodeStateful)

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
        func_dict, func_list = NodeDynSignature.get_multi(func)
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

        if isinstance(annotation, list):
            annotation, level = parse_type(annotation)
        if isinstance(annotation, type):
            annotation = annotation()

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
            func.parameters.append((name, 0))
        else:
            raise SyntaxError

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




class Stateful:
    cls_bases = (NodeStateful,)

    def start(self):
        pass

    def stop(self):
        pass

def stateful(cls):
    func = cls()
    get_signature(func)
    module_name = func.__module__.split(".")[-2]
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

    NodeStateful.add_cls(cls.bl_idname, InnerStateful)
    return InnerStateful



def node_func(*args, **values):
    def real_node_func(func):
        def annotate(func):
            for key, value in values.items():
                setattr(func, key, value)
        annotate(func)
        get_signature(func)

        if hasattr(func, 'id'):
            # has Dynamic Signature
            NodeDynSignature.add_multi(func)
            func_ref = NodeBase.get_func(func.bl_idname)
            if func_ref:
                func.categoy = 'SKIP'
                return func
            elif not hasattr(func, "cls_bases"):
                func.cls_bases = (NodeDynSignature,)
        class_factory(func)
        NodeBase.add_func(func)
        module_name = func.__module__.split(".")[-2]
        func.category = module_name
        return func
    if args and callable(args[0]):
        return real_node_func(args[0])
    else:
        print(args, values)
        return real_node_func

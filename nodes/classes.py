
import bpy
from bpy.props import EnumProperty, StringProperty

import importlib

_node_funcs = {}


class NodeBase:

    @staticmethod
    def add_func(func):
        _node_funcs[func.bl_idname] = func

    @staticmethod
    def get_func(bl_idname):
        return _node_funcs.get(bl_idname)

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
        self.adjust_inputs(func.inputs_template)
        self.adjust_outputs(func.outputs_template)


    def adjust_inputs(self, template):
        inputs_template = template
        for socket, socket_data in zip(self.inputs, inputs_template):
            socket.replace_socket(*socket_data)

        diff = len(self.inputs) - len(inputs_template)

        if diff > 0:
            for i in range(diff):
                self.inputs.remove(self.inputs[-1])
        elif diff < 0:
            for bl_id, name, default in inputs_template[diff:]:
                s = self.inputs.new(bl_id, name)
                if default is not None:
                    s.default_value = default

    def adjust_outputs(self, template):
        outputs_template = template

        for socket, socket_data in zip(self.outputs[:], outputs_template):
            socket.replace_socket(*socket_data)

        diff = len(self.outputs) - len(outputs_template)

        if diff > 0:
            for i in range(diff):
                self.outputs.remove(self.outputs[-1])
        elif diff < 0:
            for bl_id, name in outputs_template[diff:]:
                s = self.outputs.new(bl_id, name)


_node_classes = {}

class NodeStateful(NodeBase):

    @staticmethod
    def add_cls(bl_idname, func_cls):
        _node_classes[bl_idname] = func_cls

    @staticmethod
    def get_cls(bl_idname):
        return _node_classes[bl_idname]

    def compile(self):
        return NodeStateful.get_cls(self.bl_idname)(self)


_multi_storage = {}

class NodeDynSignature(NodeBase):

    @staticmethod
    def add_multi(func):
        if not func.bl_idname in _multi_storage:
            _multi_storage[func.bl_idname] = ({}, [])
        func_dict, func_list = _multi_storage[func.bl_idname]
        func_list.append((func.label, func.label, func.label, func.id))
        func_dict[func.label] = func
        NodeDynSignature.last_bl_idname = func.bl_idname

    @staticmethod
    def get_multi(func):
        return _multi_storage[func.bl_idname]


    def compile(self):
        func_dict, _ = _multi_storage[self.bl_idname]
        return func_dict[self.mode]

    def update_mode(self, context):
        self.adjust_sockets()
        self.id_data.update()

    def draw_buttons(self, context, layout):
        layout.prop(self, 'mode')
        super().draw_buttons(context, layout)



socket_types = [
    ('default', 'default', 'default', 0),
    ('SvRxFloatSocket', 'Float', 'Float', 1),
    ('SvRxIntSocket', 'Int', 'Int', 2),

]


class NodeMathBase(NodeDynSignature):

    first_input = EnumProperty(items=socket_types,
                              default="default",
                              update=NodeDynSignature.update_mode)
    second_input = EnumProperty(items=socket_types,
                                default="default",
                                update=NodeDynSignature.update_mode)

    def draw_label(self):
        """
        draws label for mutli mode nodes like math, logic and trigonometey
        """
        if not self.hide:
            return self.label or self.name

        name_or_value = [self.mode.title()]
        for socket in self.inputs:
            if socket.is_linked:
                name_or_value.append(socket.name.title())
            else:
                name_or_value.append(str(socket.default_value))
        return ' '.join(name_or_value)

    def draw_buttons_ext(self, context, layout):
        super().draw_buttons(context, layout)
        if self.inputs:
            layout.prop(self, "first_input", text="First input")
        if len(self.inputs) > 1:
            layout.prop(self, "second_input", text="Second input")



    def adjust_sockets(self):
        """Allow overrideing input types
        """
        func = self.compile()
        inputs_template = func.inputs_template.copy()

        if self.first_input != 'default' and inputs_template:
            inputs_template[0] = (self.first_input,) + inputs_template[0][1:]
        if self.second_input != 'default' and len(inputs_template) > 1:
            inputs_template[1] = (self.second_input,) + inputs_template[1][1:]

        self.adjust_inputs(inputs_template)
        self.adjust_outputs(func.outputs_template)


_node_scripts = {}

# This should be more generic and custom

FAIL_COLOR = (0.8, 0.1, 0.1)
READY_COLOR = (0, 0.8, 0.95)

class NodeScript(NodeBase):
    bl_idname = "SvRxNodeScript"
    bl_label = "Script"


    def init(self, context):
        super().init(context)


    def load_text(self, context=None):
        if self.text_file in bpy.data.texts:
            if self.text_file == 'Text':
                self.text_file = ''
                return
            mod = importlib.import_module("svrx.nodes.script.{}".format(self.text_file))
            importlib.reload(mod)
            self.adjust_sockets()
            self.color = READY_COLOR
            self.use_custom_color = True
        else:
            pass #  fail

    text_file = StringProperty(update=load_text)


    def draw_label(self):
        return "Script: {}".format(self.compile().label)

    def compile(self):
        return _node_scripts[self.text_file]

    @staticmethod
    def add(func):
        _node_scripts[func.module] = func


    def reset(self):
        self.text_file = ''
        self.inputs.clear()
        self.outputs.clear()

    def draw_buttons(self, context, layout):
        if not self.text_file:
            layout.prop_search(self, 'text_file', bpy.data, 'texts')
        else:
            row = layout.row()
            row.operator("node.svrxscript_ui_callback", text='Reset').fn_name = 'reset'
            row.operator("node.svrxscript_ui_callback", text='Reload').fn_name = 'load_text'


class SvScriptNodeLiteCallBack(bpy.types.Operator):

    bl_idname = "node.svrxscript_ui_callback"
    bl_label = "SvRx Script callback"
    fn_name = bpy.props.StringProperty(default='')

    def execute(self, context):
        getattr(context.node, self.fn_name)()
        return {'FINISHED'}


class RealNodeScript(NodeScript, bpy.types.Node):
    pass

def register():

    for func in _node_funcs.values():
        bpy.utils.register_class(func.cls)
    for cls in _node_classes.values():
        bpy.utils.register_class(cls.node_cls)



def unregister():
    for func in _node_funcs.values():
        bpy.utils.unregister_class(func.cls)

    for cls in _node_classes.values():
        bpy.utils.unregister_class(cls.node_cls)

import numpy as np

from svrx.nodes.node_base import node_func
from svrx.nodes.classes import NodeMathBase

from svrx.typing import Number, Float, Int
from svrx.util.function import constant

# pylint: disable=C0326

MATHNODE = 'SvRxNodeMath'

@node_func(bl_idname=MATHNODE, multi_label="Math", id=0, cls_bases=(NodeMathBase,))
def add(x: Number = 0.0, y: Number = 0.0) -> Number:
    return x + y

@node_func(bl_idname=MATHNODE, id=1)
def sub(x: Number = 0.0, y: Number = 0.0) -> Number:
    return x - y

@node_func(bl_idname=MATHNODE, id=2)
def mul(x: Number = 0.0, y: Number = 0.0) -> Number:
    return x * y

@node_func(bl_idname=MATHNODE, id=3)
def div(x: Number = 0.0, y: Number = 0.0) -> Number:
    return x / y

@node_func(bl_idname=MATHNODE, id=4)
def sqrt(x: Number = 1.0) -> Number:
    return x ** .5

@node_func(bl_idname=MATHNODE, id=5)
def copy_sign(x: Number = 1.0, y: Number = 0.0) -> Number:
    return np.copy_sign(x, y)


@node_func(bl_idname=MATHNODE, id=6)
def absolute(x: Number = 1.0) -> Number:
    return np.absolute(x)


@node_func(bl_idname=MATHNODE, id=9)
def reciprocal(x: Number = 0.0) -> Number:
    return 1 / x

@node_func(bl_idname=MATHNODE, id=10)
def negate(x: Number = 0.0) -> Number:
    return -x

@node_func(bl_idname=MATHNODE, id=11)
def add_1(x: Number = 0.0) -> Number:
    return x + 1

@node_func(bl_idname=MATHNODE, id=12)
def sub_1(x: Number = 0.0) -> Number:
    return x - 1

@node_func(bl_idname=MATHNODE, id=13)
def div_2(x: Number = 0.0) -> Number:
    return x / 2

@node_func(bl_idname=MATHNODE, id=14)
def mul_2(x: Number = 0.0) -> Number:
    return x * 2


@node_func(bl_idname=MATHNODE, id=15)
def as_int(x: Number = 0.0) -> Int:
    return x.astype(int)

@node_func(bl_idname=MATHNODE, id=16)
def round(x: Number = 0.0, y: Int = 0) -> Float:
    return x.round(y)


@node_func(bl_idname=MATHNODE, id=61)
@constant
def e() -> Float:
    return np.e

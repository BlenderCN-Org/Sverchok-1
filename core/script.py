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


import importlib
import importlib.abc
import importlib.util
import sys

import bpy


from svrx.util.importers import text_remap

class SvRxFinder(importlib.abc.MetaPathFinder):

    def find_spec(self, fullname, path, target=None):
        if fullname.startswith("svrx.nodes.script."):
            name = fullname.split(".")[-1]
            text_name = text_remap(name, reverse=True)
            if text_name in bpy.data.texts:
                return importlib.util.spec_from_loader(fullname, SvRxLoader(text_name))
            else:
                print("couldn't find file")

        elif fullname == "svrx.nodes.script":
            # load Module, right now uses real but empty module, will perhaps change
            pass
        return None


STANDAD_HEADER = "from svrx.nodes.node_base import node_script; from svrx.typing import *;"

class SvRxLoader(importlib.abc.SourceLoader):

    def __init__(self, text):
        self._text = text

    def get_data(self, path):
        text = bpy.data.texts[self._text]
        lines = [l.body for l in text.lines[1:]]
        lines.insert(0, STANDAD_HEADER + text.lines[0].body)
        source = "\n".join(lines)
        return source

    def get_filename(self, fullname):
        return "<bpy.data.texts[{}]>".format(self._text)


def register():
    sys.meta_path.append(SvRxFinder())

def unregister():
    for finder in sys.meta_path[:]:
        if isinstance(finder, SvRxFinder):
            sys.meta_path.remove(finder)

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


from itertools import chain, islice, accumulate

import numpy as np
from mathutils.geometry import normal

class SMesh:
    @classmethod
    def from_mesh(cls, mesh):
        return cls(SvVertices.from_mesh(mesh),
                   SvEdges.from_mesh(mesh),
                   SvPolygon.from_mesh(mesh))

    def __init__(self, vertices, edges, faces):
        self.vertices = vertices
        self.edges = edges
        self.faces = faces

    def calc_normals(self):
        """
        Face normals
        """
        normals = np.empty((len(self.faces), 3))
        for idx, face in enumerate(self.faces):
            normals[idx] = normal(self.vertices[face])
        self.faces.normals = normals

    def as_pydata(self):
        return self.vertices.as_pydata(), self.edges.as_pydata(), self.faces


class SvVertices:
    @classmethod
    def from_mesh(cls, mesh):
        vertices = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", vertices)
        vertices.shape = (len(mesh.vertices), 3)
        real_vertices = np.ones((len(mesh.vertices), 4))
        real_vertices[:,:3] = vertices
        return cls(real_vertices)

    def __getitem__(self, key):
        return self.vertices[key]

    def __init__(self, vertices):
        self.vertices = vertices

    def as_pydata(self):
        return self.vertices

class SvEdges:
    @classmethod
    def from_mesh(cls, mesh):
        # should use foreach_get
        return cls(np.array(mesh.edge_keys, dtype=np.uint32))

    def from_pydata(cls, edges):
        return cls(np.array(edges, dtype=np.uint32))

    def __init__(self, edges=None):
        self.edges = edges

    def __getitem__(self, key):
        return self.edges[key]

    def as_pydata(self):
        return self.edges

class SvPolygon:
    @classmethod
    def from_pydata(cls, faces):

        loop_info = np.zeros((len(faces), 2), dtype=np.uint32)
        loop_info[:, 0] = tuple(map(len, faces))
        loop_info[1:,1] = loop_info[:-1,0].cumsum()
        vertex_indices = np.fromiter(chain.from_iterable(faces),
                                     dtype=np.uint32,
                                     count=loop_info[:,0].sum())
        return cls(loop_info, vertex_indices)

    def __init__(self, loop_info=None, vertex_indices=None):
       self.loop_info = loop_info
       self.vertex_indices = vertex_indices

    @classmethod
    def from_mesh(cls, mesh):
        loop = np.zeros((len(mesh.polygons), 2), dtype=np.uint32)
        mesh.polygons.foreach_get("loop_total", loop[:,0])
        mesh.polygons.foreach_get("loop_start", loop[:,1])
        vertex_indices = np.empty(len(mesh.loops), dtype=np.uint32)
        mesh.loops.foreach_get("vertex_index", vertex_indices)
        return cls(loop, vertex_indices)


    def __getitem__(self, key):
        loop_start = self.loop_info[key, 1]
        loop_stop = loop_start + self.loop_info[key, 0]
        return self.vertex_indices[loop_start: loop_stop]

    def __len__(self):
        return self.loop_info.shape[0]

    def as_pydata(self):
        return [tuple(face) for face in self]

    def join(self, poly):
        offset = len(poly.vertex_indices)
        face_count = len(self)
        self.loop_info = np.concatenate((self.loop_info, poly.loop_info))
        self.vertex_indices = np.concatenate((self.vertex_indices, poly.vertex_indices + offset))
        self.loop_info[face_count:,1] += offset

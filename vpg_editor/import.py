import bpy
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty
from typing import List, Tuple


def parse_vpg(filepath: str) -> Tuple[List[Tuple[float, float, float]], List[Tuple[int, int, int]]]:
    vertices: List[Tuple[float, float, float]] = []  # 顶点坐标列表
    indices: List[Tuple[int, int, int]] = []         # 三角形索引列表

    def normalize_token(token: str) -> str:
        # 去除字符串两端空格和逗号
        return token.strip().strip(',').strip()

    with open(filepath, 'r', encoding='utf-8') as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split()
            if not parts:
                continue

            key = parts[0].lower()

            # 顶点行：以 'n' 开头
            if key.startswith('n'):
                if len(parts) < 4:
                    continue
                try:
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                    vertices.append((x, y, z))
                except ValueError:
                    continue

            # 面片行：以 'e' 开头
            elif key.startswith('e'):
                idx_tokens = parts[1:]
                if len(idx_tokens) < 3:
                    continue
                try:
                    tri = tuple(int(normalize_token(tok)) - 1 for tok in idx_tokens[:3])
                    if all(0 <= i < len(vertices) for i in tri):
                        indices.append(tri)
                except ValueError:
                    continue

    return vertices, indices


class VPG_EDITOR_OT_import_vpg(Operator, ImportHelper):
    bl_idname = 'vpg_editor.import_vpg'
    bl_label = 'Import VPG'
    bl_description = 'Import a VPG file'
    filename_ext = ".vpg"

    filter_glob: StringProperty(
        default="*.vpg",
        options={'HIDDEN'},
        maxlen=255,
    )  # type: ignore

    def execute(self, context):
        # 1. 获取文件路径
        filepath = getattr(self, "filepath", None)
        if not filepath:
            self.report({'ERROR'}, "No file path specified")
            return {'CANCELLED'}

        # 2. 解析 .vpg 文件
        vertices, indices = parse_vpg(filepath)
        if not vertices:
            self.report({'ERROR'}, "No vertices found in file")
            return {'CANCELLED'}
        if not indices:
            self.report({'WARNING'}, "No indices found; importing vertices only")

        # 3. 创建 Blender 网格对象
        mesh_name = bpy.path.display_name_from_filepath(filepath) or "VPG_Mesh"
        mesh = bpy.data.meshes.new(mesh_name)
        mesh.from_pydata(vertices, [], indices)
        mesh.update(calc_edges=True)

        # 4. 创建对象并添加到场景
        obj = bpy.data.objects.new(mesh_name, mesh)
        coll = context.collection if context.collection is not None else bpy.context.scene.collection
        coll.objects.link(obj)

        # 5. 选中并激活对象
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

        self.report({'INFO'}, f"Imported VPG: {len(vertices)} verts, {len(indices)} faces")
        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(VPG_EDITOR_OT_import_vpg.bl_idname, text="VPG (.vpg)")


def register():
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

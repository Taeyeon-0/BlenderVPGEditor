import bpy
import os
from pathlib import Path
from bpy.types import Operator
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty

from . import utils
from . import text_editor
from . import constants


class VPG_EDITOR_OT_export_vpg(Operator, ExportHelper):
    bl_idname = 'vpg_editor.export_vpg'
    bl_label = 'Export VPG'
    bl_description = 'Export current selected mesh to disk'
    filename_ext = ".vpg"

    filter_glob: StringProperty(
        default="*.vpg",
        options={'HIDDEN'},
        maxlen=255,
    )  # type: ignore

    def execute(self, context):
        # 检查选中的对象是否为 Mesh
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, 'No mesh object selected to export')
            return {'CANCELLED'}

        # 获取 Mesh 数据
        mesh = obj.data
        if mesh is None:
            self.report({'ERROR'}, 'Selected object has no mesh data')
            return {'CANCELLED'}

        # 获取映射路径
        try:
            mapped_path = mesh.get(constants.MESH_VPG_FILE_PATH)
        except Exception:
            mapped_path = None

        vpg_text: str | None = None

        # 优先使用内部文本编辑器中的内容，以确保头信息等手动修改也能导出
        if mapped_path:
            try:
                editor_text = text_editor.read_int_file(mapped_path)
            except Exception:
                editor_text = None

            if isinstance(editor_text, str):
                vpg_text = editor_text

        # 如果内部文本为空，则回退到网格上缓存的数据
        if vpg_text is None:
            try:
                cached_text = mesh.get(constants.MESH_DATA)
            except Exception:
                cached_text = None

            if isinstance(cached_text, str):
                vpg_text = cached_text

        scene = context.scene

        if vpg_text is None:
            self.report({'ERROR'}, 'No VPG data found for selected mesh')
            return {'CANCELLED'}

        # 获取用户导出路径
        selected_path = Path(self.filepath) if getattr(self, 'filepath', None) else None

        if selected_path is not None and str(selected_path) != '':
            try:
                utils.write_file(str(selected_path), vpg_text)
            except Exception as e:
                self.report({'ERROR'}, f'Failed to write file: {e}')
                return {'CANCELLED'}

            if constants.SCENE_SHORT_TO_FULL_FILENAME not in scene:
                scene[constants.SCENE_SHORT_TO_FULL_FILENAME] = {}

            # 更新路径映射
            scene[constants.SCENE_SHORT_TO_FULL_FILENAME][os.path.basename(str(selected_path))] = str(selected_path)

            try:
                # 更新 Mesh 路径
                mesh[constants.MESH_VPG_FILE_PATH] = str(selected_path)
            except Exception:
                pass

            self.report({'INFO'}, f'Exported VPG for {obj.name} -> {selected_path}')
            return {'FINISHED'}

        # 如果没有导出路径但有映射路径
        if mapped_path:
            try:
                if constants.SCENE_SHORT_TO_FULL_FILENAME in scene:
                    full_map = scene[constants.SCENE_SHORT_TO_FULL_FILENAME]
                    resolved = full_map.get(os.path.basename(mapped_path), mapped_path)
                else:
                    resolved = mapped_path

                utils.write_file(str(resolved), vpg_text)

                if constants.SCENE_SHORT_TO_FULL_FILENAME not in scene:
                    scene[constants.SCENE_SHORT_TO_FULL_FILENAME] = {}

                scene[constants.SCENE_SHORT_TO_FULL_FILENAME][os.path.basename(str(resolved))] = str(resolved)

                self.report({'INFO'}, f'Exported VPG for {obj.name} -> {resolved}')
                return {'FINISHED'}
            except Exception as e:
                self.report({'ERROR'}, f'Failed to write mapped file: {e}')
                return {'CANCELLED'}

        self.report({'ERROR'}, 'No export path specified and no mapped path available for selected mesh')
        return {'CANCELLED'}

    def invoke(self, context, event):
        # 设置导出对话框默认文件名
        obj = context.active_object
        default_name = None

        if obj is not None and obj.type == 'MESH':
            mesh = obj.data
            try:
                mapped_path = mesh.get(constants.MESH_VPG_FILE_PATH)
            except Exception:
                mapped_path = None

            # 优先使用映射路径文件名，否则使用对象名
            if mapped_path:
                default_name = os.path.basename(str(mapped_path))
            else:
                default_name = bpy.path.clean_name(obj.name) + '.vpg'

        if default_name:
            self.filepath = default_name

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


def menu_func_export(self, context):
    self.layout.operator(VPG_EDITOR_OT_export_vpg.bl_idname, text='VPG (.vpg)')


def register():
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

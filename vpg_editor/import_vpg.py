import traceback
import bpy
import bmesh

from pathlib import Path
from bpy.types import Operator
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty
from typing import Optional
from mathutils import Vector

from . import constants
from . import utils
from . import text_editor


def _deselect_all_objects(context: bpy.types.Context):
    """Safely deselect all objects without assuming a valid operator context."""
    try:
        if bpy.ops.object.select_all.poll():
            bpy.ops.object.select_all(action='DESELECT')
            return
    except Exception:
        pass
    try:
        for obj in context.selected_objects:
            try:
                obj.select_set(False)
            except Exception:
                continue
    except Exception:
        pass


def parse_vpg(filepath: str, return_maps: bool = True) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[int, int, int]],
    Optional[list[str]],
    Optional[dict[str, int]]
]:
    vertices: list[tuple[float, float, float]] = []
    indices: list[tuple[int, int, int]] = []
    node_index_to_id: list[str] = []  # index -> node_id
    node_id_to_index: dict[str, int] = {}  # 反查：node_id -> index

    def normalize_token(token: str) -> str:
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

            # Vertex line: starts with 'n'
            if key.startswith('n'):
                if len(parts) < 4:
                    continue
                try:
                    x = float(parts[1])
                    y = float(parts[2])
                    z = float(parts[3])
                except ValueError:
                    continue
                node_id = key
                if node_id in node_id_to_index:
                    continue
                vert_idx = len(vertices)
                vertices.append((x, y, z))
                node_index_to_id.append(node_id)
                node_id_to_index[node_id] = vert_idx

            # element line: starts with 'e'
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

    if return_maps:
        return vertices, indices, node_index_to_id, node_id_to_index
    else:
        return vertices, indices


def parse_vpg_text(filetext: str, return_maps: bool = True) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[int, int, int]],
    Optional[list[str]],
    Optional[dict[str, int]]
]:
    vertices: list[tuple[float, float, float]] = []
    indices: list[tuple[int, int, int]] = []
    node_index_to_id: list[str] = []  # index -> node_id
    node_id_to_index: dict[str, int] = {}  # 反查：node_id -> index

    def normalize_token(token: str) -> str:
        return token.strip().strip(',').strip()

    for raw in filetext.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if not parts:
            continue
        key = parts[0].lower()

        # Vertex line: starts with 'n'
        if key.startswith('n'):
            if len(parts) < 4:
                continue
            try:
                x = float(parts[1])
                y = float(parts[2])
                z = float(parts[3])
            except ValueError:
                continue
            node_id = key
            if node_id in node_id_to_index:
                continue
            vert_idx = len(vertices)
            vertices.append((x, y, z))
            node_index_to_id.append(node_id)
            node_id_to_index[node_id] = vert_idx

        # element line: starts with 'e'
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

    if return_maps:
        return vertices, indices, node_index_to_id, node_id_to_index
    else:
        return vertices, indices


def generate_mesh(
    obj: bpy.types.Object,
    mesh: bpy.types.Mesh,
    bm: bmesh.types.BMesh,
    file_path: str,
    vertices: list[tuple[float, float, float]],
    indices: list[tuple[int, int, int]],
    node_index_to_id: list[str]
):
    init_node_id_layer = bm.verts.layers.string.new(constants.BMESH_INIT_NODE_ID)
    node_id_layer = bm.verts.layers.string.new(constants.BMESH_NODE_ID)
    face_idx_layer = bm.faces.layers.int.new(constants.BMESH_FACE_IDX)
    transformed_positions: dict[str, Vector] = {}

    for i, (x, y, z) in enumerate(vertices):
        node_id = node_index_to_id[i]
        if node_id not in transformed_positions:
            transformed_positions[node_id] = obj.matrix_world.inverted() @ Vector((x, y, z))
        v = bm.verts.new(transformed_positions[node_id])
        bytes_node_id = bytes(node_id, 'utf-8')
        v[init_node_id_layer] = bytes_node_id
        v[node_id_layer] = bytes_node_id

    bm.verts.ensure_lookup_table()

    for i, tri in enumerate(indices):
        if tri is not None:
            face = bm.faces.new((bm.verts[tri[0]], bm.verts[tri[1]], bm.verts[tri[2]]))
            face[face_idx_layer] = i

    mesh[constants.MESH_VPG_FILE_PATH] = file_path
    mesh[constants.MESH_VERTEX_COUNT] = len(bm.verts)
    mesh[constants.MESH_TRIANGEL_COUNT] = len(bm.faces)


def import_vpg(
    context: bpy.types.Context,
    vpg_file_path: str,
    mesh_name: str,
    vertices: list[tuple[float, float, float]],
    indices: list[tuple[int, int, int]],
    node_index_to_id: list[str]
) -> bool:
    try:
        mesh = bpy.data.meshes.new(mesh_name)
        obj = bpy.data.objects.new(mesh_name, mesh)
        bm = bmesh.new()
        bm.from_mesh(mesh)

        generate_mesh(obj, mesh, bm, vpg_file_path, vertices, indices, node_index_to_id)
        bm.to_mesh(mesh)
        mesh.update(calc_edges=True)
        mesh[constants.MESH_DATA] = utils.read_file(vpg_file_path)

        vpg_collection = bpy.data.collections.get('VPG Objects')
        if vpg_collection is None:
            vpg_collection = bpy.data.collections.new('VPG Objects')
            context.scene.collection.children.link(vpg_collection)
        vpg_collection.objects.link(obj)

        _deselect_all_objects(context)

        try:
            obj.select_set(True)
        except Exception:
            pass
        try:
            context.view_layer.objects.active = obj
        except Exception:
            pass

        print('Done importing VPG.')
        return True

    except Exception as ex:
        tb = traceback.TracebackException.from_exception(ex, capture_locals=True)
        print("".join(tb.format()))
        utils.show_message_box('ERROR', 'Import VPG', 'ERROR importing VPG. Check the "System Console" for details.')
        return False


def reimport_vpg(
    context: bpy.types.Context,
    vpg_collection: bpy.types.Collection,
    obj: bpy.types.Object,
    vpg_file_path: str,
    vertices: list[tuple[float, float, float]],
    indices: list[tuple[int, int, int]],
    node_index_to_id: list[str]
) -> bool:
    try:
        try:
            _deselect_all_objects(context)
            obj.select_set(True)
            context.view_layer.objects.active = obj
        except Exception:
            pass

        try:
            if obj.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        mesh = obj.data
        if mesh is None:
            mesh = bpy.data.meshes.new(obj.name + "_reimport")
            obj.data = mesh

        bm = bmesh.new()
        try:
            generate_mesh(obj, mesh, bm, vpg_file_path, vertices, indices, node_index_to_id)
            bm.to_mesh(mesh)
            mesh.update(calc_edges=True)
            mesh[constants.MESH_DATA] = utils.read_file(vpg_file_path)
            mesh[constants.MESH_VPG_FILE_PATH] = vpg_file_path

            try:
                obj.data.update()
                obj.update_tag()
            except Exception:
                pass
        finally:
            try:
                bm.free()
            except Exception:
                pass

        print(f'Reimported VPG for object: {obj.name}')
        return True

    except Exception as ex:
        tb = traceback.TracebackException.from_exception(ex, capture_locals=True)
        print("".join(tb.format()))
        return False


def on_file_change(context: bpy.types.Context, file_path: str):
    vpg_collection: bpy.types.Collection | None = bpy.data.collections.get('VPG Objects')
    if vpg_collection is None:
        return

    editor_text = text_editor.read_int_file(file_path)

    for obj in list(vpg_collection.objects):
        if obj is None:
            continue
        mesh = obj.data
        if mesh is None:
            continue

        vpg_file_path = mesh.get(constants.MESH_VPG_FILE_PATH)
        if vpg_file_path is None or vpg_file_path != file_path:
            continue

        if editor_text is not None:
            vertices, indices, node_index_to_id, node_id_to_index = parse_vpg_text(editor_text, True)
        else:
            vertices, indices, node_index_to_id, node_id_to_index = parse_vpg(vpg_file_path, True)

        reimport_vpg(context, vpg_collection, obj, vpg_file_path, vertices, indices, node_index_to_id)


def _merge_geometry_with_existing(base_text: str, geometry_lines: list[str]) -> str:
    base_lines = base_text.splitlines()
    if not geometry_lines:
        return base_text

    geometry_indices: list[int] = []
    for idx, line in enumerate(base_lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if stripped[0].lower() in {'n', 'e'}:
            geometry_indices.append(idx)

    if not geometry_indices:
        result_lines = base_lines[:]
        if result_lines and result_lines[-1].strip():
            result_lines.append('')
        result_lines.extend(geometry_lines)
        return "\n".join(result_lines)

    first_idx = geometry_indices[0]
    last_idx = geometry_indices[-1]
    prefix = base_lines[:first_idx]
    suffix = base_lines[last_idx + 1:]

    result_lines: list[str] = []
    result_lines.extend(prefix)
    if result_lines and result_lines[-1].strip() and geometry_lines:
        result_lines.append('')
    result_lines.extend(geometry_lines)

    if suffix:
        if geometry_lines and suffix[0].strip() and geometry_lines[-1].strip():
            result_lines.append('')
        result_lines.extend(suffix)

    return "\n".join(result_lines)


def mesh_to_vpg_text(
    mesh: bpy.types.Mesh,
    obj: bpy.types.Object | None = None,
    base_text: str | None = None
) -> str:
    lines: list[str] = []
    bm: bmesh.types.BMesh | None = None
    using_edit_bmesh = False

    try:
        if obj is not None and obj.mode == 'EDIT':
            bm = bmesh.from_edit_mesh(mesh)
            using_edit_bmesh = True
        else:
            bm = bmesh.new()
            bm.from_mesh(mesh)

        bm.verts.ensure_lookup_table()

        try:
            node_id_layer = bm.verts.layers.string[constants.BMESH_NODE_ID]
        except Exception:
            node_id_layer = None

        try:
            init_node_id_layer = bm.verts.layers.string[constants.BMESH_INIT_NODE_ID]
        except Exception:
            init_node_id_layer = None

        vertex_entries: list[tuple[bmesh.types.BMVert, str]] = []
        numeric_pattern = True
        needs_renumber = False
        seen_numeric: set[str] = set()

        for idx, v in enumerate(bm.verts):
            node_id = None
            if node_id_layer is not None:
                try:
                    decoded = v[node_id_layer].decode('utf-8')
                    if decoded:
                        node_id = decoded.strip()
                except Exception:
                    pass

            if not node_id:
                node_id = f"n{idx + 1}"
                needs_renumber = True
            else:
                if len(node_id) < 2 or node_id[0].lower() != 'n' or not node_id[1:].isdigit():
                    numeric_pattern = False
                else:
                    normalized_id = 'n' + node_id[1:]
                    if node_id != normalized_id:
                        node_id = normalized_id
                        needs_renumber = True

            if node_id in seen_numeric:
                needs_renumber = True
            seen_numeric.add(node_id)

            expected_id = f"n{idx + 1}"
            if node_id != expected_id:
                needs_renumber = True

            vertex_entries.append((v, node_id))

        if numeric_pattern and needs_renumber:
            seen_numeric.clear()
            for idx, (vert, _) in enumerate(vertex_entries):
                new_id = f"n{idx + 1}"
                vertex_entries[idx] = (vert, new_id)
                if node_id_layer is not None:
                    try:
                        vert[node_id_layer] = new_id.encode('utf-8')
                    except Exception:
                        pass
                if init_node_id_layer is not None:
                    try:
                        vert[init_node_id_layer] = new_id.encode('utf-8')
                    except Exception:
                        pass

        if using_edit_bmesh:
            try:
                bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
            except Exception:
                pass

        for vert, node_id in vertex_entries:
            co = vert.co
            lines.append(f"{node_id} {co.x} {co.y} {co.z}")

        tri_counter = 1
        for face in bm.faces:
            verts = [vert.index for vert in face.verts]
            if len(verts) == 3:
                a, b, c = verts
                lines.append(f"e{tri_counter} {a+1} {b+1} {c+1}")
                tri_counter += 1
            elif len(verts) > 3:
                a = verts[0]
                for j in range(1, len(verts) - 1):
                    b = verts[j]
                    c = verts[j + 1]
                    lines.append(f"e{tri_counter} {a+1} {b+1} {c+1}")
                    tri_counter += 1

    finally:
        if bm is not None and not using_edit_bmesh:
            try:
                bm.free()
            except Exception:
                pass

    result = "\n".join(lines)
    if base_text:
        try:
            result = _merge_geometry_with_existing(base_text, lines)
        except Exception:
            result = "\n".join(lines)

    return result


def auto_convert_new_imported_meshes(
    context: bpy.types.Context,
    target_collection_name: str = 'VPG Objects'
) -> int:
    converted = 0
    vpg_collection = bpy.data.collections.get(target_collection_name)

    if vpg_collection is None:
        try:
            vpg_collection = bpy.data.collections.new(target_collection_name)
            context.scene.collection.children.link(vpg_collection)
        except Exception:
            vpg_collection = None

    # scan scene objects
    for obj in list(context.scene.objects):
        try:
            if obj is None or obj.type != 'MESH':
                continue

            mesh = obj.data
            if mesh is None:
                continue

            # skip if already converted (has vpg file path)
            if mesh.get(constants.MESH_VPG_FILE_PATH) is not None:
                continue

            # build vpg text
            vpg_text = mesh_to_vpg_text(mesh, obj)
            if not vpg_text:
                continue

            # create a pseudo filename for internal editor mapping
            safe_name = bpy.path.clean_name(obj.name)
            vpg_filename = f"{safe_name}.vpg"

            # write into internal editor
            try:
                text_editor.write_int_file(vpg_filename, vpg_text)
            except Exception:
                pass

            # attach metadata to mesh
            try:
                mesh[constants.MESH_DATA] = vpg_text
                mesh[constants.MESH_VPG_FILE_PATH] = vpg_filename
            except Exception:
                pass

            # move object to target collection
            if vpg_collection is not None:
                try:
                    for coll in list(obj.users_collection):
                        try:
                            coll.objects.unlink(obj)
                        except Exception:
                            pass
                    vpg_collection.objects.link(obj)
                except Exception:
                    pass

            converted += 1
        except Exception:
            continue

    if converted:
        print(f"Auto-converted {converted} object(s) to VPG format")

    return converted


class VPG_EDITOR_OT_import_vpg(Operator, ImportHelper):
    bl_idname = 'vpg_editor.import_vpg'
    bl_label = 'Import VPG'
    bl_description = 'Import a VPG file'
    filename_ext = ".vpg"

    # 文件过滤器设置
    filter_glob: StringProperty(
        default="*.vpg",
        options={'HIDDEN'},
        maxlen=255,
    )  # type: ignore

    def execute(self, context):
        # 1.获取文件路径
        global _vpg_file_path
        _vpg_file_path = Path(self.filepath).as_posix()

        if not _vpg_file_path:
            self.report({'ERROR'}, "No file path specified")
            return {'CANCELLED'}

        # 2.解析.vpg文件
        vertices, indices, node_index_to_id, node_id_to_index = parse_vpg(_vpg_file_path, True)

        if not vertices:
            self.report({'ERROR'}, "No vertices found in file")
            return {'CANCELLED'}

        if not indices:
            self.report({'WARNING'}, "No indices found; importing vertices only")

        # 3.创建 Blender 网格对象
        mesh_name = bpy.path.display_name_from_filepath(_vpg_file_path)

        try:
            import_vpg(context, _vpg_file_path, mesh_name, vertices, indices, node_index_to_id)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create mesh: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Imported VPG: {len(vertices)} verts, {len(indices)} faces")

        # 4. 写入内部编辑器
        text_editor.write_from_ext_to_int_file(_vpg_file_path)

        return {'FINISHED'}


def menu_func_import(self, context):
    self.layout.operator(VPG_EDITOR_OT_import_vpg.bl_idname, text="VPG (.vpg)")


def register():
    # register menu entry for File > Import
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

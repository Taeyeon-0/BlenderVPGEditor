import bpy
import traceback
from typing import Optional, Iterable

from . import import_vpg
from . import text_editor
from . import constants

# State
_HANDLER = None
_modified_objects: set[str] = set()
_do_export = False
_force_do_export = False
_poll_interval = 0.1


def _iter_objects_using_mesh(mesh: bpy.types.Mesh) -> Iterable[bpy.types.Object]:
    for obj in bpy.data.objects:
        try:
            if obj.type == 'MESH' and obj.data == mesh:
                yield obj
        except Exception:
            continue


def _collect_active_vpg_paths() -> set[str]:
    active: set[str] = set()
    for obj in bpy.data.objects:
        try:
            if obj is None or obj.type != 'MESH':
                continue
            mesh = obj.data
            if mesh is None:
                continue
            vpg_path = mesh.get(constants.MESH_VPG_FILE_PATH)
            if vpg_path:
                active.add(vpg_path)
        except Exception:
            continue
    return active


def _cleanup_orphan_internal_texts(scene: Optional[bpy.types.Scene]):
    if scene is None:
        return
    try:
        mapping = scene.get(constants.SCENE_SHORT_TO_FULL_FILENAME)
    except Exception:
        mapping = None
    if not mapping:
        return

    active_paths = _collect_active_vpg_paths()

    try:
        items = list(mapping.items())
    except AttributeError:
        try:
            items = [(key, mapping[key]) for key in list(mapping.keys())]
        except Exception:
            items = []

    for short_name, full_path in items:
        try:
            if full_path not in active_paths:
                print(f"[VPG Watcher] removing orphan VPG text {full_path}")
                text_editor.remove_int_file(full_path)
        except Exception:
            traceback.print_exc()


def _depsgraph_handler(depsgraph: bpy.types.Depsgraph):
    """Collect meshes/objects with VPG metadata that were updated."""
    global _do_export, _force_do_export
    try:
        updates = getattr(depsgraph, "updates", [])
        print(f"[VPG Watcher] depsgraph tick with {len(updates)} updates")

        for update in updates:
            id_data = getattr(update, "id", None)
            if id_data is None:
                print("[VPG Watcher] update without id data")
                continue

            candidate_objects: list[bpy.types.Object] = []

            if isinstance(id_data, bpy.types.Object) and id_data.type == 'MESH':
                base_obj = getattr(id_data, "original", None) or id_data
                obj = bpy.data.objects.get(base_obj.name)
                if obj is not None:
                    print(f"[VPG Watcher] update object candidate {obj.name}")
                    candidate_objects.append(obj)

            elif isinstance(id_data, bpy.types.Mesh):
                base_mesh = getattr(id_data, "original", None) or id_data
                print(f"[VPG Watcher] mesh update {base_mesh.name}")
                candidate_objects.extend(_iter_objects_using_mesh(base_mesh))

            if not candidate_objects:
                print("[VPG Watcher] no candidate objects found")
                continue

            if not (update.is_updated_geometry or update.is_updated_transform):
                print("[VPG Watcher] update not geometry/transform\n")
                continue

            for obj in candidate_objects:
                mesh = obj.data
                if mesh is None:
                    continue
                vpg_file_path = mesh.get(constants.MESH_VPG_FILE_PATH)
                if not vpg_file_path:
                    print(f"[VPG Watcher] object {obj.name} has no VPG metadata")
                    continue
                print(f"[VPG Watcher] detected update on {obj.name}")
                _modified_objects.add(obj.name)
                _do_export = True
                _force_do_export = True

        if _do_export:
            export_modified_objects(bpy.context)
            _do_export = False
            _force_do_export = False

    except Exception:
        traceback.print_exc()


def _sync_object_text(context: bpy.types.Context, obj: bpy.types.Object) -> bool:
    scene = context.scene if context and context.scene is not None else bpy.context.scene
    mesh = obj.data
    if mesh is None:
        return False

    vpg_file_path = mesh.get(constants.MESH_VPG_FILE_PATH)
    if not vpg_file_path:
        return False

    stored_text = mesh.get(constants.MESH_DATA)
    base_text = stored_text if isinstance(stored_text, str) else text_editor.read_int_file(vpg_file_path)
    if not isinstance(base_text, str):
        base_text = None

    new_text = import_vpg.mesh_to_vpg_text(mesh, obj, base_text)

    if isinstance(stored_text, str):
        old_text: str | None = stored_text
    elif isinstance(base_text, str):
        old_text = base_text
    else:
        old_text = None

    if new_text == old_text:
        return False

    print(f"[VPG Watcher] text change for {obj.name}? True; old_len={len(old_text) if isinstance(old_text, str) else 'None'} new_len={len(new_text)}")
    print(f"[VPG Watcher] updating text for {obj.name}")

    try:
        mesh[constants.MESH_DATA] = new_text
    except Exception:
        pass

    try:
        text_editor.write_int_file(vpg_file_path, new_text)
        short_name = text_editor.to_short_filename(vpg_file_path)
        if scene is not None:
            if constants.SCENE_PREV_TEXTS not in scene:
                scene[constants.SCENE_PREV_TEXTS] = {}
            scene[constants.SCENE_PREV_TEXTS][short_name] = new_text
        text_editor.show_int_file(vpg_file_path)
    except Exception:
        traceback.print_exc()

    return True


def export_modified_objects(context: Optional[bpy.types.Context] = None):
    """Export marked VPG objects (mesh -> internal text). Clears the modified set after processing."""
    global _modified_objects
    if context is None:
        context = bpy.context

    to_process = set(_modified_objects)
    _modified_objects.clear()

    for obj_name in to_process:
        try:
            obj = bpy.data.objects.get(obj_name)
            if obj is None or obj.type != 'MESH':
                continue
            _sync_object_text(context, obj)
        except Exception:
            traceback.print_exc()


def poll_active_operators():
    """Timer callback that checks active operator changes and triggers export when an operation finishes (or when forced). Returns interval to keep recurring."""
    global _do_export, _force_do_export
    try:
        context = bpy.context

        if _force_do_export or _do_export:
            export_modified_objects(context)
            _do_export = False
            _force_do_export = False

        # Fallback: actively compare active object even if depsgraph had no updates
        active_obj = context.active_object
        if (
            active_obj is not None
            and active_obj.type == 'MESH'
            and active_obj.mode == 'EDIT'
        ):
            mesh = active_obj.data
            if mesh is not None and mesh.get(constants.MESH_VPG_FILE_PATH):
                _sync_object_text(context, active_obj)

        _cleanup_orphan_internal_texts(context.scene)

    except Exception:
        traceback.print_exc()

    return _poll_interval


def register():
    global _HANDLER
    if _HANDLER is not None:
        return

    _HANDLER = _depsgraph_handler

    try:
        if _HANDLER not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(_HANDLER)
    except Exception:
        try:
            bpy.app.handlers.depsgraph_update_post.append(_HANDLER)
        except Exception:
            pass

    try:
        bpy.app.timers.register(poll_active_operators, first_interval=_poll_interval, persistent=True)
    except Exception:
        pass


def unregister():
    global _HANDLER, _modified_objects
    try:
        if _HANDLER is not None and _HANDLER in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(_HANDLER)
    except Exception:
        pass

    _HANDLER = None

    try:
        bpy.app.timers.unregister(poll_active_operators)
    except Exception:
        pass

    _modified_objects.clear()

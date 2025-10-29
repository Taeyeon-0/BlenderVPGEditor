import bpy
from . import text_editor
from . import import_vpg

check_file_interval = 0.1


def check_text_file_changes():
    context = bpy.context
    try:
        text_editor.check_open_int_file_for_changes(context)
    except Exception:
        pass
    return check_file_interval


def check_imported_meshes():
    context = bpy.context
    try:
        import_vpg.auto_convert_new_imported_meshes(context)
    except Exception:
        pass
    return check_file_interval


def register():
    bpy.app.timers.register(
        check_text_file_changes,
        first_interval=check_file_interval,
        persistent=True
    )
    bpy.app.timers.register(
        check_imported_meshes,
        first_interval=check_file_interval,
        persistent=True
    )


def unregister():
    bpy.app.timers.unregister(check_text_file_changes)
    bpy.app.timers.unregister(check_imported_meshes)

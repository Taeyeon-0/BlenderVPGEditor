import bpy
import os

from . import utils
from . import import_vpg
from . import constants

HISTORY_STACK_SIZE = 250
history_stack = []
history_stack_idx = -1


def to_short_filename(filename: str):
    return os.path.basename(filename)


def write_int_file(filename: str, text: str):
    scene = bpy.context.scene
    short_filename = to_short_filename(filename)

    if constants.SCENE_SHORT_TO_FULL_FILENAME not in scene:
        scene[constants.SCENE_SHORT_TO_FULL_FILENAME] = {}

    scene[constants.SCENE_SHORT_TO_FULL_FILENAME][short_filename] = filename

    if short_filename not in bpy.data.texts:
        bpy.data.texts.new(short_filename)

    file = bpy.data.texts[short_filename]
    curr_line, curr_char = file.current_line_index, file.current_character
    file.clear()
    file.write(text)
    file.cursor_set(curr_line, character=curr_char)

    if constants.SCENE_PREV_TEXTS not in scene:
        scene[constants.SCENE_PREV_TEXTS] = {}

    if short_filename not in scene[constants.SCENE_PREV_TEXTS]:
        scene[constants.SCENE_PREV_TEXTS][short_filename] = None


def remove_int_file(filename: str):
    scene = bpy.context.scene
    short_filename = to_short_filename(filename)

    try:
        text = bpy.data.texts.get(short_filename)
        if text is not None:
            bpy.data.texts.remove(text)
    except Exception:
        pass

    if scene is None:
        return

    try:
        if constants.SCENE_PREV_TEXTS in scene:
            prev_texts = scene[constants.SCENE_PREV_TEXTS]
            if short_filename in prev_texts:
                del prev_texts[short_filename]
    except Exception:
        pass

    try:
        if constants.SCENE_SHORT_TO_FULL_FILENAME in scene:
            filename_map = scene[constants.SCENE_SHORT_TO_FULL_FILENAME]
            if short_filename in filename_map:
                del filename_map[short_filename]
    except Exception:
        pass


def write_from_ext_to_int_file(filepath: str) -> str:
    filetext = utils.read_file(filepath)
    if filetext is None:
        return None
    write_int_file(filepath, filetext)
    return filetext


def write_from_int_to_ext_file(filepath: str) -> bool:
    short_filename = to_short_filename(filepath)
    text: bpy.types.Text | None = bpy.data.texts.get(short_filename)
    if text is None:
        return False
    res = utils.write_file(filepath, text.as_string())
    return res


def read_int_file(filename: str) -> str | None:
    short_filename = to_short_filename(filename)
    text: bpy.types.Text | None = bpy.data.texts.get(short_filename)
    if text is None:
        return None
    return text.as_string()


def show_int_file(filename: str):
    short_filename = to_short_filename(filename)
    text: bpy.types.Text | None = bpy.data.texts.get(short_filename)
    if text is None:
        return

    text_area = None
    for area in bpy.context.screen.areas:
        if area.type == "TEXT_EDITOR":
            text_area = area
            break

    if text_area is None or not text_area.spaces:
        return

    space = text_area.spaces[0]
    if space.text != text:
        space.text = text


def check_open_int_file_for_changes(context: bpy.types.Context, undoing_redoing=False):
    scene = context.scene
    if constants.SCENE_PREV_TEXTS not in scene:
        return False

    text = None
    text_area = None

    for area in context.screen.areas:
        if area.type == "TEXT_EDITOR":
            text_area = area
            break

    if text_area is not None:
        text = text_area.spaces[0].text

    if text is None:
        return False

    short_filename, curr_file_text = text.name, text.as_string()
    last_file_text = scene[constants.SCENE_PREV_TEXTS].get(short_filename, False)
    if last_file_text is False:
        return False

    filename = scene[constants.SCENE_SHORT_TO_FULL_FILENAME].get(short_filename)
    if filename is None:
        return False

    file_changed = False

    if curr_file_text != last_file_text:
        print("file changed")
        scene[constants.SCENE_PREV_TEXTS][short_filename] = curr_file_text
        import_vpg.on_file_change(context, filename)
        file_changed = True

    if not undoing_redoing and file_changed:
        global history_stack, history_stack_idx
        history_stack_idx += 1
        history_stack.insert(history_stack_idx, {short_filename: curr_file_text})
        history_stack = history_stack[:history_stack_idx + 1]
        if len(history_stack) > HISTORY_STACK_SIZE:
            history_stack.pop(0)

    return file_changed


def on_undo_redo(context: bpy.types.Context, undoing: bool):
    scene = context.scene
    if constants.SCENE_SHORT_TO_FULL_FILENAME not in scene or constants.SCENE_PREV_TEXTS not in scene:
        return

    global history_stack_idx
    if history_stack_idx == -1:
        return

    if undoing:
        history_stack_idx -= 1
    else:
        history_stack_idx += 1

    history_stack_idx = utils.clamp(history_stack_idx, 0, len(history_stack) - 1)
    entry = history_stack[history_stack_idx]
    filepaths = []

    for short_filename, text in entry.items():
        if short_filename not in bpy.data.texts:
            return

        file = bpy.data.texts[short_filename]
        curr_line, curr_char = file.current_line_index, file.current_character
        file.clear()
        file.write(text)
        file.cursor_set(curr_line, character=curr_char)

        filepaths.append(scene[constants.SCENE_SHORT_TO_FULL_FILENAME].get(short_filename))

    check_open_int_file_for_changes(context, True)

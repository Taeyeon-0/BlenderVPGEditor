import sys
import bpy

from . import constants

def show_message_box(icon='INFO', title="Message Box", message=""):
    def draw(self, context):
        self.layout.label(text=message)

    if not constants.UNIT_TESTING:
        bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def read_file(filepath: str):
    content = None
    try:
        with open(filepath, mode='r', encoding='utf8') as f:
            content = f.read()
    except IOError as e:
        print(e, file=sys.stderr)
    return content


def write_file(filepath: str, content: str):
    try:
        with open(filepath, mode='w', encoding='utf8') as f:
            f.write(content)
    except IOError as e:
        print(e, file=sys.stderr)
        return False
    return True


def clamp(value, min_value, max_value):
    return max(min_value, min(value, max_value))

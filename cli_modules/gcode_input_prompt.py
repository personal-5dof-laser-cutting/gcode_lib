from prompt_toolkit.widgets import TextArea, Label
from prompt_toolkit.layout import Dimension, Window
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.application.current import get_app


def handle_submit(buffer: Buffer, destination: Window = None):
    command_text = buffer.text
    buffer.text = ""

    if destination: 
        destination.children.append(Label(text=f"> {command_text}"))
        destination.vertical_scroll = destination.content_height

    else:
        print(command_text)

    get_app().invalidate()

gcode_input_prompt = TextArea(
    text=f"label",
    width=Dimension(),
    multiline=False,
    prompt="> ",
    accept_handler=handle_submit,
)




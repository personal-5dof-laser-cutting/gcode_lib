from prompt_toolkit.widgets import TextArea, Label, Frame
from prompt_toolkit.layout import Dimension, Window
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.application.current import get_app
from functools import partial


class GCodePrompt:
    destination: Window

    def __init__(self, destination: Window):
        self.destination = destination

    def handle_submit(self, buffer: Buffer):
        command_text = buffer.text
        buffer.text = ""

        if self.destination:
            self.destination.children.append(Frame(Label(text=f"> {command_text}")))
            # self.destination.vertical_scroll = self.destination.content_height

        else:
            print(command_text)

        app = get_app()
        app.invalidate()

    @property
    def ui(self):
        return TextArea(
            text=f"label",
            width=Dimension(),
            multiline=False,
            prompt="> ",
            accept_handler=self.handle_submit,
        )

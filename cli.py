from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.application.current import get_app
from prompt_toolkit.layout import Layout, Dimension, HSplit, ScrollablePane
from prompt_toolkit.widgets import Frame, TextArea, Label
from prompt_toolkit.buffer import Buffer

# --- DATA STRUCTURES --- #

gcode_labels = [
    Label(text="Gcode Line 1"),
    Label(text="Gcode Line 2"),
    Label(text="... many more lines ..."),
    Label(text="Gcode Line N"),
]

gcode_container = HSplit(
    gcode_labels
)

# --- KEY BINDINGS --- #

key_bindings = KeyBindings()


@key_bindings.add("c-q")
@key_bindings.add("c-c")
def exit(event) -> None:
    get_app().exit()


key_bindings.add("tab")(focus_next)
key_bindings.add("s-tab")(focus_previous)

# -- COMMAND PROMPT -- #

def handle_input_submit(buffer: Buffer):
    command_text = buffer.text
    buffer.text = ""

    gcode_labels.append(Label(text="Hello World!"))
    
    get_app().invalidate()


# --- LAYOUT --- #

scrollable_content = HSplit(
    gcode_labels
)

input_prompt = TextArea(
    text=f"label",
    width=Dimension(),
    multiline=False,
    prompt="> ",
    accept_handler=handle_input_submit,
)

root_container = HSplit(
    [
        Frame(ScrollablePane(scrollable_content)),
        Frame(input_prompt),
    ]
)
layout = Layout(container=root_container)


# --- APP --- #

application = Application(
    layout=layout, full_screen=True, mouse_support=True, key_bindings=key_bindings
)


def main():
    application.run()


if __name__ == "__main__":
    main()

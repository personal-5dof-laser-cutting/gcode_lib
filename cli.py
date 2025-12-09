from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.application.current import get_app
from prompt_toolkit.layout import Layout, Dimension, HSplit, ScrollablePane
from prompt_toolkit.widgets import Frame, TextArea, Label

# --- KEY BINDINGS --- #

key_bindings = KeyBindings()

@key_bindings.add("c-q")
@key_bindings.add("c-c")
def exit(event) -> None:
    get_app().exit()


key_bindings.add("tab")(focus_next)
key_bindings.add("s-tab")(focus_previous)

@key_bindings.add("c-q")
@key_bindings.add("c-c")
def exit(event) -> None:
    get_app().exit()

# -- COMMAND PROMPT -- #

input_bindings = KeyBindings()
@input_bindings.add('enter')
def handle_submit(event):
    event.cli.current_buffer.text = ""


# --- LAYOUT --- #

scrollable_content = HSplit(
    [
        Label(text="Gcode Line 1"),
        Label(text="Gcode Line 2"),
        Label(text="... many more lines ..."),
        Label(text="Gcode Line N"),
    ]
)

input_prompt = TextArea(text=f"label", width=Dimension(), multiline=False, prompt="> ",)
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

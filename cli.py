from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit
from prompt_toolkit.widgets import Frame

from cli_modules.gcode_input_prompt import gcode_input_prompt


def main():
    key_bindings = KeyBindings()

    @key_bindings.add("c-q")
    def exit(event) -> None:
        get_app().exit()

    root_container = HSplit(
        [
            Frame(gcode_input_prompt),
        ]
    )
    layout = Layout(container=root_container)

    application = Application(
        layout=layout, full_screen=True, mouse_support=True, key_bindings=key_bindings
    )
    application.run()


if __name__ == "__main__":
    main()

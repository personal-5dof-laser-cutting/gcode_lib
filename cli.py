from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.widgets import Frame

from cli_modules.gcode_input_prompt import GCodePrompt
from cli_modules.gcode_log_window import GCodeWindow


def main():
    key_bindings = KeyBindings()

    @key_bindings.add("c-q")
    def exit(event) -> None:
        get_app().exit()

    prompt = GCodePrompt(destination=None)
    log_window = GCodeWindow()

    prompt.destination = log_window.child_container

    root_container = HSplit(
        [
            Frame(log_window.ui),
            Frame(prompt.ui),
        ]
    )
    layout = Layout(container=root_container)

    application = Application(
        layout=layout, full_screen=True, mouse_support=True, key_bindings=key_bindings
    )
    application.run()


if __name__ == "__main__":
    main()

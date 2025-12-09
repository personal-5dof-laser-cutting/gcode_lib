from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.application.current import get_app

key_bindings = KeyBindings()

@key_bindings.add("c-c")
def exit(event) -> None:
    get_app().exit()

key_bindings.add("tab")(focus_next)
key_bindings.add("s-tab")(focus_previous)

application = Application(full_screen=True, mouse_support=True)


def main():
    application.run()


if __name__ == "__main__":
    main()

from prompt_toolkit.application import Application

application = Application(full_screen=True, mouse_support=True)


def main():
    application.run()


if __name__ == "__main__":
    main()

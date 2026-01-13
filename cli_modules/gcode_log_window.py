from prompt_toolkit.layout import Window, Container, HSplit
from prompt_toolkit.widgets import TextArea, Label
from prompt_toolkit.widgets import Frame


from prompt_toolkit.widgets import Label
from prompt_toolkit.layout import Window, HSplit

class GCodeWindow:
    def __init__(self):
        # 1. Initialize the list with the initial Label
        self.children = [Label(text="Hello World")]
        
        # 2. HSplit holds the list of Labels (This is the dynamic container)
        self.child_container = HSplit(children=self.children)
        
        # 3. Window wraps the HSplit (The Window correctly implements layout methods)
        self.window = Window(content=self.child_container)
        
        # 4. Frame wraps the Window (Optional, but useful for borders)
        self.frame = Frame(self.window)

    @property
    def ui(self):
        return self.frame # Or self.window if you skip the Frame
    
    @property
    def container_children(self):
        # Provide access to the actual list being modified
        return self.child_container.children

# --- How to Add a New Line (The Fix for the dynamic addition) ---

def add_new_output_line(gcode_window_instance, text):
    # Add a new Label to the HSplit's children list
    gcode_window_instance.container_children.append(Label(text=text))
    
    # Trigger the redraw
    get_app().invalidate() 

# Example of how the handler would look with this structure:
# def handle_submit(buffer: Buffer, destination_window: GCodeWindow):
#     command_text = buffer.text
#     buffer.text = ""
#     
#     destination_window.container_children.append(Label(text=f"> {command_text}"))
#     get_app().invalidate()

# gcode_lib

A generic serial bridge over websockets supporting non-blocking send and receive operations simultainously via multithreading.

## Install

Add with uv: `uv add "gcode_lib @ git+ssh://git@github.com/HCI-BP-25-26/gcode_lib.git@0.1.0"`
And then import it with `from gcode_interface import GCodeInterface`

## Usage

Recommended (context manager):

The context manager handles opening and closing the *context* even when errors occur.

```py
with GCodeInterface("ws://<INSERT IP>:<PORT>") as gif:
  gif.end("?")
  time.sleep(1)
  gif.recv()
  gif.recv()
  gif.recv()
```

Alternative:

```py
gif = GCodeInterface(ws://<INSERT IP>:<PORT>")
try:
  gif.send("?")
  time.sleep(1)
  gif.recv()
  gif.recv()
  gif.recv()
  gif.close()
except Exception as e:
  pass
finally:
  gif.close()
```



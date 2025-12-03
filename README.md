# gcode_lib

A generic serial bridge over websockets supporting non-blocking send and receive operations simultainously via multithreading.

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

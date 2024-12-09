import asyncio
import gbulb
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gst, Gtk

from .gst import Pipe
from .gui import App
from .ble import scanner

if __name__ == "__main__":
    gbulb.install()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    pipe = Pipe()
    pipe.set_state(True)
    app = App(pipe, application_id="wyrd.pc80b-bleak")
    loop.create_task(scanner(app))
    try:
        loop.run_forever(application=app)
    except KeyboardInterrupt:
        app.quit()

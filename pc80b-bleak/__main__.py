import asyncio
import gbulb
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gst, Gtk

from .gui import GUI
from .ble import scanner

if __name__ == "__main__":
    Gst.init()
    Gtk.init()
    gbulb.install()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    gui = GUI()
    app = Gtk.Application()
    loop.create_task(scanner(gui))
    app.connect('activate', gui.activate)
    try:
        loop.run_forever(application=app)
    except KeyboardInterrupt:
        app.quit()

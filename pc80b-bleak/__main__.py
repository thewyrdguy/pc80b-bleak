"""Command line entry point for pc80b-bleak streamer"""

from getopt import getopt
from sys import argv
from threading import Thread

# pylint: disable=relative-beyond-top-level  # Why is it complaining?...
from .gst import Pipe
from .gui import App
from .ble import Scanner

if __name__ == "__main__":
    topts, args = getopt(argv[1:], "vt")
    opts = dict(topts)
    (pipe := Pipe()).set_state(True)
    dathread = Scanner((app := App(pipe)), **opts)
    try:
        dathread.start()
        app.run()
    except KeyboardInterrupt:
        dathread.stop()
        app.quit()

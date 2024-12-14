"""Command line entry point for pc80b-bleak streamer"""

from asyncio import new_event_loop, set_event_loop
from getopt import getopt
from sys import argv

try:
    from gi.events import GLibEventLoopPolicy
    from asyncio import (  # pylint: disable=ungrouped-imports
        set_event_loop_policy,
    )

    set_event_loop_policy(GLibEventLoopPolicy())
    RUN_NATIVELY = True
except ImportError:
    import gbulb
    import gi

    gi.require_version("Gtk", "4.0")

    gbulb.install(gtk=True)
    RUN_NATIVELY = False

# pylint: disable=relative-beyond-top-level  # Why is it complaining?...
from .gst import Pipe
from .gui import App
from .ble import scanner, testsrc

if __name__ == "__main__":
    topts, args = getopt(argv[1:], "vt")
    opts = dict(topts)
    sigsrc = testsrc if "-t" in opts else scanner
    set_event_loop(loop := new_event_loop())
    (pipe := Pipe()).set_state(True)
    loop.create_task(
        sigsrc(app := App(pipe, application_id="wyrd.pc80b-bleak"))
    )
    try:
        if RUN_NATIVELY:
            app.run()
        else:
            loop.run_forever(application=app)
    except KeyboardInterrupt:
        app.quit()

import asyncio

try:
    from gi.events import GLibEventLoopPolicy

    asyncio.set_event_loop_policy(GlibEventLoopPolicy())
    run_natively = True
except ImportError:
    import gbulb
    import gi

    gi.require_version("Gtk", "4.0")

    gbulb.install(gtk=True)
    run_natively = False

from .gst import Pipe
from .gui import App
from .ble import scanner

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    pipe = Pipe()
    pipe.set_state(True)
    app = App(pipe, application_id="wyrd.pc80b-bleak")
    loop.create_task(scanner(app))
    try:
        if run_natively:
            app.run()
        else:
            loop.run_forever(application=app)
    except KeyboardInterrupt:
        app.quit()

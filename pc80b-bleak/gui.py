import gi
import cairo
from typing import Any

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

CRT_W = 720
CRT_H = 480

Gtk.init()


class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, pipe, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.pipe = pipe
        self.pipe.register_on_level_callback(self.on_level)

        # self.set_default_size(1080, 720)
        self.set_title("pc80b-bleak")

        picture = Gtk.Picture.new()
        picture.set_paintable(pipe.paintable)
        frame = Gtk.Frame()
        frame.set_child(picture)
        crt = Gtk.Box()
        crt.set_size_request(CRT_W, CRT_H)
        crt.append(frame)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.label = Gtk.Label.new("Scanning")
        vbox.append(self.label)
        vbox.append(crt)

        self.set_child(vbox)

    def on_level(self, **kwargs: Any) -> None:
        pass  # print(self.__class__.__name__, "LEVEL", kwargs)

    def report_ble(self, state: str) -> None:
        self.label.set_text(state)


class App(Adw.Application):
    def __init__(self, pipe, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pipe = pipe
        self.win = None
        self.pending_ble_report = None

        self.connect("activate", self.on_activate)
        self.connect("shutdown", self.on_close)

    def on_activate(self, app: Adw.Application) -> None:
        assert app is self
        self.win = AppWindow(self.pipe, application=app)
        self.win.present()
        if self.pending_ble_report is not None:
            self.win.report_ble(self.pending_ble_report)
            self.pending_ble_report = None

    def on_close(self, _):
        self.win.close()
        self.pipe.set_state(None)

    def report_ecg(self, ev) -> None:
        self.pipe.report_ecg(ev)

    def report_ble(self, state: str) -> None:
        if self.win is not None:
            self.win.report_ble(state)
        else:
            self.pending_ble_report = state


if __name__ == "__main__":
    import sys
    from .gst import Pipe

    pipe = Pipe()
    pipe.set_state(True)
    app = App(pipe, application_id="wyrd.pc80b-bleak")
    try:
        res = app.run(sys.argv)
        print("exit", res)
    except KeyboardInterrupt:
        app.quit()

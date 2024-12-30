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
        self.level_data = {}

        # self.set_default_size(1080, 720)
        self.set_title("pc80b-bleak")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.append(hbox)
        self.label = Gtk.Label.new("Scanning")
        self.label.set_hexpand(True)
        self.label.set_xalign(0.0)
        lbframe = Gtk.Frame()
        lbframe.set_child(self.label)
        lbbox = Gtk.Box()
        lbbox.append(lbframe)
        vbox.append(lbbox)
        self.set_child(vbox)

        self.monda = Gtk.DrawingArea()
        self.monda.set_size_request(40, CRT_H)
        self.monda.set_draw_func(self.draw_mon, None)
        lframe = Gtk.Frame()
        lframe.set_child(self.monda)
        lbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        lbox.append(lframe)
        hbox.append(lbox)

        picture = Gtk.Picture.new()
        picture.set_paintable(pipe.paintable)
        frame = Gtk.Frame()
        frame.set_child(picture)
        crt = Gtk.Box()
        crt.set_size_request(CRT_W, CRT_H)
        crt.append(frame)
        hbox.append(crt)

        rbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox.append(rbox)

    def draw_mon(self, monda, c, w, h, _):
        maxh = h - 30
        lvl = round((self.level_data.get("rms", [0.0])[0] + 35) * maxh / 35.0)
        if lvl < 0:
            lvl = 0
        if lvl > maxh:
            lvl = maxh
        c.set_source_rgb(0, 0, 0)
        c.rectangle(10, 10, w - 20, h - 20)
        c.fill()
        c.set_source_rgb(0, 1, 0)
        c.rectangle(15, 15 + maxh - lvl, w - 30, lvl)
        c.fill()

    def on_level(self, **kwargs: Any) -> None:
        self.level_data = kwargs
        self.monda.queue_draw()

    def report_ble(self, connected: bool, state: str) -> None:
        # show red/green indicator
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
            self.win.report_ble(*self.pending_ble_report)
            self.pending_ble_report = None

    def on_close(self, _):
        self.win.close()
        self.pipe.set_state(None)

    def report_ecg(self, ev) -> None:
        self.pipe.report_ecg(ev)

    def report_ble(self, connected: bool, state: str) -> None:
        self.pipe.report_ble(connected, state)
        if self.win is not None:
            self.win.report_ble(connected, state)
        else:
            self.pending_ble_report = connected, state


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

import gi
import cairo
from typing import Any

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from .gst import Pipe
from .ble import Scanner

CRT_W = 720
CRT_H = 480

Gtk.init()


class AppWindow(Gtk.ApplicationWindow):
    def __init__(self, app, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        super().__init__(application=app)
        self.level_data = {}
        self.connect("close-request", self.on_close)
        self.pipe = Pipe()
        self.pipe.register_on_level_callback(self.on_level)

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
        picture.set_paintable(self.pipe.paintable)
        frame = Gtk.Frame()
        frame.set_child(picture)
        crt = Gtk.Box()
        crt.set_size_request(CRT_W, CRT_H)
        crt.append(frame)
        hbox.append(crt)

        rbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        hbox.append(rbox)

        self.pipe.set_state(True)
        self.datathread = Scanner(self, **kwargs)
        self.datathread.start()

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

    def on_close(self, _) -> None:
        self.datathread.stop()
        self.datathread.join()
        self.pipe.set_state(None)

    def on_level(self, **kwargs: Any) -> None:
        self.level_data = kwargs
        self.monda.queue_draw()

    def report_ble(self, connected: bool, state: str) -> None:
        # show red/green indicator
        self.label.set_text(state)
        self.pipe.report_ble(connected, state)

    def report_ecg(self, ev) -> None:
        self.pipe.report_ecg(ev)


class App(Adw.Application):
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        super().__init__()
        self.connect("activate", self.on_activate)
        self.connect("shutdown", self.on_shutdown)

    def on_activate(self, app: Adw.Application) -> None:
        assert app is self
        self.win = AppWindow(self, *self.args, **self.kwargs)
        self.win.present()

    def on_shutdown(self, _):
        self.win.close()

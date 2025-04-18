from __future__ import annotations
import gi  # type: ignore [import-untyped]
from cairo import Context, Surface
from typing import Any, Dict, List, Literal

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import (  # type: ignore [import-untyped]
    Adw,
    Gdk,
    Gtk,
    GObject,
)

from .sgn import Signal
from .gst import Pipe

CRT_W = 720
CRT_H = 480

CSS = """
.onair {
    font-weight: bold;
    color: white;
    background-color: red;
}
.offair {
    color: gray;
    text-decoration: line-through;
}
"""

Gtk.init()


def spacepad(what: Gtk.Widget) -> None:
    what.set_spacing(5)
    what.set_margin_top(5)
    what.set_margin_bottom(5)
    what.set_margin_start(5)
    what.set_margin_end(5)


class AppWindow(Gtk.ApplicationWindow):  # type: ignore [misc] # no gtk stubs
    def __init__(
        self, app: Adw.Application, *args: Any, **kwargs: Any
    ) -> None:
        self.args = args
        self.kwargs = kwargs
        super().__init__(application=app)
        self.connect("close-request", self.on_close)

        self.level_data: Dict[str, List[float]] = {}
        self.signal = Signal(CRT_W, CRT_H)
        self.pipe = Pipe(
            CRT_W, CRT_H, on_level=self.on_level, on_error=self.on_gst_error
        )
        self.signal.register_pipe(self.pipe)
        self.pipe.register_signal(self.signal)

        kctrl = Gtk.EventControllerKey()
        kctrl.connect("key-pressed", self.on_keypress, None)
        self.add_controller(kctrl)

        # self.set_default_size(1080, 720)
        self.set_title("pc80b-bleak")
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_margin_top(5)
        self.set_child(vbox)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        self.monda = Gtk.DrawingArea()
        self.monda.set_size_request(40, CRT_H // 2)
        self.monda.set_halign(Gtk.Align.CENTER)
        self.monda.set_valign(Gtk.Align.CENTER)
        self.monda.set_draw_func(self.draw_mon, None)
        monframe = Gtk.Frame()
        monframe.set_child(self.monda)
        testswitch = Gtk.Switch()
        testswitch.set_halign(Gtk.Align.CENTER)
        testswitch.set_valign(Gtk.Align.CENTER)
        testswitch.set_active(False)
        testswitch.connect("state-set", self.on_testswitch)
        delaybtn = Gtk.SpinButton(orientation=Gtk.Orientation.VERTICAL)
        delaybtn.props.adjustment = Gtk.Adjustment(
            lower=500, upper=1500, step_increment=20, page_increment=200
        )
        delaybtn.set_numeric(True)
        delaybtn.set_value(self.pipe.get_adelay())
        delaybtn.connect("value-changed", self.on_adelay)
        lbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        spacepad(lbox)
        lbox.append(Gtk.Label(label="Test"))
        lbox.append(testswitch)
        lbox.append(Gtk.Label(label="Vol"))
        lbox.append(monframe)
        lbox.append(Gtk.Label(label="Delay"))
        lbox.append(delaybtn)
        lbox.append(Gtk.Label(label="(ms)"))
        hbox.append(lbox)

        mbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        picture = Gtk.Picture.new()
        picture.set_paintable(self.pipe.paintable)
        frame = Gtk.Frame()
        frame.set_child(picture)
        crtbox = Gtk.Box()
        crtbox.set_size_request(CRT_W, CRT_H)
        crtbox.append(frame)
        mbox.append(crtbox)

        model = Gtk.ListStore(GObject.TYPE_STRING)
        for el in (
            "rtmp://abuser.cardiobasel.ch/stream/live",
            "rtmp://a.rtmp.youtube.com/live2",
            "rtmp://live.twitch.tv/app",
        ):
            model.append((el,))
        completion = Gtk.EntryCompletion()
        completion.set_minimum_key_length(0)
        completion.set_model(model)
        completion.set_text_column(0)
        self.streamurl = Gtk.Entry()
        self.streamurl.set_completion(completion)
        self.streamurl.set_hexpand(True)
        self.streamurl.set_placeholder_text("Enter RTMP URL")
        self.streamurl.set_text("rtmp://abuser.cardiobasel.ch/stream/live")
        self.streamurl.set_alignment(0)
        self.streamurl.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, "edit-clear"
        )
        self.streamurl.set_icon_tooltip_markup(
            Gtk.EntryIconPosition.SECONDARY, "<b>Clear</b>"
        )
        self.streamurl.set_max_length(48)
        self.streamurl.connect("icon-press", self.on_clear_icon_press)
        self.streamurl.connect("activate", self.on_textentry_activate)
        self.streamkey = Gtk.Entry()
        self.streamkey.set_placeholder_text("Enter streaming key")
        self.streamkey.set_alignment(0)
        self.streamkey.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, "edit-clear"
        )
        self.streamkey.set_icon_tooltip_markup(
            Gtk.EntryIconPosition.SECONDARY, "<b>Clear</b>"
        )
        self.streamkey.set_max_length(48)
        self.streamkey.connect("icon-press", self.on_clear_icon_press)
        self.streamkey.connect("activate", self.on_textentry_activate)
        urlentry = Gtk.Box()
        spacepad(urlentry)
        urlentry.append(self.streamurl)
        urlentry.append(self.streamkey)
        urlframe = Gtk.Frame()
        urlframe.set_child(urlentry)
        urlbox = Gtk.Box()
        spacepad(urlbox)
        urlbox.append(urlframe)
        self.bcast = Gtk.Switch()
        self.bcast.set_halign(Gtk.Align.END)
        self.bcast.set_valign(Gtk.Align.CENTER)
        self.bcast.set_state(False)
        self.bcast.connect("state-set", self.on_bcast)
        urlbox.append(self.bcast)
        mbox.append(urlbox)

        hbox.append(mbox)

        rbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        spacepad(rbox)
        self.onairlbl = Gtk.Label(label="On\nAir")
        self.onairlbl.add_css_class("onair")
        self.offairlbl = Gtk.Label(label="Off\nAir")
        self.offairlbl.add_css_class("offair")
        self.onairframe = Gtk.Frame()
        self.onairframe.set_child(self.offairlbl)
        rbox.append(self.onairframe)
        hbox.append(rbox)

        vbox.append(hbox)

        self.label = Gtk.Label.new("Uninitialised")
        self.label.set_hexpand(True)
        self.label.set_xalign(0.0)
        lbframe = Gtk.Frame()
        lbframe.set_child(self.label)
        lbbox = Gtk.Box()
        spacepad(lbbox)
        lbbox.append(lbframe)
        vbox.append(lbbox)

        self.pipe.set_state(True)
        self.signal.start(False)

    def draw_mon(
        self,
        monda: Gtk.DrawingArea,
        c: Context[Surface],
        w: int,
        h: int,
        udata: Literal[None],
    ) -> None:
        maxh = h - 20
        c.set_source_rgb(0, 0, 0)
        c.rectangle(5, 5, w - 10, h - 10)
        c.fill()
        for lr in (0, 1):
            lvl = round(
                (self.level_data.get("rms", [0.0, 0.0])[lr] + 35) * maxh / 35.0
            )
            if lvl < 0:
                lvl = 0
            if lvl > maxh:
                lvl = maxh
            c.set_source_rgb(0, 1, 0)
            c.rectangle(10 + lr * 14, 10 + maxh - lvl, 10, lvl)
            c.fill()

    def on_testswitch(self, switch: Gtk.Widget, state: bool) -> None:
        self.signal.start(state)

    def on_adelay(self, sbtn: Gtk.Widget) -> None:
        # print("delay spinbutton", sbtn.get_value_as_int())
        self.pipe.set_adelay(sbtn.get_value_as_int())

    def on_textentry_activate(self, entry: Gtk.Widget) -> None:
        if not self.bcast.get_active():
            self.bcast.set_active(True)

    def on_bcast(self, entry: Gtk.Widget, state: bool) -> None:
        # print("bcast switch", state, "url", self.streamurl.get_text())
        if state:
            self.pipe.start_broadcast(
                self.streamurl.get_text(), self.streamkey.get_text()
            )
            self.label.set_text("Broadcast started")
        else:
            self.pipe.stop_broadcast()
            self.label.set_text("Broadcast stopped")
        self.onairframe.set_child(self.onairlbl if state else self.offairlbl)

    def on_keypress(
        self,
        event: Gtk.Event,
        keyval: int,
        keycode: int,
        state: Gdk.ModifierType,
        udata: Literal[None],
    ) -> None:
        if keyval == Gdk.KEY_q and state & Gdk.ModifierType.CONTROL_MASK:
            self.close()

    def on_clear_icon_press(
        self, entry: Gtk.Widget, icon_pos: Gtk.EntryIconPosition
    ) -> None:
        if icon_pos == Gtk.EntryIconPosition.SECONDARY:
            entry.get_buffer().set_text("", 0)

    def on_close(self, _: Any) -> None:
        self.signal.stop()
        self.pipe.set_state(None)

    def on_level(self, **kwargs: List[float]) -> None:
        self.level_data = kwargs
        self.monda.queue_draw()

    def on_gst_error(self, error: Gtk.Error) -> None:
        self.bcast.set_active(False)
        self.label.set_text(str(error))


class App(Adw.Application):  # type: ignore [misc] # no stubs
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        super().__init__()
        self.get_style_manager().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self.connect("activate", self.on_activate)
        self.connect("shutdown", self.on_shutdown)

    def on_activate(self, app: Adw.Application) -> None:
        assert app is self
        self.win = AppWindow(self, *self.args, **self.kwargs)
        self.win.present()

    def on_shutdown(self, _: Any) -> None:
        self.win.close()

import gi
import cairo
from typing import Any, Optional

gi.require_version("GLib", "2.0")
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

CRT_W = 720
CRT_H = 480

CAPS = (
    f"video/x-raw,format=RGBA,bpp=32,depth=32,width={CRT_W},height={CRT_H}"
    ",red_mask=-16777216,green_mask=16711680,blue_mask=65280"
    ",alpha_mask=255,endianness=4321,framerate=1/30"
)

Gst.init()


class Pipe:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.pipeline = Gst.Pipeline.new()
        self.on_level_callback = None

        bus = self.pipeline.get_bus()
        bus.connect("message::eos", self.on_eos)
        bus.connect("message::error", self.on_error)

        gtksink = Gst.ElementFactory.make("gtk4paintablesink", None)
        self.paintable = gtksink.get_property("paintable")
        if not self.paintable.props.gl_context:
            raise RuntimeError("Refusing to run without OpenGL")
        sink = Gst.ElementFactory.make("glsinkbin", None)
        sink.set_property("sink", gtksink)

        self.src = Gst.ElementFactory.make("appsrc", None)
        self.src.set_property("format", Gst.Format.TIME)

        self.pipeline.add(self.src)
        self.pipeline.add(sink)

        self.src.link_filtered(sink, Gst.Caps.from_string(CAPS))
        sink.set_property("sync", True)

        self.src.connect("need-data", self.on_need_data)

        self.pipeline.add(
            asrc := Gst.ElementFactory.make("autoaudiosrc", None)
        )
        self.pipeline.add(
            acnv := Gst.ElementFactory.make("audioconvert", None)
        )
        self.pipeline.add(alvl := Gst.ElementFactory.make("level", None))
        self.pipeline.add(asnk := Gst.ElementFactory.make("fakesink", None))
        asrc.link(acnv)
        acnv.link_filtered(
            alvl, Gst.Caps.from_string("audio/x-raw,channels=2")
        )
        alvl.link(asnk)
        asnk.set_property("sync", True)
        bus.add_signal_watch()
        bus.connect("message::element", self.on_level)

    def on_eos(self, bus, msg):
        print("End of stream")

    def on_error(self, bus, msg):
        error = msg.parse_error()
        print("ERROR", error)

    def register_on_level_callback(self, callback) -> None:
        self.on_level_callback = callback

    def on_level(self, bus, msg):
        s = msg.get_structure()
        kwargs = {k: s.get_value(k) for k in ("rms", "peak", "decay")}
        if self.on_level_callback is not None:
            self.on_level_callback(**kwargs)
        else:
            print("LEVEL", kwargs)

    def on_need_data(self, source, amount):
        with cairo.ImageSurface(cairo.FORMAT_ARGB32, CRT_W, CRT_H) as image:
            context = cairo.Context(image)
            context.set_source_rgba(0.5, 0.0, 0.0, 1.0)
            context.rectangle(0, 0, CRT_W, CRT_H)
            context.fill()
            context.select_font_face(
                "sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD
            )
            context.set_font_size(48)
            text = "No Signal"
            (x, y, w, h, dx, dy) = context.text_extents(text)
            context.move_to((CRT_W - w) / 2.0, (CRT_H - h) / 2.0)
            context.set_source_rgba(1.0, 1.0, 1.0, 1.0)
            context.show_text(text)
            # Gst.Buffer.add_reference_timestamp_meta(
            #   self, reference, timestamp, duration
            # )
            # timestamp/x-unix: for timestamps based on the UNIX epoch
            self.src.emit(
                "push-buffer",
                Gst.Buffer.new_wrapped_bytes(GLib.Bytes.new(image.get_data())),
            )

    def set_state(self, state: Optional[bool]):
        if state is None:
            self.pipeline.set_state(Gst.State.NULL)
        elif state:
            self.pipeline.set_state(Gst.State.PLAYING)
        else:
            self.pipeline.set_state(Gst.State.PAUSED)

    def report_ecg(self, ev) -> None:
        print("DATASINK", ev)

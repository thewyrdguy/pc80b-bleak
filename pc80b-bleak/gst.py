import gi
import cairo
from typing import Any, Optional

from .drw import Drw

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
        self.on_level_callback = None
        self.pl = Gst.Pipeline.new()
        bus = self.pl.get_bus()
        bus.connect("message::eos", self.on_eos)
        bus.connect("message::error", self.on_error)

        # Local video sink
        gtksink = Gst.ElementFactory.make("gtk4paintablesink", None)
        self.paintable = gtksink.get_property("paintable")
        if not self.paintable.props.gl_context:
            raise RuntimeError("Refusing to run without OpenGL")
        self.pl.add(lvsnk := Gst.ElementFactory.make("glsinkbin", None))
        lvsnk.set_property("sink", gtksink)
        lvsnk.set_property("sync", True)
        self.pl.add(lvque := Gst.ElementFactory.make("queue", None))
        lvque.set_property("max-size-time", 0)
        lvque.set_property("max-size-bytes", 0)
        lvque.set_property("max-size-buffers", 0)
        lvque.link(lvsnk)

        # Video application source
        self.pl.add(tee := Gst.ElementFactory.make("tee", None))
        tee.link(lvque)
        #tee.link(lvsnk)
        self.pl.add(appsrc := Gst.ElementFactory.make("appsrc", None))
        appsrc.set_property("format", Gst.Format.TIME)
        appsrc.set_property("stream-type", 0)
        appsrc.set_property("is-live", True)
        self.drw = Drw(appsrc, CRT_W, CRT_H)
        appsrc.link_filtered(tee, Gst.Caps.from_string(CAPS))

        self.pl.add(fakesnk := Gst.ElementFactory.make("fakesink", None))
        fakesnk.set_property("sync", True)
        # terminal element
        self.pl.add(alvl := Gst.ElementFactory.make("level", None))
        alvl.link(fakesnk)
        self.pl.add(acnv := Gst.ElementFactory.make("audioconvert", None))
        acnv.link_filtered(
            alvl, Gst.Caps.from_string("audio/x-raw,channels=2")
        )
        self.pl.add(asrc := Gst.ElementFactory.make("autoaudiosrc", None))
        asrc.link(acnv)
        bus.add_signal_watch()
        bus.connect("message::element", self.on_level)

        if False:
            # https://github.com/matthew1000/gstreamer-cheat-sheet/blob/master/rtmp.md
            # Server: ffplay -listen 1 rtmp://0.0.0.0:9999/stream
            # https://stackoverflow.com/questions/67512264/how-to-use-gstreamer-to-mux-live-audio-and-video-to-mpegts
            self.pl.add(rtmp := Gst.ElementFactory.make("rtmpsink", None))
            rtmp.set_property(
                "location", "rtmp://localhost:9999/stream live=1"
            )
            self.pl.add(flvmux := Gst.ElementFactory.make("flvmux", None))
            flvmux.set_property("streamable", True)
            flvmux.link(rtmp)

            # self.pl.add(
            #    voaacenc := Gst.ElementFactory.make("voaacenc", None)
            # )
            # voaacenc.set_property("bitrate", 128000)
            # voaacenc.link(flvmux)
            # alvl.link(voaacenc)

            # self.pl.add(
            #    x264enc := Gst.ElementFactory.make("x264enc", None)
            # )
            # x264enc.set_property("cabac", 1)
            # x264enc.set_property("bframes", 2)
            # x264enc.set_property("ref", 1)
            # x264enc.link(flvmux)
            ##self.pl.add(
            ##    vqueue := Gst.ElementFactory.make("queue", None)
            ##)
            ##vqueue.link(x264enc)
            # self.pl.add(
            #    vconv := Gst.ElementFactory.make("videoconvert", None)
            # )
            # vconv.link(vqueue)

            # appsrc.link_filtered(vconv, Gst.Caps.from_string(CAPS))
            # self.pl.add(
            #    tvsrc := Gst.ElementFactory.make("videotestsrc", None)
            # )
            # tvsrc.set_property("is-live", 1)
            # tvsrc.link_filtered(vconv, Gst.Caps.from_string(CAPS))
            # tvsrc.link(vconv)

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

    def set_state(self, state: Optional[bool]):
        if state is None:
            self.pl.set_state(Gst.State.NULL)
        elif state:
            self.pl.set_state(Gst.State.PLAYING)
        else:
            self.pl.set_state(Gst.State.PAUSED)

    def report_ble(self, connected: bool, state: str) -> None:
        self.drw.report_ble(connected, state)

    def report_ecg(self, ev) -> None:
        self.drw.report_ecg(ev)

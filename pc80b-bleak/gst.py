# https://github.com/matthew1000/gstreamer-cheat-sheet/blob/master/rtmp.md
# Server: ffplay -listen 1 rtmp://0.0.0.0:9999/stream
# https://stackoverflow.com/questions/67512264/how-to-use-gstreamer-to-mux-live-audio-and-video-to-mpegts
# https://stackoverflow.com/questions/27905606/gstreamer-how-recover-from-rtmpsink-error

import gi
import cairo
from typing import Any, Optional

from .sgn import Signal
from .drw import Drw

gi.require_version("GLib", "2.0")
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

CRT_W = 720
CRT_H = 480

CAPS = (
    f"video/x-raw,format=RGBA,bpp=32,depth=32,width={CRT_W},height={CRT_H}"
    ",red_mask=-16777216,green_mask=16711680,blue_mask=65280"
    ",alpha_mask=255,endianness=4321,framerate=30/1"
)

Gst.init()


class Pipe:
    def __init__(self, signal: Signal) -> None:
        self.signal = signal
        self.on_level_callback = None
        self.on_error_callback = None
        self.pl = Gst.Pipeline.new()
        bus = self.pl.get_bus()
        bus.connect("message::eos", self.on_eos)
        bus.connect("message::error", self.on_error)

        # RMTP audio/video sink
        self.fakevsnk = Gst.ElementFactory.make("fakesink", None)
        self.pl.add(self.fakevsnk)
        self.fakevsnk.set_property("sync", True)
        # terminal element
        self.rtmp = Gst.ElementFactory.make("rtmpsink", None)
        # terminal element

        self.rtee = Gst.ElementFactory.make("tee", None)
        self.pl.add(self.rtee)
        self.rtee.link(self.fakevsnk)
        self.pl.add(flvm := Gst.ElementFactory.make("flvmux", None))
        flvm.set_property("streamable", True)
        flvm.link(self.rtee)
        self.pl.add(x264 := Gst.ElementFactory.make("x264enc", None))
        x264.set_property("cabac", 1)
        x264.set_property("bframes", 2)
        x264.set_property("ref", 1)
        x264.set_property("key-int-max", 100)
        x264.set_property("tune", "zerolatency")
        x264.link(flvm)
        self.pl.add(vconv := Gst.ElementFactory.make("videoconvert", None))
        vconv.link(x264)
        self.pl.add(rvque := Gst.ElementFactory.make("queue", None))
        rvque.set_property("max-size-time", 0)
        rvque.set_property("max-size-bytes", 0)
        rvque.set_property("max-size-buffers", 0)
        rvque.link(vconv)

        self.pl.add(voaacenc := Gst.ElementFactory.make("voaacenc", None))
        voaacenc.set_property("bitrate", 128000)
        voaacenc.link(flvm)
        self.pl.add(laque := Gst.ElementFactory.make("queue", None))
        laque.link(voaacenc)

        # Local video sink
        gtksink = Gst.ElementFactory.make("gtk4paintablesink", None)
        self.paintable = gtksink.get_property("paintable")
        if not self.paintable.props.gl_context:
            raise RuntimeError("Refusing to run without OpenGL")
        self.pl.add(lvsnk := Gst.ElementFactory.make("glsinkbin", None))
        lvsnk.set_property("sink", gtksink)
        lvsnk.set_property("sync", True)
        self.pl.add(lvque := Gst.ElementFactory.make("queue", None))
        # lvque.set_property("max-size-time", 0)
        # lvque.set_property("max-size-bytes", 0)
        # lvque.set_property("max-size-buffers", 0)
        lvque.link(lvsnk)

        # Video application source
        self.pl.add(tee := Gst.ElementFactory.make("tee", None))
        tee.link(lvque)
        tee.link(rvque)
        self.pl.add(appsrc := Gst.ElementFactory.make("appsrc", None))
        appsrc.set_property("format", Gst.Format.TIME)
        appsrc.set_property("stream-type", 0)
        appsrc.set_property("is-live", True)
        # appsrc.set_property("emit-signals", True)
        appsrc.set_property("leaky-type", 2)  # GstApp.AppStreamType.DOWNSTREAM
        self.drw = Drw(self.signal, appsrc, CRT_W, CRT_H)
        appsrc.link_filtered(tee, Gst.Caps.from_string(CAPS))

        self.pl.add(alvl := Gst.ElementFactory.make("level", None))
        # alvl.link(fakesnk)
        alvl.link(laque)
        self.pl.add(acnv := Gst.ElementFactory.make("audioconvert", None))
        acnv.link_filtered(
            alvl, Gst.Caps.from_string("audio/x-raw,channels=2")
        )
        self.pl.add(asrc := Gst.ElementFactory.make("autoaudiosrc", None))
        asrc.link(acnv)
        bus.add_signal_watch()
        bus.connect("message::element", self.on_level)

    def start_broadcast(self, url: str, key: str):
        print("start broadcast", url, key)
        if key and not url.endswith("/"):
            durl = url + "/" + key
        else:
            durl = url
        self.rtmp.set_property("location", f"{durl} live=1")
        self.set_state(False)
        self.pl.add(self.rtmp)
        self.rtee.link(self.rtmp)
        self.set_state(True)

    def stop_broadcast(self, forced: bool = False):
        print("stop broadcast")
        if self.rtmp.get_state(0).state is Gst.State.PLAYING:
            print("was playing, unlink and reset rtmp sink, forced", forced)
            self.set_state(None if forced else False)
            self.rtee.unlink(self.rtmp)
            self.pl.remove(self.rtmp)
            self.rtmp.set_state(Gst.State.NULL)
            self.set_state(True)

    def on_eos(self, bus, msg):
        print("End of stream")
        self.stop_broadcast(forced=True)
        if self.on_error_callback is not None:
            self.on_error_callback("Remote stopped receiving (RTMP EOS)")

    def on_error(self, bus, msg):
        error, debug = msg.parse_error()
        print("ERROR", error, "DEBUG", debug)
        if msg.src is self.rtmp:
            print("RTMP error", error)
            self.stop_broadcast(forced=True)
        if self.on_error_callback is not None:
            self.on_error_callback(error.message)

    def register_on_level_callback(self, callback) -> None:
        self.on_level_callback = callback

    def register_on_error_callback(self, callback) -> None:
        self.on_error_callback = callback

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

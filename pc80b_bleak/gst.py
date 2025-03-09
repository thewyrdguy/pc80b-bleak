# https://github.com/matthew1000/gstreamer-cheat-sheet/blob/master/rtmp.md
# Server: ffplay -listen 1 rtmp://0.0.0.0:9999/stream
# https://stackoverflow.com/questions/67512264/how-to-use-gstreamer-to-mux-live-audio-and-video-to-mpegts
# https://stackoverflow.com/questions/27905606/gstreamer-how-recover-from-rtmpsink-error

from __future__ import annotations
import gi  # type: ignore [import-untyped]
import cairo
from contextlib import ExitStack
from time import time_ns
from typing import (
    Any,
    Callable,
    ContextManager,
    Literal,
    Optional,
    Tuple,
    TYPE_CHECKING,
)

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # type: ignore [import-untyped]

if TYPE_CHECKING:
    from .sgn import Signal

POOLSIZE = 128

ADELAY = 0  # 1_000_000_000

CAPS = (
    "video/x-raw,format=RGBA,bpp=32,depth=32,width={crt_w},height={crt_h}"
    ",red_mask=-16777216,green_mask=16711680,blue_mask=65280"
    ",alpha_mask=255,endianness=4321,framerate=30/1"
)

Gst.init()


class PoolBuf(ContextManager[Tuple[memoryview, Callable[[int, int], None]]]):
    """Context manager to acquire a buffer from the pool and submit on exit"""

    def __init__(
        self,
        pool: Gst.BufferPool,
        lst: Gst.BufferList,
        sclk: int,
    ) -> None:
        self.pool = pool
        self.lst = lst
        self.sclk = sclk

    def __enter__(self) -> Tuple[memoryview, Callable[[int, int], None]]:
        res, self.buffer = self.pool.acquire_buffer()
        if res != Gst.FlowReturn.OK:
            raise RuntimeError(f"buffer acquisition {res}")
        with ExitStack() as mmctx:
            mm = mmctx.enter_context(
                self.buffer.map(Gst.MapFlags.READ | Gst.MapFlags.WRITE)
            )
            self.mmstack = mmctx.pop_all()
        return mm.data, self.setstamp

    def setstamp(self, dur: int, ts: int) -> None:
        self.dur = dur
        self.ts = ts

    def __exit__(self, ec: Any, *_: Any) -> Literal[False]:
        with self.mmstack:
            pass
        if ec is None:
            # print("timestamping buffer", self.dur, self.ts - sclk)
            self.buffer.duration = self.dur
            self.buffer.pts = self.sclk + self.ts
            self.lst.insert(-1, self.buffer)  # "-1" will append to the end
        else:
            self.pool.release_buffer(self.buffer)
        return False


class BufList(ContextManager[Callable[[], PoolBuf]]):
    def __init__(
        self,
        pool: Gst.BufferPool,
        src: Gst.Element,
    ) -> None:
        self.pool = pool
        self.src = src
        self.sclk = src.get_current_clock_time()

    def __enter__(self) -> Callable[[], PoolBuf]:
        self.lst = Gst.BufferList()
        return self.bufmaker

    def __exit__(self, ex: Any, *_: Any) -> Literal[False]:
        if ex is None:
            self.src.emit("push-buffer-list", self.lst)
        return False

    def bufmaker(self) -> PoolBuf:
        return PoolBuf(self.pool, self.lst, self.sclk)


class Pipe:
    def __init__(
        self,
        crt_w: int,
        crt_h: int,
        *,
        on_level: Callable[..., None],
        on_error: Callable[..., None],
    ) -> None:
        self.on_level_gui = on_level
        self.on_error_gui = on_error
        # The following must be set by register_data_callbacks()
        self.on_need_data_sgn = lambda: None
        self.on_enough_data_sgn = lambda: None
        self.signal: Optional[Signal] = None
        self.adelay = ADELAY

        self.pool = Gst.BufferPool()
        bufsize = crt_w * crt_h * 4  # for FORMAT_ARGB32
        bpconf = self.pool.get_config()
        self.pool.config_set_params(bpconf, None, bufsize, POOLSIZE, POOLSIZE)
        self.pool.set_config(bpconf)
        if not self.pool.set_active(True):
            raise RuntimeError("Could not activate buffer pool")

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
        voaacenc.get_static_pad("sink").add_probe(
            Gst.PadProbeType.BUFFER, self.pad_probe, None
        )
        voaacenc.link(flvm)
        self.laque = Gst.ElementFactory.make("queue", None)
        self.pl.add(self.laque)
        # self.laque.set_property("min-threshold-time", ADELAY)
        self.laque.link(voaacenc)

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
        self.src = appsrc
        appsrc.set_property("format", Gst.Format.TIME)
        appsrc.set_property("stream-type", 0)
        appsrc.set_property("is-live", True)
        appsrc.set_property("max-bytes", 11_059_200)  # Eight buffers
        appsrc.set_property("min-percent", 5)
        # appsrc.set_property("emit-signals", True)
        # 2 below is for GstApp.AppStreamType.DOWNSTREAM
        # appsrc.set_property("leaky-type", 2)
        appsrc.connect("need-data", self.on_need_data)
        appsrc.connect("enough-data", self.on_enough_data)
        appsrc.link_filtered(
            tee,
            Gst.Caps.from_string(CAPS.format(crt_w=crt_w, crt_h=crt_h)),
        )

        self.pl.add(alvl := Gst.ElementFactory.make("level", None))
        # alvl.link(fakesnk)
        alvl.link(self.laque)
        self.pl.add(acnv := Gst.ElementFactory.make("audioconvert", None))
        acnv.link_filtered(
            alvl, Gst.Caps.from_string("audio/x-raw,channels=2")
        )
        self.pl.add(asrc := Gst.ElementFactory.make("autoaudiosrc", None))
        asrc.link(acnv)
        bus.add_signal_watch()
        bus.connect("message::element", self.on_level)

    def pad_probe(
        self,
        probe: Gst.PadProbeType,
        info: Gst.PadProbeInfo,
        udata: Literal[None],
    ) -> Gst.PadProbeReturn:
        info.get_buffer().pts += self.adelay
        # print("buffer", buffer, buffer.pts, buffer.dts, buffer.duration)
        return Gst.PadProbeReturn.OK

    # def set_adelay(self, adelay: int):
    #     self.laque.set_property("min-threshold-time", adelay * 1_000_000)

    def start_broadcast(self, url: str, key: str) -> None:
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

    def stop_broadcast(self, forced: bool = False) -> None:
        print("stop broadcast")
        if self.rtmp.get_state(0).state is Gst.State.PLAYING:
            print("was playing, unlink and reset rtmp sink, forced", forced)
            self.set_state(None if forced else False)
            self.rtee.unlink(self.rtmp)
            self.pl.remove(self.rtmp)
            self.rtmp.set_state(Gst.State.NULL)
            self.set_state(True)

    def get_adelay(self) -> int:
        return self.adelay // 1_000_000

    def set_adelay(self, delay_ms: int) -> None:
        print("set_adelay", delay_ms, "ms")
        self.adelay = delay_ms * 1_000_000

    def on_eos(self, bus: Gst.Bus, msg: Gst.Message) -> None:
        print("End of stream")
        self.stop_broadcast(forced=True)

    def on_error(self, bus: Gst.Bus, msg: Gst.Message) -> None:
        error, debug = msg.parse_error()
        if msg.src is self.rtmp:
            print("RTMP ERROR", error, "DEBUG", debug)
            self.stop_broadcast(forced=True)
        else:
            print("Non RTMP ERROR", error, "DEBUG", debug)
        self.on_error_gui(error.message)

    def on_level(self, bus: Gst.Bus, msg: Gst.Message) -> None:
        s = msg.get_structure()
        kwargs = {k: s.get_value(k) for k in ("rms", "peak", "decay")}
        self.on_level_gui(**kwargs)

    def set_state(self, state: Optional[bool]) -> None:
        if state is None:
            self.pl.set_state(Gst.State.NULL)
        elif state:
            self.pl.set_state(Gst.State.PLAYING)
        else:
            self.pl.set_state(Gst.State.PAUSED)

    def on_need_data(self, source: Gst.Element, amount: int) -> None:
        if self.signal is None:
            print("Need data, time", time_ns(), "amount", amount)
        else:
            self.signal.on_need_data(source, amount)

    def on_enough_data(self, source: Gst.Element) -> None:
        if self.signal is None:
            print("Uh-oh, got 'enough-data'")
        else:
            self.signal.on_enough_data(source)

    def register_signal(self, signal: Signal) -> None:
        self.signal = signal

    def listmaker(self) -> BufList:
        return BufList(self.pool, self.src)

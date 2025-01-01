from cairo import (
    Context,
    ImageSurface,
    FORMAT_ARGB32,
    FONT_SLANT_NORMAL,
    FONT_WEIGHT_BOLD,
)
from time import time_ns
from typing import Iterable, Tuple

import gi

gi.require_version("GLib", "2.0")
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

from .datatypes import EventPc80bContData, EventPc80bFastData, TestData

FRAMES_PER_SEC = 30
VALS_PER_SEC = 150
SECS_ON_SCREEN = 3

POOLSIZE = 12

VALS_ON_SCREEN = VALS_PER_SEC * SECS_ON_SCREEN
SAMPS_PER_FRAME = VALS_PER_SEC // FRAMES_PER_SEC
SAMPDUR = 1_000_000_000 // VALS_PER_SEC
FRAMEDUR = 1_000_000_000 // FRAMES_PER_SEC


class Drw:
    def __init__(self, src: Gst.Element, crt_w: int, crt_h: int) -> None:
        self.src = src
        self.crt_w = crt_w
        self.crt_h = crt_h
        src.connect("need-data", self.on_need_data)
        src.connect("enough-data", self.on_enough_data)
        self.image = ImageSurface(FORMAT_ARGB32, self.crt_w, self.crt_h)
        bufsize = len(self.image.get_data())
        # print("bufsize", bufsize)
        self.pool = Gst.BufferPool.new()
        bpconf = self.pool.get_config()
        self.pool.config_set_params(bpconf, None, bufsize, POOLSIZE, POOLSIZE)
        self.pool.set_config(bpconf)
        if not self.pool.set_active(True):
            raise RuntimeError("Could not activate buffer pool")
        self.c = Context(self.image)
        self.samppos = 0
        self.prevval = 0.0

    def clearscreen(self, text: str) -> None:
        self.c.set_source_rgb(0.0, 0.0, 0.0)
        self.c.rectangle(0, 0, self.crt_w, self.crt_h)
        self.c.fill()
        self.c.select_font_face(
            "sans-serif", FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD
        )
        self.c.set_font_size(36)
        (x, y, w, h, dx, dy) = self.c.text_extents(text)
        self.c.move_to((self.crt_w - w) / 2.0, (self.crt_h - h) / 2.0)
        self.c.set_source_rgb(1.0, 1.0, 1.0)
        self.c.show_text(text)

        self.bytes = self.image.get_data()
        gbytes = GLib.Bytes.new(self.bytes)
        buffer = Gst.Buffer.new_wrapped_bytes(gbytes).copy_deep()
        buffer.duration = FRAMEDUR
        print("push clearscreen")
        self.src.emit("push-buffer", buffer)
        self.samppos = 0
        self.prevval = 0.0
        self.c.move_to(0, self.crt_h / 2)

    def draw(self, data: Iterable[Tuple[int, float]]):
        """
        Produce video buffers from data that can be 5 to 25 samples.
        This is called when
        1. new data arrives from the BLE receiver, or
        2. gstremer pipeline askes for more buffers (we then draw flatline)
        """
        start = time_ns()
        ymid = self.crt_h / 2
        yscale = ymid / 4.0  # div by max y value - +/- 4 mV
        blist = Gst.BufferList.new()
        self.c.set_line_width(4)
        try:
            while True:  # Will be broken by StopIteration
                self.c.set_source_rgb(0.0, 0.0, 0.0)
                self.c.rectangle(
                    self.samppos * self.crt_w // VALS_ON_SCREEN,
                    0,
                    SAMPS_PER_FRAME * self.crt_w // VALS_ON_SCREEN,
                    self.crt_h,
                )
                self.c.fill()
                self.c.set_source_rgb(0.0, 1.0, 0.0)
                frstart = 0
                self.c.move_to(
                    self.samppos * self.crt_w // VALS_ON_SCREEN,
                    ymid - self.prevval * yscale,
                )
                for tstamp, val in (
                    next(data) for _ in range(SAMPS_PER_FRAME)
                ):
                    if frstart == 0:
                        frstart = tstamp  # timestamp of the first sample
                    self.samppos += 1
                    self.c.line_to(
                        self.samppos * self.crt_w // VALS_ON_SCREEN,
                        ymid - val * yscale,
                    )

                    if self.samppos >= VALS_ON_SCREEN:
                        self.samppos = 0
                        self.c.move_to(0, ymid - val * yscale)

                self.prevval = val
                self.c.stroke()
                self.c.set_source_rgb(0.2, 0.2, 0.2)
                xpos = self.samppos * self.crt_w // VALS_ON_SCREEN + 2
                self.c.move_to(xpos, 0)
                self.c.line_to(xpos, self.crt_h)
                self.c.stroke()

                # print("image ready", (time_ns() - start) // 1_000)
                imgbytes = self.image.get_data()
                # print("got image data", (time_ns() - start) // 1_000)
                # buffer = Gst.Buffer.new_memdup(self.bytes)
                res, buffer = self.pool.acquire_buffer()
                if res != Gst.FlowReturn.OK:
                    raise RuntimeError(f"buffer acquisition {res}")
                # print("buffer acquired", (time_ns() - start) // 1_000)
                with buffer.map(Gst.MapFlags.READ | Gst.MapFlags.WRITE) as m:
                    # print("data mapped", (time_ns() - start) // 1_000)
                    m.data[:] = imgbytes
                # print("data copied", (time_ns() - start) // 1_000)
                buffer.duration = FRAMEDUR
                buffer.dts = frstart + FRAMEDUR  # Delay by one frame (?)
                # and add the buffer to the list
                blist.insert(-1, buffer)  # "-1" will append to the end
        except StopIteration:
            pass
        except RuntimeError as e:  # After PEP 479 it does not bubble up
            if not isinstance(e.__cause__, StopIteration):
                raise
        # print(
        #     "push blist",
        #     (time_ns() - start) // 1_000,
        #     "length",
        #     blist.length(),
        # )
        self.src.emit("push-buffer-list", blist)
        # print("blist pushed", (time_ns() - start) // 1_000)

    def on_need_data(self, source, amount):
        """
        If asked for buffer by gstreamer, it probably means that data
        thread is not sending any data. So produce one frame worth of
        zeroes and send one buffer.
        """
        # print("Need data, time", time_ns())
        start = self.src.get_current_clock_time()
        self.draw(((start + n * SAMPDUR, 0.0) for n in range(SAMPS_PER_FRAME)))

    def on_enough_data(self, source):
        print("Uh-oh, got 'enough-data'")

    def report_ble(self, connected: bool, state: str) -> None:
        self.clearscreen("" if connected else state)

    def report_ecg(self, ev) -> None:
        """Put data in the fifo and start producing buffers"""
        start = self.src.get_current_clock_time()
        # print("ECG, time", start, "event", ev)
        if isinstance(ev, (EventPc80bContData, EventPc80bFastData, TestData)):
            self.draw(
                ((start + n * SAMPDUR, v) for n, v in enumerate(ev.ecgFloats))
            )

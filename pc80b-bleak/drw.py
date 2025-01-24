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

# from .datatypes import EventPc80bContData, EventPc80bFastData, TestData
from .sgn import Signal

FRAMES_PER_SEC = 30
VALS_PER_SEC = 150
SECS_ON_SCREEN = 3

POOLSIZE = 128

VALS_ON_SCREEN = VALS_PER_SEC * SECS_ON_SCREEN
VALS_PER_FRAME = VALS_PER_SEC // FRAMES_PER_SEC
SAMPDUR = 1_000_000_000 // VALS_PER_SEC
FRAMEDUR = 1_000_000_000 // FRAMES_PER_SEC


class Drw:
    def __init__(
        self, signal: Signal, src: Gst.Element, crt_w: int, crt_h: int
    ) -> None:
        self.signal = signal
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
        buffer.pts = self.src.get_current_clock_time()
        print("push clearscreen")
        self.src.emit("push-buffer", buffer)
        self.samppos = 0
        self.prevval = 0.0
        self.c.move_to(0, self.crt_h / 2)

    def draw(self):
        """
        Produce video buffers from data that can be 5 to 25 samples.
        This is called when
        1. new data arrives from the BLE receiver, or
        2. gstremer pipeline askes for more buffers (we then draw flatline)
        """
        start = time_ns()
        offset = self.src.get_current_clock_time() - start
        ymid = self.crt_h / 2
        yscale = ymid / 4.0  # div by max y value - +/- 4 mV
        blist = Gst.BufferList.new()
        self.c.set_line_width(4)
        while framedata := self.signal.pull(VALS_PER_FRAME):
            self.c.set_source_rgb(0.0, 0.0, 0.0)
            self.c.rectangle(
                self.samppos * self.crt_w // VALS_ON_SCREEN,
                0,
                VALS_PER_FRAME * self.crt_w // VALS_ON_SCREEN,
                self.crt_h,
            )
            self.c.fill()
            self.c.set_source_rgb(0.0, 1.0, 0.0)
            lasttstamp = 0
            self.c.move_to(
                self.samppos * self.crt_w // VALS_ON_SCREEN,
                ymid - self.prevval * yscale,
            )
            for tstamp, val in framedata:
                lasttstamp = tstamp  # will use value of the last sample
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
            buffer.pts = lasttstamp + offset + FRAMEDUR * 30  # Future
            # print(
            #     "BUF",
            #     self.src.get_current_clock_time(),
            #     buffer.pts,
            #     buffer.duration,
            # )
            # and add the buffer to the list
            blist.insert(-1, buffer)  # "-1" will append to the end
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
        print("Need data, time", time_ns(), "amount", amount)
        connected, state = self.signal.get_status()
        if connected:
            if self.signal.is_empty():
                start = time_ns() - 166666666  # 1_000_000_000 * 25 // 150
                values = [(start + i * 6666666, 0.0) for i in range(25)]
                self.signal.push(values)
            self.draw()
        else:
            self.clearscreen(state)

    def on_enough_data(self, source):
        print("Uh-oh, got 'enough-data'")

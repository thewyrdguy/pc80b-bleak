from cairo import (
    Context,
    ImageSurface,
    FORMAT_ARGB32,
    FONT_SLANT_NORMAL,
    FONT_WEIGHT_BOLD,
)
from itertools import islice
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
        self.c = Context(self.image)
        self.clearscreen("ECG recodrer not connected")

    def clearscreen(self, text: str) -> None:
        self.c.set_source_rgb(0.0, 0.0, 0.0)
        self.c.rectangle(0, 0, self.crt_w, self.crt_h)
        self.c.fill()
        self.c.select_font_face(
            "sans-serif", FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD
        )
        self.c.set_font_size(48)
        (x, y, w, h, dx, dy) = self.c.text_extents(text)
        self.c.move_to((self.crt_w - w) / 2.0, (self.crt_h - h) / 2.0)
        self.c.set_source_rgb(1.0, 1.0, 1.0)
        self.c.show_text(text)

        buffer = Gst.Buffer.new_wrapped_bytes(
            GLib.Bytes.new(self.image.get_data())
        )
        buffer.duration = FRAMEDUR
        print("push clearscreen")
        self.src.emit("push-buffer", buffer)
        self.samppos = 0
        self.prevval = 0.0
        self.c.move_to(0, self.crt_h / 2)

    def draw(self, data: Iterable[Tuple[int, float]]):
        """
        Consume data from the fifo and produce video buffers.
        Return when all data is consumed.
        This is called when
        1. new data arrives from the BLE receiver, or
        2. gstremer pipeline askes for more buffers (we then draw flatline)
        """
        # TODO move timestamping to the report_ecg() function
        start = time_ns()
        ymid = self.crt_h / 2
        yscale = ymid / 4.0  # div by max y value - +/- 4 mV
        self.c.set_source_rgb(0.0, 1.0, 0.0)
        self.c.set_line_width(3)
        blist = Gst.BufferList.new()
        try:
            while True:  # Will be broken by StopIteration
                for tstamp, val in (
                    next(data) for _ in range(SAMPS_PER_FRAME)
                ):
                    self.samppos += 1
                    self.c.line_to(
                        self.samppos * self.crt_w // VALS_ON_SCREEN,
                        ymid - val * yscale,
                    )

                    if self.samppos >= VALS_ON_SCREEN:
                        self.samppos = 0
                        self.c.move_to(self.samppos, ymid - val * yscale)

                self.prevval = val
                self.c.stroke()

                # Wrap the image in a Buffer and make a fresh copy
                buffer = Gst.Buffer.new_wrapped_bytes(
                    GLib.Bytes.new(self.image.get_data())
                ).copy_deep()
                buffer.duration = FRAMEDUR
                buffer.add_reference_timestamp_meta(
                    Gst.Caps.from_string("timestamp/x-unix"),
                    tstamp,
                    FRAMEDUR,
                )
                # and add the buffer to the list
                blist.insert(-1, buffer)  # "-1" will append to the end
        except StopIteration:
            pass
        except RuntimeError as e:  # After PEP 479 it does not bubble up
            if not isinstance(e.__cause__, StopIteration):
                raise
        self.src.emit("push-buffer-list", blist)

    def on_need_data(self, source, amount):
        """
        If asked for buffer by gstreamer, it probably means that data
        thread is not sending any data. So produce one frame worth of
        zeroes and send one buffer.
        """
        # print("Need data, time", time_ns())
        start = time_ns()
        self.draw(((start + n * SAMPDUR, 0.0) for n in range(SAMPS_PER_FRAME)))

    def on_enough_data(self, source):
        print("Uh-oh, got 'enough-data'")

    def report_ecg(self, ev) -> None:
        """Put data in the fifo and start producing buffers"""
        start = time_ns()
        # print("ECG, time", start, "event", ev)
        if isinstance(ev, (EventPc80bContData, EventPc80bFastData, TestData)):
            self.draw(
                ((start + n * SAMPDUR, v) for n, v in enumerate(ev.ecgFloats))
            )

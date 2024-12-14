from collections import deque
from cairo import (
    Context,
    ImageSurface,
    FORMAT_ARGB32,
    FONT_SLANT_NORMAL,
    FONT_WEIGHT_BOLD,
)
from itertools import islice
from math import sin
from time import time

import gi

gi.require_version("GLib", "2.0")
gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst

from .datatypes import EventPc80bContData, EventPc80bFastData

WWIDTH = 150 * 3
SAMPF = 5
DURATION = 33333333


class Drw:
    def __init__(self, src, crt_w, crt_h) -> None:
        self.src = src
        self.crt_w = crt_w
        self.crt_h = crt_h
        self.data = deque([], WWIDTH)
        self.samppos = 0
        self.prevval = 0.0
        src.connect("need-data", self.on_need_data)
        self.image = ImageSurface(FORMAT_ARGB32, self.crt_w, self.crt_h)
        self.c = Context(self.image)
        self.clearscreen()

    def clearscreen(self):
        self.c.set_source_rgb(0.0, 0.0, 0.0)
        self.c.rectangle(0, 0, self.crt_w, self.crt_h)
        self.c.fill()
        self.c.select_font_face(
            "sans-serif", FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD
        )
        self.c.set_font_size(48)
        text = "No Signal"
        (x, y, w, h, dx, dy) = self.c.text_extents(text)
        self.c.move_to((self.crt_w - w) / 2.0, (self.crt_h - h) / 2.0)
        self.c.set_source_rgb(1.0, 1.0, 1.0)
        self.c.show_text(text)

        buffer = Gst.Buffer.new_wrapped_bytes(
            GLib.Bytes.new(self.image.get_data())
        )
        buffer.duration = DURATION
        print("push clearscreen")
        self.src.emit("push-buffer", buffer)

    def draw(self):
        start = round(time() * 1000000000)
        seqno = 0
        xstep = self.crt_w / WWIDTH
        ymid = self.crt_h / 2
        yscale = ymid / 1.5  # div by max y value
        self.c.set_source_rgb(0.0, 1.0, 0.0)
        self.c.set_line_width(3)
        while True:
            try:
                self.c.move_to(
                    self.samppos * xstep, ymid - self.prevval * yscale
                )
                for val in (self.data.popleft() for _ in range(SAMPF)):
                    self.c.line_to(
                        self.samppos * xstep + xstep, ymid - val * yscale
                    )
                    self.c.stroke()
                    self.prevval = val
                    self.samppos += 1

                    if self.samppos > WWIDTH:
                        self.samppos = -WWIDTH

                buffer = Gst.Buffer.new_wrapped_bytes(
                    GLib.Bytes.new(self.image.get_data())
                )
                buffer.duration = DURATION
                # buffer = Gst.Buffer.copy_deep(self.buffer)
                buffer.add_reference_timestamp_meta(
                    Gst.Caps.from_string("timestamp/x-unix"),
                    start + DURATION * seqno,
                    DURATION,
                )
                # print("pushing buffer seq", seqno, "timestamp", start + DURATION * seqno)
                seqno += 1
                self.src.emit("push-buffer", buffer)
            except IndexError:  # Ran out of data
                print("Ran out of data, seqno:", seqno)
                break

    def on_need_data(self, source, amount):
        print("Need data, fifo", len(self.data), "time", time())
        if not self.data:  # deque empty
            self.data.extend(0.0 for _ in range(SAMPF))
        #    self.data.extend(sin(i / 20) for i in range(WWIDTH))
        self.draw()

    def report_ecg(self, ev) -> None:
        if isinstance(ev, (EventPc80bContData, EventPc80bFastData)):
            self.data.extend(ev.ecgFloats)
            self.draw()
        print("ECG fifo", len(self.data), "event", ev)

from cairo import (
    Context,
    ImageSurface,
    FORMAT_ARGB32,
    FONT_SLANT_NORMAL,
    FONT_WEIGHT_BOLD,
)
from collections import deque
from itertools import repeat
from time import time_ns
from typing import Callable, ContextManager, Iterable, Tuple

# from .datatypes import EventPc80bContData, EventPc80bFastData, TestData
from .sgn import Signal

FRAMES_PER_SEC = 30
VALS_PER_SEC = 150
SECS_ON_SCREEN = 3

VALS_ON_SCREEN = VALS_PER_SEC * SECS_ON_SCREEN
VALS_PER_FRAME = VALS_PER_SEC // FRAMES_PER_SEC
SAMPDUR = 1_000_000_000 // VALS_PER_SEC
FRAMEDUR = 1_000_000_000 // FRAMES_PER_SEC


class Drw:
    def __init__(
        self,
        signal: Signal,
        bufgen: ContextManager[Tuple[bytes, Callable[[int, int], None]]],
        crt_w: int,
        crt_h: int,
    ) -> None:
        self.signal = signal
        self.bufgen = bufgen
        self.crt_w = crt_w
        self.crt_h = crt_h
        self.cleardata()

    def cleardata(self) -> None:
        self.samppos = 0
        now = time_ns()
        self.data = deque(
            repeat((now, 0.0), VALS_ON_SCREEN), maxlen=VALS_ON_SCREEN
        )

    def clearscreen(self, c: Context, text: str) -> None:
        c.set_source_rgb(0.0, 0.0, 0.0)
        c.rectangle(0, 0, self.crt_w, self.crt_h)
        c.fill()
        c.select_font_face("sans-serif", FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD)
        c.set_font_size(36)
        (x, y, w, h, dx, dy) = c.text_extents(text)
        c.move_to((self.crt_w - w) / 2.0, (self.crt_h - h) / 2.0)
        c.set_source_rgb(1.0, 1.0, 1.0)
        c.show_text(text)

    def drawcurve(self, c: Context):
        """
        Visualize data as a curve in the draw context
        """
        xscale = self.crt_w / VALS_ON_SCREEN
        ymid = self.crt_h / 2
        yscale = ymid / 4.0  # div by max y value - +/- 4 mV
        c.set_source_rgb(0.0, 0.0, 0.0)
        c.rectangle(0, 0, self.crt_w, self.crt_h)
        c.fill()
        c.set_source_rgb(0.0, 1.0, 0.0)
        c.set_line_width(4)
        for x, (tstamp, val) in enumerate(self.data):
            xpos = (self.samppos + x) % VALS_ON_SCREEN * xscale
            if xpos:
                c.line_to(xpos, ymid - val * yscale)
            else:  # Point zero - move to the left edge
                c.move_to(xpos, ymid - val * yscale)
        c.stroke()
        c.set_source_rgb(0.2, 0.2, 0.2)
        xpos = self.samppos * xscale
        c.move_to(xpos, 0)
        c.line_to(xpos, self.crt_h)
        c.stroke()

    def draw(self, timeoffset: int) -> None:
        now = time_ns()
        # print("draw:", timeoffset, "now", now, "diff", timeoffset + now)
        connected, state = self.signal.get_status()
        if connected:
            if self.signal.is_empty():
                start = time_ns() - SAMPDUR * VALS_PER_FRAME
                values = [
                    (start + i * SAMPDUR, 0.0) for i in range(VALS_PER_FRAME)
                ]
                self.signal.push(values)
            count = 0
            while framedata := self.signal.pull(VALS_PER_FRAME):
                laststamp = framedata[-1][0]
                self.data.extend(framedata)
                self.samppos += VALS_PER_FRAME
                if self.samppos >= VALS_ON_SCREEN:
                    self.samppos = 0
                with self.bufgen() as (mem, setts):
                    image = ImageSurface.create_for_data(
                        mem, FORMAT_ARGB32, self.crt_w, self.crt_h
                    )
                    c = Context(image)
                    try:
                        self.drawcurve(c)
                    finally:
                        del c
                        del image
                    setts(FRAMEDUR, timeoffset + laststamp + FRAMEDUR * 15)
                    # print(
                    #    "buffer",
                    #    FRAMEDUR,
                    #    "pts",
                    #    timeoffset + laststamp + 300000000,
                    # )
                count += 1
            # print("Used", count, "buffers")
        else:
            self.data = deque(
                repeat((0.0, 0.0), VALS_ON_SCREEN), maxlen=VALS_ON_SCREEN
            )
            with self.bufgen() as (mem, setts):
                image = ImageSurface.create_for_data(
                    mem, FORMAT_ARGB32, self.crt_w, self.crt_h
                )
                c = Context(image)
                try:
                    self.clearscreen(c, state)
                finally:
                    del c
                    del image
                setts(FRAMEDUR, timeoffset + now + FRAMEDUR * 15)
                # print("buffer", FRAMEDUR, "pts", timeoffset + now + FRAMEDUR)

"""Draw display picture"""

from cairo import (
    Context,
    ImageSurface,
    FORMAT_ARGB32,
    FONT_SLANT_NORMAL,
    FONT_WEIGHT_BOLD,
)
from datetime import datetime
from enum import Enum
from time import time_ns
from typing import (
    Callable,
    ContextManager,
    Iterable,
    NamedTuple,
    Tuple,
    TYPE_CHECKING,
)

from .datatypes import Channel, MMode, MStage


class FrameMeta(NamedTuple):
    bat: int = 0
    hr: int = 0
    leadoff: bool = True
    gain: int = 0
    vol: int = 0
    channel: Channel = Channel.detecting
    mmode: MMode = MMode.detecting
    mstage: MStage = MStage.detecting
    datatype: int = 0


class Drw:
    def __init__(
        self,
        crt_w: int,
        crt_h: int,
        vals_on_screen: int,
    ) -> None:
        self.crt_w = crt_w
        self.crt_h = crt_h
        self.vals_on_screen = vals_on_screen

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

    def drawcurve(
        self, c: Context, fmeta: FrameMeta, data: Iterable, samppos: int
    ):
        """
        Visualize data as a curve in the draw context
        """
        xscale = self.crt_w / self.vals_on_screen
        ymid = self.crt_h / 2
        yscale = ymid / 4.0  # div by max y value - +/- 4 mV
        c.set_source_rgb(0.0, 0.0, 0.0)
        c.rectangle(0, 0, self.crt_w, self.crt_h)
        c.fill()
        c.set_source_rgb(0.0, 1.0, 0.0)
        c.set_line_width(4)
        for x, val in enumerate(data):
            xpos = (samppos + x) % self.vals_on_screen * xscale
            if xpos:
                c.line_to(xpos, ymid - val * yscale)
            else:  # Point zero - move to the left edge
                c.move_to(xpos, ymid - val * yscale)
        c.stroke()
        c.set_source_rgb(0.2, 0.2, 0.2)
        xpos = samppos * xscale
        c.move_to(xpos, 0)
        c.line_to(xpos, self.crt_h)
        c.stroke()

"""Draw display picture"""

# pylint: disable=missing-function-docstring,no-name-in-module

from __future__ import annotations
from datetime import datetime, timezone
from typing import Iterable, NamedTuple
from cairo import (
    Context,
    ImageSurface,
    # FORMAT_ARGB32,
    FONT_SLANT_NORMAL,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_NORMAL,
)

from .datatypes import Channel, MMode, MStage


class FrameMeta(NamedTuple):
    """Aggregate data for drawing a frame"""

    dtime: datetime = datetime.now()
    battery: int = 0
    hr: int = 0
    leadoff: bool = True
    gain: int = 0
    vol: int = 0
    channel: Channel = Channel.detecting
    mmode: MMode = MMode.detecting
    mstage: MStage = MStage.detecting
    datatype: int = 0


def drawtext(
    c: Context[ImageSurface], x: int, y: int, text: str, fsize: int = 16
) -> None:
    c.select_font_face("sans-serif", FONT_SLANT_NORMAL, FONT_WEIGHT_NORMAL)
    c.set_font_size(fsize)
    c.move_to(x, y)
    c.set_source_rgb(1.0, 1.0, 1.0)
    c.show_text(text)


class Drw:  # pylint: disable=too-many-instance-attributes
    """Drawer class with geometry of the display and drawing methods"""

    def __init__(
        self,
        crt_w: int,
        crt_h: int,
        vals_on_screen: int,
        vals_per_sec: int,
    ) -> None:
        self.crt_w = crt_w
        self.crt_h = crt_h
        self.vals_on_screen = vals_on_screen
        self.xscale = self.crt_w / self.vals_on_screen
        self.ymid = self.crt_h // 2
        self.yscale = self.ymid / 4.0  # div by max y value - +/- 4 mV
        # Big square width .2 sec, small square .04 sec
        # Big square hight .5 mV, small square .1 mV
        self.xtick_step = vals_per_sec // 5  # big square - 200 msec
        self.xtick_max = self.crt_w // self.xtick_step
        self.ytick_step = self.ymid // 8  # big squate - .5 mV
        self.ytick_max = self.crt_h // self.ytick_step

    def clearscreen(self, c: Context[ImageSurface], text: str) -> None:
        c.set_source_rgb(0.0, 0.0, 0.0)
        c.rectangle(0, 0, self.crt_w, self.crt_h)
        c.fill()
        c.select_font_face("sans-serif", FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD)
        c.set_font_size(36)
        (_x, _y, w, h, _dx, _dy) = c.text_extents(text)
        c.move_to((self.crt_w - w) / 2.0, (self.crt_h - h) / 2.0)
        c.set_source_rgb(1.0, 1.0, 1.0)
        c.show_text(text)

    def drawcurve(
        self,
        c: Context[ImageSurface],
        fmeta: FrameMeta,
        data: Iterable[float],
        samppos: int,
    ) -> None:
        """
        Visualize data as a curve in the draw context
        """
        # Black background
        c.set_source_rgb(0.0, 0.0, 0.0)
        c.rectangle(0, 0, self.crt_w, self.crt_h)
        c.fill()
        # Grid
        c.set_source_rgb(0.4, 0.4, 0.4)
        c.set_line_width(2)
        for x in range(self.xtick_max):
            c.move_to(x * self.xtick_step, 0)
            c.line_to(x * self.xtick_step, self.crt_h)
        for y in range(self.ytick_max):
            c.move_to(0, y * self.ytick_step)
            c.line_to(self.crt_w, y * self.ytick_step)
        c.stroke()
        # Green signal trace
        c.set_source_rgb(0.0, 1.0, 0.0)
        c.set_line_width(4)
        for x, val in enumerate(data):
            xpos = (samppos + x) % self.vals_on_screen * self.xscale
            if xpos:
                c.line_to(xpos, self.ymid - val * self.yscale)
            else:  # Point zero - move to the left edge
                c.move_to(xpos, self.ymid - val * self.yscale)
        c.stroke()
        # Running edge
        c.set_source_rgb(0.2, 0.2, 0.2)
        xpos = samppos * self.xscale
        c.move_to(xpos, 0)
        c.line_to(xpos, self.crt_h)
        c.stroke()

        drawtext(
            c,
            20,
            self.crt_h - 20,
            fmeta.dtime.astimezone(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
        )
        drawtext(
            c,
            self.crt_w - 70,
            40,
            str(fmeta.hr) if fmeta.hr else "---",
            fsize=32,
        )

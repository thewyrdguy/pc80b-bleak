"""Draw display picture"""

# pylint: disable=missing-function-docstring,no-name-in-module

from __future__ import annotations
from datetime import datetime, timezone
from collections import deque
from typing import Iterable, NamedTuple
from cairo import (
    # ColorMode,
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
        self.yscale = self.ymid / 2.5  # div by max y value - +/- 2.5 mV
        # Big square width .2 sec, small square .04 sec
        # Big square hight .5 mV, small square .1 mV
        self.xtick_step = (  # big square - 200 msec
            self.crt_w // (vals_on_screen // vals_per_sec) // 5
        )
        self.xtick_max = self.crt_w // self.xtick_step
        self.ytick_step = self.ymid // 5  # big squate - .5 mV
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

    def drawcurve(  # pylint: disable=too-many-branches,too-many-statements
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
        # Grid labels
        for y, l in zip(
            range(self.ytick_max // 2), ("+2", "+1", "+0", "-1", "-2")
        ):
            drawtext(c, 5, (2 * y + 1) * self.ytick_step + 6, l)
        drawtext(c, 5, 20, "mV")
        # Grid
        c.set_source_rgb(0.4, 0.4, 0.4)
        c.set_line_width(2)
        for x in range(self.xtick_max):
            c.move_to(x * self.xtick_step, 0)
            c.line_to(x * self.xtick_step, self.crt_h)
        for y in range(self.ytick_max):
            c.move_to(25 if y % 2 else 0, y * self.ytick_step)
            c.line_to(self.crt_w, y * self.ytick_step)
        c.stroke()
        # Green signal trace
        c.set_source_rgb(0.0, 1.0, 0.0)
        c.set_line_width(4)
        last5: deque[float] = deque(maxlen=5)
        for x, val in enumerate(data):
            last5.append(val)
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

        # Blinking icon
        prev = 0.0
        act = 0.0
        for val in last5:
            act += abs(val - prev)
            prev = val
        c.select_font_face(
            # "Noto Color Emoji", FONT_SLANT_NORMAL, FONT_WEIGHT_NORMAL
            "Symbola",
            FONT_SLANT_NORMAL,
            FONT_WEIGHT_NORMAL,
        )
        c.set_source_rgb(0.0, 0.0, 1.0)
        if act > 0.5:
            c.set_font_size(36)
            c.move_to(55, 35)
            # fo = c.get_font_options()
            # fo.set_color_mode(ColorMode.COLOR)
            # c.set_font_options(fo)
            c.show_text("\u2665")  # WHY on earch is it BLUE?!
            # ("\U0001f498\U0001f499\U0001f49a\U0001f49b\U0001f49c")
        # Lead off
        c.set_font_size(28)
        c.move_to(105, 35)
        if fmeta.leadoff:
            c.set_source_rgb(0.0, 0.0, 1.0)
            c.show_text("\u268b")
        else:
            c.set_source_rgb(0.0, 1.0, 0.0)
            c.show_text("\u29df")
        # contin/interval
        c.set_source_rgb(0.0, 1.0, 0.0)
        if fmeta.mmode is MMode.continuous:
            c.move_to(155, 32)
            c.show_text("\u221e")
        elif fmeta.mmode is MMode.fast:
            c.move_to(155, 35)
            c.show_text("\u2b72")
        else:  # fmeta.mmode is MMode.detecting:
            c.move_to(155, 35)
            c.set_source_rgb(0.4, 0.4, 0.4)
            c.show_text("\u2b62")
        # Channel
        c.move_to(202, 33)
        clr, sym = {
            Channel.detecting: ((0.5, 0.5, 0.5), "\U0001f173"),
            Channel.internal: ((0.0, 1.0, 0.0), "\U0001f178"),
            Channel.external: ((0.0, 1.0, 0.0), "\U0001f174"),
        }.get(fmeta.channel, ((0.5, 0.5, 0.5), "\u2753"))
        c.set_source_rgb(*clr)
        c.show_text(sym)
        # Stage
        c.move_to(250, 33)
        clr, sym = {
            MStage.detecting: ((0.5, 0.5, 0.5), "\u24b9"),
            MStage.preparing: ((0.0, 1.0, 0.0), "\u24c5"),
            MStage.measuring: ((0.0, 1.0, 0.0), "\u24c2"),
            MStage.analyzing: ((0.0, 1.0, 0.0), "\u24b6"),
            MStage.result: ((0.0, 1.0, 0.0), "\u24c7"),
            MStage.stop: ((0.0, 0.0, 1.0), "\u24c8"),
        }.get(fmeta.mstage, ((0.5, 0.5, 0.5), "\u2753"))
        c.set_source_rgb(*clr)
        c.show_text(sym)
        # Gain
        drawtext(c, 405, 25, "Gain " + str(fmeta.gain))
        # Vol
        drawtext(c, 510, 25, "Vol " + str(fmeta.gain))
        # Datetime
        drawtext(
            c,
            20,
            self.crt_h - 15,
            fmeta.dtime.astimezone(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
            fsize=24,
        )
        # Heart rate
        drawtext(
            c,
            self.crt_w - 100,
            60,
            str(fmeta.hr) if fmeta.hr else "---",
            fsize=48,
        )
        # Battery level
        c.set_source_rgb(0.0, 1.0, 0.0)
        c.set_line_width(2)
        c.rectangle(self.crt_w - 80, self.crt_h - 35, 60, 20)
        c.stroke()
        c.rectangle(self.crt_w - 80, self.crt_h - 35, fmeta.battery * 20, 20)
        c.fill()

"""Conduit for passing received data to the consumer"""

from collections import deque
from datetime import datetime
from itertools import repeat
from time import time_ns
from typing import Optional, Tuple
from cairo import (
    Context,
    ImageSurface,
    FORMAT_ARGB32,
)

from .ble import Scanner, TestEvent
from .datatypes import (
    Event,
    EventPc80bContData,
    EventPc80bFastData,
    EventPc80bHeartbeat,
    EventPc80bTime,
    Channel,
    MMode,
    MStage,
)
from .drw import Drw, FrameMeta
from .gst import Pipe

import gi  # type: ignore [import-untyped]

gi.require_version("Gst", "1.0")
from gi.repository import Gst  # type: ignore [import-untyped]

FRAMES_PER_SEC = 30
VALS_PER_SEC = 150
SECS_ON_SCREEN = 3

VALS_ON_SCREEN = VALS_PER_SEC * SECS_ON_SCREEN
VALS_PER_FRAME = VALS_PER_SEC // FRAMES_PER_SEC
SAMPDUR = 1_000_000_000 // VALS_PER_SEC
FRAMEDUR = 1_000_000_000 // FRAMES_PER_SEC


class Signal:
    def __init__(self, crt_w: int, crt_h: int) -> None:
        self.crt_w = crt_w
        self.crt_h = crt_h
        self.datathread: Optional[Scanner] = None
        self.status = (False, "Uninitialised")
        self.data = deque(repeat(0.0, VALS_ON_SCREEN), maxlen=VALS_ON_SCREEN)
        self.samppos = 0
        self.battery = 0
        self.dtime = datetime(1,1,1)

    def cleardata(self) -> None:
        self.samppos = 0

    def start(self, state: bool) -> None:
        if self.datathread is not None:
            self.datathread.stop()
            self.datathread.join()
        self.datathread = Scanner(self, test=state)
        self.datathread.start()

    def stop(self) -> None:
        if self.datathread is not None:
            self.datathread.stop()
            self.datathread.join()
            self.datathread = None

    def report_status(self, receiving: bool, details: str) -> None:
        self.status = (receiving, details)

    def report_data(self, event: Event) -> None:
        if isinstance(
            event, (EventPc80bContData, EventPc80bFastData, TestEvent)
        ):
            if event.fin:
                # clean up something? Change status?
                return
            fmeta = FrameMeta(
                dtime = self.dtime,
                battery = self.battery,
                **{
                    k: getattr(event, k)
                    for k in FrameMeta._fields
                    if hasattr(event, k)
                }
            )
            with self.pipe.listmaker() as dispense:
                for i in range(len(event.ecgFloats) // VALS_PER_FRAME):
                    o = i * VALS_PER_FRAME
                    self.data.extend(event.ecgFloats[o : o + VALS_PER_FRAME])
                    self.samppos += VALS_PER_FRAME
                    if self.samppos >= VALS_ON_SCREEN:
                        self.samppos = 0
                    with dispense() as (mem, setts):
                        image = ImageSurface.create_for_data(
                            mem, FORMAT_ARGB32, self.crt_w, self.crt_h
                        )
                        c = Context(image)
                        try:
                            self.drw.drawcurve(
                                c, fmeta, self.data, self.samppos
                            )
                        finally:
                            del c
                            del image
                        setts(FRAMEDUR, (i + 15) * FRAMEDUR)
                        # print("buf", i, "with ts", i * FRAMEDUR)
            # print("buflist sent")
        elif isinstance(event, EventPc80bHeartbeat):
            self.battery = event.batt
        elif isinstance(event, EventPc80bTime):
            self.dtime = event.datetime
            print("time event", self.dtime)
        else:
            print("unhandled", event)

    def register_pipe(self, pipe: Pipe) -> None:
        self.pipe = pipe
        self.drw = Drw(self.crt_w, self.crt_h, VALS_ON_SCREEN)

    def on_need_data(self, source: Gst.Element, amount: int) -> None:
        print(
            "Need data, time",
            time_ns(),
            "source",
            source.get_current_clock_time(),
            "amount",
            amount,
        )

        with self.pipe.listmaker() as dispense:
            with dispense() as (mem, setts):
                image = ImageSurface.create_for_data(
                    mem, FORMAT_ARGB32, self.crt_w, self.crt_h
                )
                c = Context(image)
                try:
                    if self.status[0]:
                        self.drw.drawcurve(
                            c, FrameMeta(), repeat(0.0, VALS_ON_SCREEN), 0
                        )
                    else:
                        self.drw.clearscreen(c, self.status[1])
                finally:
                    del c
                    del image
                setts(FRAMEDUR, 0)

    def on_enough_data(self, source: Gst.Element) -> None:
        print("Uh-oh, got 'enough-data'")

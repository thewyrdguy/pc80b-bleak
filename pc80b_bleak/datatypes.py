from enum import Enum
from inspect import isclass
from sys import stderr
from struct import error, unpack
from datetime import datetime
from typing import ClassVar, Dict, List, NamedTuple, Type


class Channel(Enum):
    detecting = 0
    internal = 1
    external = 2


class MMode(Enum):
    detecting = 0
    fast = 1
    continuous = 2


class MStage(Enum):
    detecting = 0
    preparing = 1
    measuring = 2
    analyzing = 3
    result = 4
    stop = 5


class Event:
    ev: ClassVar[int]
    data: bytes = b""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def __repr__(self) -> str:
        return f"""{self.__class__.__name__}(0x{self.ev:02x}:{self.data.hex()[:16]} {', '.join(
                f'{k}={len(v) if isinstance(v,list) else v}'
                for k, v in self.__dict__.items()
                if not (k == 'data' or k.startswith('__')))})"""


class EventPc80bDeviceInfo(Event):
    ev = 0x11

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        size = len(data)
        if size == 6:
            self.softwareV = ".".join(str(e) for e in data[:4])  # c
        elif size == 8:
            self.softwareV = (
                ".".join(str(e) for e in data[:3])
                + "."
                + "".join(str(e) for e in data[3:])
            )  # c
        else:
            self.softwareV = str(data[0])  # c
        self.hardwareV = data[-2]  # d
        self.algorithmV = data[-1]  # e


class EventPc80bTime(Event):
    ev = 0x33  # Not sure. It should be time?

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.sc, self.mn, self.hr, self.dy, self.mo, self.yr, self.z = unpack(
            "<BBBBBHB", data[:8]
        )
        self.datetime = datetime(
            self.yr, self.mo, self.dy, self.hr, self.mn, self.sc
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"({self.yr:04d}-{self.mo:02d}-{self.dy:02d}"
            f" {self.hr:02d}:{self.mn:02d}:{self.sc:02d} {self.z})"
        )


class EventPc80bTransmode(Event):
    ev = 0x55  # end of preparation, need response

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        devtyp, modes = unpack("<BB", data[:2])
        self.model = {10: "PC-80A", 11: "PC-80B", 128: "PC-80B(UW)"}.get(
            devtyp, "<unknown>"
        )
        self.filtermode = (modes & 128) >> 7
        self.transtype = modes & 1
        self.serialno = data[2:].hex()


class EventPc80bContData(Event):
    ev = 0xAA

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.seqNo = data[0]
        if len(data) == 1:
            self.fin = True
            return
        self.fin = False
        try:
            bv, self.hr, vl, lgv = unpack("<50sBBB", data[1:])
        except error:
            print("LEN", len(data), "DATA", data.hex(), file=stderr)
            return
        self.leadoff = bool(lgv >> 7)
        self.gain = (lgv & 0x70) >> 4
        self.vol = ((lgv & 0x0F) << 8) + vl  # in 1/1000th
        try:
            self.ecgFloats = [
                (unpack("<H", bv[i : i + 2])[0] - 2048) / 330
                for i in range(0, len(bv), 2)
            ]
        except error:
            self.ecgFloats = []


class EventPc80bFastData(Event):
    ev = 0xDD

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.fin = False
        self.seqNo, xgain, cmsh, self.hr, ldt = unpack("<HBBBB", data[:6])
        #    0, 1    2      3         4    5
        self.gain = (xgain & 0x70) >> 4  # three bits
        self.channel = Channel((cmsh & 0xC0) >> 6)  # two bits
        self.mmode = MMode((cmsh & 0x30) >> 4)  # two bits
        self.mstage = MStage(cmsh & 0x0F)  # four bits
        self.leadoff = bool(ldt >> 7)
        self.datatype = ldt & 0x07  # three bits
        if self.mstage in (MStage.analyzing, MStage.result, MStage.stop):
            self.fin = True
            self.ecgFloats = []
        else:
            bv = data[6:]
            try:
                self.ecgFloats = [
                    (unpack("<H", bv[i : i + 2])[0] - 2048) / 330
                    for i in range(0, len(bv), 2)
                ]
            except error:
                self.ecgFloats = []


class EventPc80bHeartbeat(Event):
    ev = 0xFF


CLASSES: Dict[int, Type[Event]] = {
    cls.ev: cls
    for nm, cls in locals().items()
    if isclass(cls)
    and cls.__name__.startswith("EventPc80b")
    and cls is not Event
}


def mkEv(ev: int, data: bytes) -> Event:
    if ev in CLASSES:
        return CLASSES[ev](data)
    raise RuntimeError(f"EventPc80b???(0x{ev:02x}:{data.hex()} )")


class TestData(Event):
    def __init__(self, ecgFloats: List[float]) -> None:
        self.ecgFloats = ecgFloats

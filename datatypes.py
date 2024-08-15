from inspect import isclass
from struct import error, unpack
from typing import ClassVar, NamedTuple


class Event:
    ev: ClassVar[int]
    data: bytes = b""

    def __init__(self, data) -> None:
        self.data = data

    def __repr__(self) -> str:
        return f"""{self.__class__.__name__}(0x{self.ev:02x}:{self.data.hex()[:16]} {', '.join(
                f'{k}={len(v) if isinstance(v,list) else v}'
                for k, v in self.__dict__.items()
                if not (k == 'data' or k.startswith('__')))})"""


class EventPc80bDeviceInfo(Event):
    ev = 0x11


class EventPc80bTime(Event):
    ev = 0x33  # Not sure. It should be time?


class EventPc80bOff(Event):
    ev = 0xAA


class EventPc80bFastData(Event):
    ev = 0xDD

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.seqNo, xgain, cmsh, self.hr, ldt = unpack("<HBBBB", data[:6])
        #    0, 1    2      3         4    5
        self.gain = (xgain & 0x70) >> 4  # three bits
        self.channel = (cmsh & 0xC0) >> 6  # two bits
        self.mmode = {0: "detecting", 1: "fast", 2: "continuous"}.get(
            (cmsh & 0x30) >> 4, "???"
        )  # two bits
        self.mstage = {
            0: "detecting",
            1: "preparing",
            2: "measuring",
            3: "analyzing",
            4: "result",
            5: "stop",
        }.get(
            cmsh & 0x0F, "???"
        )  # four bits
        self.leadoff = bool(ldt >> 7)
        self.datatype = ldt & 0x07  # three bits
        bv = data[6:]
        try:
            self.ecgFloats = [
                (unpack("<H", bv[i : i + 2])[0] - 2048) / 330
                for i in range(0, len(bv), 2)
            ]
        except error:
            self.ecgFloats = []


class EventPc80bBatLevel(Event):
    ev = 0xFF


CLASSES = {
    cls.ev: cls
    for nm, cls in locals().items()
    if isclass(cls)
    and cls.__name__.startswith("EventPc80b")
    and cls is not Event
}


def mkEv(ev, data):
    if ev in CLASSES:
        return CLASSES[ev](data)
    return f"EventPc80b???(0x{ev:02x}:{data.hex()} )"

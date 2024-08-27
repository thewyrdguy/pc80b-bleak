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

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"({self.yr:04d}-{self.mo:02d}-{self.dy:02d}"
            f" {self.hr:02d}:{self.mn:02d}:{self.sc:02d} {self.z})"
        )


class EventPc80bReady(Event):
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


class EventPc80bEOR(Event):
    ev = 0xAA


class EventPc80bFastData(Event):
    ev = 0xDD

    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.seqNo, xgain, cmsh, self.hr, ldt = unpack("<HBBBB", data[:6])
        #    0, 1    2      3         4    5
        self.gain = (xgain & 0x70) >> 4  # three bits
        self.channel = {0: "detecting", 1: "internal", 2: "external"}.get(
            (cmsh & 0xC0) >> 6, "<?>"
        )  # two bits
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


class EventPc80bHeartbeat(Event):
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

"""BLE receiver"""

from __future__ import annotations
import asyncio
from getopt import getopt  # pylint: disable=deprecated-module
from sys import argv, stderr
from struct import pack, unpack
from threading import Thread
from time import time
from typing import List, Tuple, TYPE_CHECKING

from bleak import BleakScanner, BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from crcmod import predefined  # type: ignore [import-untyped]

from .datatypes import (
    mkEv,
    Event,
    EventPc80bContData,
    EventPc80bTransmode,
)

if TYPE_CHECKING:
    from .sgn import Signal

# pylint: disable=missing-function-docstring

DELAY = 3
DEVINFO = "0000180a-0000-1000-8000-00805f9b34fb"
PC80B_SRV = "0000fff0-0000-1000-8000-00805f9b34fb"
PC80B_OUT = "0000fff2-0000-1000-8000-00805f9b34fb"
PC80B_CTL = "0000fff3-0000-1000-8000-00805f9b34fb"
PC80B_NTF = "0000fff1-0000-1000-8000-00805f9b34fb"
PC80B_NTD = "00002902-0000-1000-8000-00805f9b34fb"

crc8 = predefined.mkCrcFun("crc-8-maxim")

disconnect = asyncio.Event()
task = None

verbose = False


class Receiver:  # pylint: disable=too-few-public-methods
    """Container for BLE receive async function"""

    def __init__(self, client: BleakClient, signal: Signal) -> None:
        self.length = 0
        self.buffer = b""
        self.received = asyncio.Event()
        self.clientref = client
        self.signal = signal
        self.last_time = 0.0

    async def receive(self, _ch: BleakGATTCharacteristic, val: bytes) -> None:
        self.buffer += val
        while len(self.buffer) > self.length:
            if len(self.buffer) < 3:
                break
            (self.length,) = unpack("B", self.buffer[2:3])
            self.length += 4
            if len(self.buffer) < self.length:
                break
            frame = self.buffer[: self.length]
            self.buffer = self.buffer[self.length :]
            self.length = 0
            self.received.set()
            # print(len(frame), ":", frame.hex(), file=stderr)
            data = frame[:-1]
            crc = int.from_bytes(frame[-1:])
            if crc != crc8(data):
                print("CRC MISMATCH", data.hex(), crc, file=stderr)
            st, evt = unpack("BB", data[:2])
            if st != 0xA5:
                print("BAD START", data.hex(), file=stderr)
            ev = mkEv(evt, data[3:])
            self.signal.report_data(ev)
            if isinstance(ev, EventPc80bTransmode):
                print("Sending ACK", file=stderr)
                runcont = bytes.fromhex("a55501") + pack(
                    "B", 0x01 if ev.transtype else 0x00
                )
                bcrc = pack("B", crc8(runcont))
                print("SENDING:", runcont.hex(), bcrc.hex(), file=stderr)
                await self.clientref.write_gatt_char(
                    PC80B_OUT, runcont + bcrc, response=True
                )
            elif isinstance(ev, EventPc80bContData):
                if ev.fin or (ev.seqNo % 64 == 0):
                    print("Sending ACK", file=stderr)
                    cdack = (
                        bytes.fromhex("a5aa02") + ev.seqNo.to_bytes() + b"\0"
                    )
                    bcrc = pack("B", crc8(cdack))
                    print("SENDING:", cdack.hex(), bcrc.hex(), file=stderr)
                    await self.clientref.write_gatt_char(
                        PC80B_OUT, cdack + bcrc, response=True
                    )

            now = time()
            if now - self.last_time > 10:
                self.last_time = now
                hb = bytes.fromhex("a5ff0100")
                bcrc = pack("B", crc8(hb))
                print("SENDING:", hb.hex(), bcrc.hex(), file=stderr)
                await self.clientref.write_gatt_char(
                    PC80B_OUT, hb + bcrc, response=True
                )


def on_disconnect(client: BleakClient) -> None:
    print("Disconnect callback", client)
    disconnect.set()


async def scanner(signal: Signal) -> None:
    global task  # pylint: disable=global-statement
    task = asyncio.current_task()
    try:
        signal.report_status(False, "Scanning")
        # pylint: disable=undefined-loop-variable
        async with BleakScanner() as bscanner:
            print("Waiting for PC80B-BLE device to appear...", file=stderr)
            async for dev, data in bscanner.advertisement_data():
                # print(dev, "\n", data, "\n", file=stderr)
                if dev.name == "PC80B-BLE":
                    # if PC80B_SRV in data.service_uuids:
                    break
        signal.report_status(False, f"Found {dev}")
        print(
            "Trying to use device",
            dev,
            "rssi",
            data.rssi,
            "wait",
            DELAY,
            "sec",
            file=stderr,
        )
        await asyncio.sleep(DELAY)
        try:
            async with BleakClient(
                dev, disconnected_callback=on_disconnect
            ) as client:
                # Disconnect callback may have been called in the duration
                # of connecting and querying attributes. If we got here,
                # it means that they should be ignored. True failure to
                # connect is reported as TimeoutError execption, that we
                # handle below. And disconnect that happens _after_ this
                # point will really result in dropping out of the context.
                disconnect.clear()

                srvd = {srv.uuid: srv for srv in client.services}
                # print("srvd", srvd, file=stderr)
                details = ", ".join(
                    [
                        # pylint: disable=line-too-long
                        f"{char.description.split()[0]}: "
                        f"{(await client.read_gatt_char(char)).decode('ascii')}"
                        for char in srvd[DEVINFO].characteristics
                    ]
                )
                print("Connected;", details, file=stderr)
                chrd = {
                    char.uuid: char for char in srvd[PC80B_SRV].characteristics
                }
                # print("chrd", chrd, file=stderr)
                ctlval = await client.read_gatt_char(PC80B_CTL)
                # print("ctlval", ctlval.hex(), file=stderr)
                ntf = chrd[PC80B_NTF]
                # dscd = {
                #     descriptor.uuid: descriptor
                #     for descriptor in ntf.descriptors
                # }
                # ntdval = await client.read_gatt_descriptor(
                #     dscd[PC80B_NTD].handle
                # )
                # print("ntdval", ntdval.hex(), file=stderr)
                signal.report_status(True, f"Connected {dev} {details}")
                print(
                    "All controls are in place, ctl value",
                    ctlval.hex(),
                    file=stderr,
                )
                receiver = Receiver(client, signal)
                await client.start_notify(ntf, receiver.receive)
                # devinfo = bytes.fromhex("5a1106000000000000")
                # crc = pack("B", crc8(devinfo))
                # print("SENDING:", devinfo.hex(), crc.hex(), file=stderr)
                # await client.write_gatt_char(PC80B_OUT, devinfo + crc)
                await disconnect.wait()
                signal.report_status(False, "Disconnected")
                print("Disconnecting", file=stderr)
        except TimeoutError:
            print("Timeout connecting, retry")
        print("Disconnected", file=stderr)
    except asyncio.exceptions.CancelledError:
        return


class TestEvent(Event):
    # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Mock event for testing"""

    ev = 0xFF

    def __init__(self, floats: List[float]) -> None:
        super().__init__(b"")
        self.fin = False
        self.seqNo = 0
        self.hr = 0
        self.gain = 0
        self.channel = 0
        self.mmode = 0
        self.mstage = 0
        self.leadoff = True
        self.datatype = 0
        self.mstage = 0
        self.ecgFloats = floats


async def testsrc(signal: Signal) -> None:
    global task  # pylint: disable=global-statement
    task = asyncio.current_task()
    print("Launched test source")
    signal.report_status(True, "Sending test ladder signal")
    step = 0
    try:
        while True:
            if step > 6:
                step = 0
            values = [step - 3.0 for i in range(25)]
            signal.report_data(TestEvent(values))
            step += 1
            await asyncio.sleep(0.166666666)
    except asyncio.exceptions.CancelledError:
        return


class Scanner(Thread):
    """BLE scanning thread"""

    def __init__(self, signal: Signal, test: bool) -> None:
        super().__init__()
        self.signal = signal
        self.test = test

    def run(self) -> None:
        asyncio.run((testsrc if self.test else scanner)(self.signal))
        print("asyncio.run finished")

    def stop(self) -> None:
        global task  # pylint: disable=global-statement
        print("scanner stop called")
        disconnect.set()
        if task is not None:
            task.cancel()
            task = None


if __name__ == "__main__":
    topts, args = getopt(argv[1:], "hva:")
    opts = dict(topts)
    verbose = "-v" in opts

    class PseudoSignal(Signal):  # pylint: disable=used-before-assignment
        """Mock receiver for testing"""

        def report_ble(self, connected: bool, sts: Tuple[int, str]) -> None:
            print("report_ble", sts, "connected:", connected)

        def report_ecg(self, ev: Event) -> None:
            print("report_ecg", ev)

    try:
        asyncio.run(scanner(PseudoSignal(0, 0)))
    except KeyboardInterrupt:
        print("Exit", file=stderr)

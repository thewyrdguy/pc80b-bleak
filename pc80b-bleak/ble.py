#!/usr/bin/python3

import asyncio
from getopt import getopt
from os import mknod, unlink, write
from stat import S_IFIFO
from sys import argv, stderr, stdout
from struct import pack, unpack
from threading import Thread
from time import time_ns
from bleak import backends, BleakScanner, BleakClient
from crcmod import predefined

from .datatypes import (
    mkEv,
    EventPc80bContData,
    EventPc80bFastData,
    EventPc80bTransmode,
    EventPc80bTime,
    TestData,
)
from .sgn import Signal

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


class Receiver:
    def __init__(self, client, signal):
        self.length = 0
        self.buffer = b""
        self.received = asyncio.Event()
        self.clientref = client
        self.signal = signal

    async def receive(self, char, val):
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
            # self.signal.report_ecg(ev)
            if isinstance(ev, (EventPc80bContData, EventPc80bFastData)):
                start = time_ns() - 6666666 * len(ev.ecgFloats)
                self.signal.push(
                    list(
                        zip(
                            (
                                start + i * 6666666
                                for i in range(len(ev.ecgFloats))
                            ),
                            ev.ecgFloats,
                        )
                    )
                )
            if isinstance(ev, EventPc80bTransmode):
                print("Sending ACK", file=stderr)
                runcont = bytes.fromhex("a55501") + pack(
                    "B", 0x01 if ev.transtype else 0x00
                )
                crc = pack("B", crc8(runcont))
                print("SENDING:", runcont.hex(), crc.hex(), file=stderr)
                await self.clientref.write_gatt_char(
                    PC80B_OUT, runcont + crc, response=True
                )
            elif isinstance(ev, EventPc80bContData):
                if ev.fin or (ev.seqNo % 64 == 0):
                    print("Sending ACK", file=stderr)
                    cdack = (
                        bytes.fromhex("a5aa02") + ev.seqNo.to_bytes() + b"\0"
                    )
                    crc = pack("B", crc8(cdack))
                    print("SENDING:", cdack.hex(), crc.hex(), file=stderr)
                    await self.clientref.write_gatt_char(
                        PC80B_OUT, cdack + crc, response=True
                    )


def on_disconnect(client):
    print("Disconnect callback")
    disconnect.set()


async def scanner(signal):
    global task
    task = asyncio.current_task()
    try:
        signal.report_status(False, f"Scanning")
        async with BleakScanner() as scanner:
            print("Waiting for PC80B-BLE device to appear...", file=stderr)
            async for dev, data in scanner.advertisement_data():
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
                dscd = {
                    descriptor.uuid: descriptor
                    for descriptor in ntf.descriptors
                }
                ntdval = await client.read_gatt_descriptor(
                    dscd[PC80B_NTD].handle
                )
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


async def testsrc(signal):
    global task
    task = asyncio.current_task()
    print("Launched test source")
    signal.report_status(True, "Sending test ladder signal")
    step = 0
    try:
        while True:
            if step > 6:
                step = 0
            start = time_ns() - 166666666  # 1_000_000_000 * 25 // 150
            values = [(start + i * 6666666, step - 3.0) for i in range(25)]
            signal.push(values)
            step += 1
            await asyncio.sleep(0.166666666)
    except asyncio.exceptions.CancelledError:
        return


class Scanner(Thread):
    def __init__(self, signal: Signal, test: bool = False) -> None:
        super().__init__()
        self.signal = signal
        self.test = test

    def run(self) -> None:
        asyncio.run((testsrc if self.test else scanner)(self.signal))
        print("asyncio.run finished")

    def stop(self) -> None:
        global task
        print("scanner stop called")
        disconnect.set()
        if task is not None:
            task.cancel()
            task = None


if __name__ == "__main__":
    topts, args = getopt(argv[1:], "hva:")
    opts = dict(topts)
    verbose = "-v" in opts

    class Gui:
        def report_ble(self, connected, sts) -> None:
            print("report_ble", sts)

        def report_ecg(self, ev) -> None:
            print("report_ecg", ev)

    try:
        asyncio.run(scanner(Gui()))
    except KeyboardInterrupt:
        print("Exit", file=stderr)

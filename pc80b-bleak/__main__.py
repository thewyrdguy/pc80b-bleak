#!/usr/bin/python3

import asyncio
from getopt import getopt
from os import mknod, unlink
from stat import S_IFIFO
from sys import argv
from struct import pack, unpack
from bleak import backends, BleakScanner, BleakClient
from crcmod import predefined

from .datatypes import (
    mkEv,
    EventPc80bContData,
    EventPc80bFastData,
    EventPc80bTransmode,
    EventPc80bTime,
)

DELAY = 2
DEVINFO = "0000180a-0000-1000-8000-00805f9b34fb"
PC80B_SRV = "0000fff0-0000-1000-8000-00805f9b34fb"
PC80B_OUT = "0000fff2-0000-1000-8000-00805f9b34fb"
PC80B_CTL = "0000fff3-0000-1000-8000-00805f9b34fb"
PC80B_NTF = "0000fff1-0000-1000-8000-00805f9b34fb"
PC80B_NTD = "00002902-0000-1000-8000-00805f9b34fb"

crc8 = predefined.mkCrcFun("crc-8-maxim")

stop = asyncio.Event()


class Receiver:
    def __init__(self, client, outstream):
        self.length = 0
        self.buffer = b""
        self.received = asyncio.Event()
        self.clientref = client
        self.outstream = outstream
        self.timestamp = 0.0

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
            # print(len(frame), ":", frame.hex())
            data = frame[:-1]
            crc = int.from_bytes(frame[-1:])
            if crc != crc8(data):
                print("CRC MISMATCH", data.hex(), crc)
            st, evt = unpack("BB", data[:2])
            if st != 0xA5:
                print("BAD START", data.hex())
            ev = mkEv(evt, data[3:])
            print(ev)
            if isinstance(ev, EventPc80bTime):
                self.timestamp = ev.datetime.timestamp()
            elif isinstance(ev, EventPc80bTransmode):
                print("Sending ACK")
                runcont = bytes.fromhex("a55501") + pack(
                    "B", 0x01 if ev.transtype else 0x00
                )
                crc = pack("B", crc8(runcont))
                print("SENDING:", runcont.hex(), crc.hex())
                await self.clientref.write_gatt_char(
                    PC80B_OUT, runcont + crc, response=True
                )
            elif isinstance(ev, EventPc80bContData):
                if ev.fin or (ev.seqNo % 64 == 0):
                    print("Sending ACK")
                    cdack = (
                        bytes.fromhex("a5aa02") + ev.seqNo.to_bytes() + b"\0"
                    )
                    crc = pack("B", crc8(cdack))
                    print("SENDING:", cdack.hex(), crc.hex())
                    await self.clientref.write_gatt_char(
                        PC80B_OUT, cdack + crc, response=True
                    )
                if ev.fin:
                    stop.set()
                else:
                    for sample in ev.ecgFloats:
                        outstream.write(
                            f"{self.timestamp} {sample} 0 0\n".encode("ascii")
                        )
                        self.timestamp += 0.006666666666666667
            elif isinstance(ev, EventPc80bFastData):
                for sample in ev.ecgFloats:
                    outstream.write(
                        f"{self.timestamp} {sample} 0 0\n".encode("ascii")
                    )
                    self.timestamp += 0.006666666666666667


async def main(outstream):
    async with BleakScanner() as scanner:
        print("Waiting for PC80B-BLE device to appear...")
        async for dev, data in scanner.advertisement_data():
            # print(dev, "\n", data, "\n")
            if dev.name == "PC80B-BLE":
                # if PC80B_SRV in data.service_uuids:
                break
    print("Trying to use device", dev, "rssi", data.rssi, "wait", DELAY, "sec")
    await asyncio.sleep(DELAY)
    async with BleakClient(dev) as client:
        srvd = {srv.uuid: srv for srv in client.services}
        # print("srvd", srvd)
        print(
            "Connected;",
            ", ".join(
                [
                    f"{char.description.split()[0]}: "
                    f"{(await client.read_gatt_char(char)).decode('ascii')}"
                    for char in srvd[DEVINFO].characteristics
                ]
            ),
        )
        chrd = {char.uuid: char for char in srvd[PC80B_SRV].characteristics}
        # print("chrd", chrd)
        ctlval = await client.read_gatt_char(PC80B_CTL)
        # print("ctlval", ctlval.hex())
        ntf = chrd[PC80B_NTF]
        dscd = {descriptor.uuid: descriptor for descriptor in ntf.descriptors}
        ntdval = await client.read_gatt_descriptor(dscd[PC80B_NTD].handle)
        # print("ntdval", ntdval.hex())
        print(
            "All controls are in place, ctl value",
            ctlval.hex(),
        )
        receiver = Receiver(client, outstream)
        await client.start_notify(ntf, receiver.receive)
        # devinfo = bytes.fromhex("5a1106000000000000")
        # crc = pack("B", crc8(devinfo))
        # print("SENDING:", devinfo.hex(), crc.hex())
        # await client.write_gatt_char(PC80B_OUT, devinfo + crc)
        await stop.wait()

        outstream.close()
        print("Disconnecting")
    print("Disconnected")


async def shutdown(outstream):
    print("Shutdown")
    outstream.close()


if __name__ == "__main__":
    topts, args = getopt(argv[1:], "hva:")
    opts = dict(topts)
    sockname = args[0] if len(args) >= 1 else "/tmp/pc80b.sock"
    #try:
    #    unlink(sockname)
    #except FileNotFoundError:
    #    pass
    try:
        mknod(sockname, S_IFIFO | 0o644)
    except FileExistsError:
        pass
    outstream = open(sockname, "wb", buffering=0)
    try:
        asyncio.run(main(outstream))
    except KeyboardInterrupt:
        asyncio.run(shutdown(outstream))
        print("Exit")

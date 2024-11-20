#!/usr/bin/python3

import asyncio
from struct import pack, unpack
from bleak import backends, BleakScanner, BleakClient
from crcmod import predefined

from .datatypes import mkEv, EventPc80bContData, EventPc80bReady

DELAY = 2
DEVINFO = "0000180a-0000-1000-8000-00805f9b34fb"
PC80B_SRV = "0000fff0-0000-1000-8000-00805f9b34fb"
PC80B_OUT = "0000fff2-0000-1000-8000-00805f9b34fb"
PC80B_CTL = "0000fff3-0000-1000-8000-00805f9b34fb"
PC80B_NTF = "0000fff1-0000-1000-8000-00805f9b34fb"
PC80B_NTD = "00002902-0000-1000-8000-00805f9b34fb"

crc8 = predefined.mkCrcFun("crc-8-maxim")

stop = asyncio.Event()


async def frame_receiver(char, val):
    char.buffer += val
    while len(char.buffer) > char.length:
        if len(char.buffer) < 3:
            break
        (char.length,) = unpack("B", char.buffer[2:3])
        char.length += 4
        if len(char.buffer) < char.length:
            break
        frame = char.buffer[: char.length]
        char.buffer = char.buffer[char.length :]
        char.length = 0
        char.received.set()
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
        if isinstance(ev, EventPc80bReady):
            print("Sending ACK")
            runcont = bytes.fromhex("a5550100")
            crc = pack("B", crc8(runcont))
            print("SENDING:", runcont.hex(), crc.hex())
            await char.clientref.write_gatt_char(
                PC80B_OUT, runcont + crc, response=True
            )
        elif isinstance(ev, EventPc80bContData) and ev.fin:
            print("Data FIN, Sending ACK")
            cdack =  bytes.fromhex("a5aa02") + ev.seqNo.to_bytes() + b"\0"
            crc = pack("B", crc8(cdack))
            print("SENDING:", cdack.hex(), crc.hex())
            await char.clientref.write_gatt_char(
                PC80B_OUT, cdack + crc, response=True
            )
            stop.set()


async def main():
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

        ntf.length = 0
        ntf.buffer = b""
        ntf.received = asyncio.Event()
        ntf.clientref = client
        await client.start_notify(ntf, frame_receiver)
        #devinfo = bytes.fromhex("5a1106000000000000")
        #crc = pack("B", crc8(devinfo))
        #print("SENDING:", devinfo.hex(), crc.hex())
        #await client.write_gatt_char(PC80B_OUT, devinfo + crc)
        await stop.wait()

        print("Disconnecting")
    print("Disconnected")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        stop.set()
        print("Exit")

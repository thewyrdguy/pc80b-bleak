#!/usr/bin/python3

import asyncio
from struct import unpack
from bleak import backends, BleakScanner, BleakClient
from crcmod import predefined

from datatypes import mkEv

DELAY = 2
DEVINFO = "0000180a-0000-1000-8000-00805f9b34fb"
PC80B_SRV = "0000fff0-0000-1000-8000-00805f9b34fb"
PC80B_OUT = "0000fff2-0000-1000-8000-00805f9b34fb"
PC80B_CTL = "0000fff3-0000-1000-8000-00805f9b34fb"
PC80B_NTF = "0000fff1-0000-1000-8000-00805f9b34fb"
PC80B_NTD = "00002902-0000-1000-8000-00805f9b34fb"

crc8 = predefined.mkCrcFun("crc-8-maxim")

stop = asyncio.Event()

def frame_receiver(char, val):
    char.buffer += val
    while len(char.buffer) > char.length:
        if len(char.buffer) < 3:
            break
        (char.length,) = unpack("B", char.buffer[2:3])
        char.length += 4
        if len(char.buffer) < char.length:
            break
        frame = char.buffer[:char.length]
        char.buffer = char.buffer[char.length:]
        char.length = 0
        char.received.set()
        print(len(frame), ":", frame.hex())
        data = frame[:-1]
        crc = int.from_bytes(frame[-1:])
        if crc != crc8(data):
            print("CRC MISMATCH", data.hex(), crc)
        st, ev = unpack("BB", data[:2])
        if st != 0xa5:
            print("BAD START", data.hex())
        print(mkEv(ev, data[3:]))


async def main():
    async with BleakScanner() as scanner:
        print("Waiting for PC80B-BLE device to appear...")
        async for dev, data in scanner.advertisement_data():
            # print(dev, "\n", data, "\n")
            if dev.name == "PC80B-BLE":
                break
    print("Trying to use device", dev, "rssi", data.rssi, "wait", DELAY, "sec")
    await asyncio.sleep(DELAY)
    async with BleakClient(dev) as client:
        devinfo = next(srv for srv in client.services if srv.uuid == DEVINFO)
        print(
            "Connected;",
            ", ".join(
                [
                    f"{char.description.split()[0]}: "
                    f"{(await client.read_gatt_char(char)).decode('utf-8')}"
                    for char in devinfo.characteristics
                ]
            ),
        )
        srv = None
        out = None
        ctl = None
        ntf = None
        ntd = None
        ctlval = None
        for service in client.services:
            if service.uuid == DEVINFO:
                continue
            if service.uuid == PC80B_SRV:
                srv = service
            else:
                print("Service", service)
            for char in service.characteristics:
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char.uuid)
                    except Exception as e:
                        value = e
                else:
                    value = "<not readable>"
                if service.uuid == PC80B_SRV and char.uuid == PC80B_OUT:
                    out = char
                elif service.uuid == PC80B_SRV and char.uuid == PC80B_CTL:
                    ctl = char
                    ctlval = value
                elif service.uuid == PC80B_SRV and char.uuid == PC80B_NTF:
                    ntf = char
                else:
                    print("\tCharacteristic", char, value, char.properties)
                    if "write-without-response" in char.properties:
                        print(
                            "\t\tmax write",
                            char.max_write_without_response_size,
                        )
                for descriptor in char.descriptors:
                    try:
                        value = await client.read_gatt_descriptor(
                            descriptor.handle
                        )
                    except Exception as e:
                        value = e
                    if (
                        service.uuid == PC80B_SRV
                        and char.uuid == PC80B_NTF
                        and descriptor.uuid == PC80B_NTD
                    ):
                        ntd = descriptor
                        ntdval = value
                    else:
                        print("\t\tDescriptor:", descriptor, value)
        if all(x is not None for x in (srv, out, ctl, ntf, ntd)):
            print("All controls are in place, ctl value", ctlval.hex(), "desc value", ntdval.hex())

            ntf.length = 0
            ntf.buffer = b""
            ntf.received = asyncio.Event()
            await client.start_notify(ntf, frame_receiver)
            await ntf.received.wait()
            print("SENDING:", "a511030000008e")
            await client.write_gatt_char(ctl, bytes.fromhex("a511030000008e"))
            await stop.wait()

        print("Disconnecting")
    print("Disconnected")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        stop.set()
        print("Exit")

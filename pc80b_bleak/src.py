"""Source of samples: either BLE receiver or test source"""

from __future__ import annotations

from threading import Thread
from typing import TYPE_CHECKING

from .ble import BleSrc
from .tst import TestSrc

if TYPE_CHECKING:
    from .sgn import Signal

# pylint: disable=missing-function-docstring


class Source(Thread):
    """Thread that submits samples, from BLE or test"""

    def __init__(self, signal: Signal, test: bool) -> None:
        super().__init__()
        self.src = TestSrc(signal) if test else BleSrc(signal)

    def run(self) -> None:
        self.src.run()
        print("asyncio.run finished")

    def stop(self) -> None:
        print("Source stop called")
        self.src.stop()
        self.join()
        print("Source thread joined")

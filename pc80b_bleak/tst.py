"""Emulated asyncio receiver"""

from __future__ import annotations
from asyncio import current_task, run, sleep, Task
from asyncio.exceptions import CancelledError
from typing import Any, Generator, Optional, Tuple, TYPE_CHECKING

from .datatypes import (
    EventPc80bContData,
    EventPc80bTransmode,
    EventPc80bTime,
    EventPc80bHeartbeat,
    Channel,
    MMode,
    MStage,
)
from .sample import sample

if TYPE_CHECKING:
    from .sgn import Signal

# pylint: disable=missing-function-docstring


def _give25() -> Generator[Tuple[float, ...]]:
    pos = 0
    while True:
        npos = pos + 25
        yield sample[pos:npos]
        if npos >= 150:
            pos = 0
        else:
            pos = npos


give25 = _give25()


class TestSrc:
    """Warpper for cancellable async task"""

    def __init__(self, signal: Signal) -> None:
        self.signal = signal
        self.task: Optional[Task[Any]] = None

    async def _task(self) -> None:
        self.task = current_task()
        print("Launched test source")
        # signal.report_status(True, "Sending test ladder signal")
        step = 0
        try:
            while True:
                if step > 4:
                    step = 0
                values = next(give25)
                print(step, values)
                # signal.report_data(TestEvent(values))
                step += 1
                await sleep(0.166666666)
        except CancelledError:
            print("Async task got cancelled")
            self.task = None

    # pylint: disable=duplicate-code

    def run(self) -> None:
        if self.task is None:
            run(self._task())
        else:
            print("Async task already running")

    def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
        else:
            print("Trying to cancel non-running task")

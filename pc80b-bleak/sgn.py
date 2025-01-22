"""Conduit for passing received data to the consumer"""

from collections import deque
from typing import List, Tuple

DEPTH = 150 * 3


class Signal:
    def __init__(self) -> None:
        self.data = deque([], DEPTH)
        self.status = (False, "Uninitialized")

    def push(self, data: List[Tuple[int, float]]) -> None:
        self.data.extend(data)

    def pull(self, amount: int) -> List[Tuple[int, float]]:
        try:
            return [self.data.popleft() for _ in range(amount)]
        except IndexError:  # Ran out of data
            return []

    def is_empty(self) -> bool:
        return not bool(self.data)

    def report_status(self, receiving: bool, details: str) -> None:
        self.status = (receiving, details)

    def get_status(self) -> Tuple[bool, str]:
        return self.status

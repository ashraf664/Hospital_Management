"""A dynamically growing circular-buffer FIFO queue."""

from collections.abc import Iterator
from typing import Generic, TypeVar, cast

from data_structures.dynamic_array import DynamicArray


T = TypeVar("T")


class Queue(Generic[T]):
    """Store values in first-in-first-out order.

    Enqueue is amortized O(1); dequeue, peek, is_empty, and size are O(1).
    Find scans the queue in O(n).
    """

    def __init__(self, initial_capacity: int = 4) -> None:
        if initial_capacity < 1:
            raise ValueError("initial_capacity must be at least 1.")
        self._buffer: DynamicArray[T] = DynamicArray(initial_capacity)
        self._head = 0
        self._size = 0

    @property
    def capacity(self) -> int:
        """Return the current ring-buffer capacity."""
        return self._buffer.capacity

    def enqueue(self, value: T) -> None:
        """Add value at the rear of the queue."""
        if self._size == self._buffer.capacity:
            self._resize(self._buffer.capacity * 2)
        tail = (self._head + self._size) % self._buffer.capacity
        self._buffer._set_slot(tail, value)
        self._size += 1

    def dequeue(self) -> T:
        """Remove and return the oldest value, or raise IndexError if empty."""
        if self.is_empty():
            raise IndexError("dequeue from empty queue.")
        value = self._buffer._get_slot(self._head)
        self._buffer._clear_slot(self._head)
        self._head = (self._head + 1) % self._buffer.capacity
        self._size -= 1
        return cast(T, value)

    def peek(self) -> T:
        """Return the oldest value without removing it."""
        if self.is_empty():
            raise IndexError("peek from empty queue.")
        return cast(T, self._buffer._get_slot(self._head))

    def is_empty(self) -> bool:
        """Return whether the queue contains no values."""
        return self._size == 0

    def size(self) -> int:
        """Return the number of queued values."""
        return self._size

    def find(self, value: T) -> bool:
        """Return whether value exists in the queue, scanning in O(n)."""
        for offset in range(self._size):
            index = (self._head + offset) % self._buffer.capacity
            if self._buffer._get_slot(index) == value:
                return True
        return False

    def _resize(self, new_capacity: int) -> None:
        new_buffer: DynamicArray[T] = DynamicArray(new_capacity)
        for offset in range(self._size):
            old_index = (self._head + offset) % self._buffer.capacity
            new_buffer._set_slot(offset, self._buffer._get_slot(old_index))
        self._buffer = new_buffer
        self._head = 0

    def __iter__(self) -> Iterator[T]:
        for offset in range(self._size):
            index = (self._head + offset) % self._buffer.capacity
            yield cast(T, self._buffer._get_slot(index))

    def __len__(self) -> int:
        return self._size

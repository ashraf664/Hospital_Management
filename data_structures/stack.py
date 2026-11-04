"""A LIFO stack backed by the custom dynamic array."""

from collections.abc import Iterator
from typing import Generic, TypeVar

from data_structures.dynamic_array import DynamicArray


T = TypeVar("T")


class Stack(Generic[T]):
    """Store the most recently pushed value at the top.

    Push is amortized O(1); pop, peek, is_empty, and size are O(1).
    Find scans the stack in O(n).
    """

    def __init__(self, initial_capacity: int = 4) -> None:
        self._items: DynamicArray[T] = DynamicArray(initial_capacity)

    def push(self, value: T) -> None:
        """Add value to the top of the stack."""
        self._items.append(value)

    def pop(self) -> T:
        """Remove and return the top value, or raise IndexError if empty."""
        if self.is_empty():
            raise IndexError("pop from empty stack.")
        return self._items._pop_last()

    def peek(self) -> T:
        """Return the top value without removing it."""
        if self.is_empty():
            raise IndexError("peek from empty stack.")
        return self._items.get(self._items.size() - 1)

    def is_empty(self) -> bool:
        """Return whether the stack contains no values."""
        return self._items.size() == 0

    def size(self) -> int:
        """Return the number of values on the stack."""
        return self._items.size()

    def find(self, value: T) -> bool:
        """Return whether value exists, scanning in O(n)."""
        return self._items.find(value) != -1

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __len__(self) -> int:
        return self._items.size()

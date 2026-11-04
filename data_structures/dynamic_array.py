"""A manually managed, resizable array with contiguous indexed storage."""

from collections.abc import Iterator
from typing import Generic, TypeVar, cast


T = TypeVar("T")
_EMPTY = object()


class DynamicArray(Generic[T]):
    """Store values in a contiguous buffer that grows and shrinks as needed.

    Indexed access and replacement are O(1). Append is amortized O(1);
    insertion and removal while preserving order are O(n). Iteration is O(n).
    """

    def __init__(self, initial_capacity: int = 4) -> None:
        if initial_capacity < 1:
            raise ValueError("initial_capacity must be at least 1.")
        self._minimum_capacity = initial_capacity
        self._capacity = initial_capacity
        self._size = 0
        self._items: list[object] = [_EMPTY] * initial_capacity

    @property
    def capacity(self) -> int:
        """Return the number of allocated storage slots."""
        return self._capacity

    def size(self) -> int:
        """Return the number of stored values."""
        return self._size

    def get(self, index: int) -> T:
        """Return a value; non-integer indexes raise TypeError, invalid indexes IndexError."""
        self._check_element_index(index)
        return cast(T, self._items[index])

    def set(self, index: int, value: T) -> None:
        """Replace the value at index."""
        self._check_element_index(index)
        self._items[index] = value

    def append(self, value: T) -> None:
        """Add a value at the end, growing the buffer when it is full."""
        if self._size == self._capacity:
            self._resize(self._capacity * 2)
        self._items[self._size] = value
        self._size += 1

    def insert(self, index: int, value: T) -> None:
        """Insert at [0, size]; reject non-integers with TypeError."""
        self._check_index_type(index)
        if index < 0 or index > self._size:
            raise IndexError("insert index out of range.")
        if self._size == self._capacity:
            self._resize(self._capacity * 2)
        for position in range(self._size, index, -1):
            self._items[position] = self._items[position - 1]
        self._items[index] = value
        self._size += 1

    def remove(self, index: int) -> T:
        """Remove and return the value at index."""
        self._check_element_index(index)
        removed = cast(T, self._items[index])
        for position in range(index, self._size - 1):
            self._items[position] = self._items[position + 1]
        self._size -= 1
        self._clear_slot(self._size)
        if (
            self._capacity > self._minimum_capacity
            and self._size <= self._capacity // 4
        ):
            self._resize(max(self._minimum_capacity, self._capacity // 2))
        return removed

    def remove_at(self, index: int) -> T:
        """Alias for remove(index), matching the SRS operation name."""
        return self.remove(index)

    def _pop_last(self) -> T:
        """Remove the final value without shrinking, in O(1) time."""
        if self._size == 0:
            raise IndexError("pop from empty array.")
        self._size -= 1
        value = cast(T, self._items[self._size])
        self._clear_slot(self._size)
        return value

    def find(self, value: T) -> int:
        """Return the first matching index, or -1 when the value is absent."""
        for index in range(self._size):
            if self._items[index] == value:
                return index
        return -1

    def _check_element_index(self, index: int) -> None:
        self._check_index_type(index)
        if index < 0 or index >= self._size:
            raise IndexError("array index out of range.")

    @staticmethod
    def _check_index_type(index: int) -> None:
        """Require a plain integer index; booleans are not accepted as indexes."""
        if type(index) is not int:
            raise TypeError("index must be an integer.")

    def _get_slot(self, index: int) -> T | None:
        """Read a physical slot; use _is_slot_empty to distinguish empty from None."""
        self._check_index_type(index)
        if index < 0 or index >= self._capacity:
            raise IndexError("storage slot out of range.")
        item = self._items[index]
        return None if item is _EMPTY else cast(T, item)

    def _set_slot(self, index: int, value: T | None) -> None:
        """Store any value, including None, in a physical slot."""
        self._check_index_type(index)
        if index < 0 or index >= self._capacity:
            raise IndexError("storage slot out of range.")
        self._items[index] = value

    def _clear_slot(self, index: int) -> None:
        """Mark a physical slot empty without reserving None as a sentinel."""
        self._check_index_type(index)
        if index < 0 or index >= self._capacity:
            raise IndexError("storage slot out of range.")
        self._items[index] = _EMPTY

    def _is_slot_empty(self, index: int) -> bool:
        """Return whether a physical slot contains the private empty sentinel."""
        self._check_index_type(index)
        if index < 0 or index >= self._capacity:
            raise IndexError("storage slot out of range.")
        return self._items[index] is _EMPTY

    def _resize(self, new_capacity: int) -> None:
        items: list[object] = [_EMPTY] * new_capacity
        for index in range(self._size):
            items[index] = self._items[index]
        self._items = items
        self._capacity = new_capacity

    def __iter__(self) -> Iterator[T]:
        for index in range(self._size):
            yield cast(T, self._items[index])

    def __len__(self) -> int:
        return self._size

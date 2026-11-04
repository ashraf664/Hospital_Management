"""A hash-based set composed from the custom hash table."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, TypeVar

from data_structures.hash_table import HashTable


T = TypeVar("T")


class CustomSet(Generic[T]):
    """Store unique hashable values using the project's HashTable.

    Add, remove, and contains are expected O(1), worst-case O(n). Union and
    intersection are expected O(n + m), subject to hash-table collisions.
    """

    def __init__(self) -> None:
        self._values: HashTable[T, bool] = HashTable()

    def add(self, value: T) -> bool:
        """Add value, returning True only when it was not already present."""
        if self.contains(value):
            return False
        self._values.set(value, True)
        return True

    def remove(self, value: T) -> None:
        """Remove value or raise KeyError when absent."""
        self._values.remove(value)

    def contains(self, value: T) -> bool:
        """Return whether value is in the set."""
        return self._values.contains(value)

    def union(self, other: CustomSet[T]) -> CustomSet[T]:
        """Return a new set containing members from both sets."""
        result = CustomSet[T]()
        for value in self:
            result.add(value)
        for value in other:
            result.add(value)
        return result

    def intersection(self, other: CustomSet[T]) -> CustomSet[T]:
        """Return a new set containing members common to both sets."""
        result = CustomSet[T]()
        smaller, larger = (
            (self, other) if self.size() <= other.size() else (other, self)
        )
        for value in smaller:
            if larger.contains(value):
                result.add(value)
        return result

    def size(self) -> int:
        """Return the number of unique values."""
        return self._values.size()

    def __iter__(self) -> Iterator[T]:
        return iter(self._values)

    def __len__(self) -> int:
        return self._values.size()

"""A max-priority queue implemented with a binary heap."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar, cast

from data_structures.dynamic_array import DynamicArray


T = TypeVar("T")
P = TypeVar("P")


@dataclass(frozen=True, slots=True)
class _HeapEntry(Generic[T, P]):
    item: T
    priority: P
    sequence: int


class PriorityQueue(Generic[T, P]):
    """Remove larger comparable priorities first; equal priorities are FIFO.

    This generic ordering is not a clinical triage policy. Enqueue and dequeue
    are O(log n), peek and size are O(1), and find scans in O(n).
    """

    def __init__(self) -> None:
        self._heap: DynamicArray[_HeapEntry[T, P]] = DynamicArray()
        self._next_sequence = 0

    def enqueue(self, item: T, priority: P) -> None:
        """Insert item using a larger-first priority ordering."""
        entry = _HeapEntry(item, priority, self._next_sequence)
        insertion_index = self._heap.size()
        while insertion_index > 0:
            parent_index = (insertion_index - 1) // 2
            parent = self._heap.get(parent_index)
            if self._comes_before(entry, parent):
                insertion_index = parent_index
            else:
                break

        self._heap.append(entry)
        index = self._heap.size() - 1
        while index > insertion_index:
            parent_index = (index - 1) // 2
            self._heap.set(index, self._heap.get(parent_index))
            index = parent_index
        self._heap.set(insertion_index, entry)
        self._next_sequence += 1

    def dequeue(self) -> T:
        """Remove and return the highest-priority item."""
        if self.is_empty():
            raise IndexError("dequeue from empty priority queue.")
        highest = self._heap.get(0)
        last = self._heap._pop_last()
        if not self.is_empty():
            self._heap.set(0, last)
            self._sift_down(0)
        return highest.item

    def peek(self) -> T:
        """Return the highest-priority item without removing it."""
        if self.is_empty():
            raise IndexError("peek from empty priority queue.")
        return self._heap.get(0).item

    def is_empty(self) -> bool:
        """Return whether the priority queue contains no items."""
        return self._heap.size() == 0

    def size(self) -> int:
        """Return the number of queued items."""
        return self._heap.size()

    def find(self, item: T) -> bool:
        """Return whether item exists, scanning the heap in O(n)."""
        for entry in self._heap:
            if entry.item == item:
                return True
        return False

    def _comes_before(self, first: _HeapEntry[T, P], second: _HeapEntry[T, P]) -> bool:
        if first.priority == second.priority:
            return first.sequence < second.sequence
        return cast(bool, first.priority > second.priority)

    def _sift_down(self, start: int) -> None:
        index = start
        size = self._heap.size()
        while True:
            left = 2 * index + 1
            right = left + 1
            highest = index
            if left < size and self._comes_before(
                self._heap.get(left), self._heap.get(highest)
            ):
                highest = left
            if right < size and self._comes_before(
                self._heap.get(right), self._heap.get(highest)
            ):
                highest = right
            if highest == index:
                return
            current = self._heap.get(index)
            self._heap.set(index, self._heap.get(highest))
            self._heap.set(highest, current)
            index = highest

    def __iter__(self) -> Iterator[T]:
        for entry in self._heap:
            yield entry.item

    def __len__(self) -> int:
        return self._heap.size()

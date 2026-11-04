"""A resizable separate-chaining hash table."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, TypeVar

from data_structures.dynamic_array import DynamicArray


K = TypeVar("K")
V = TypeVar("V")


class _Node(Generic[K, V]):
    """Linked entry stored in a hash bucket."""

    __slots__ = ("key", "value", "next")

    def __init__(
        self,
        key: K,
        value: V,
        next_node: _Node[K, V] | None = None,
    ) -> None:
        self.key = key
        self.value = value
        self.next = next_node


class HashTable(Generic[K, V]):
    """Map hashable keys to values using linked chains for collisions.

    Set, get, remove, and contains are expected O(1), worst-case O(n) under
    heavy collisions. Iterating over keys or entries is O(n).
    """

    def __init__(
        self,
        initial_capacity: int = 8,
        max_load_factor: float = 0.75,
    ) -> None:
        if initial_capacity < 1:
            raise ValueError("initial_capacity must be at least 1.")
        if not 0 < max_load_factor < 1:
            raise ValueError("max_load_factor must be between 0 and 1.")
        self._minimum_capacity = initial_capacity
        self._buckets: DynamicArray[_Node[K, V] | None] = DynamicArray(
            initial_capacity
        )
        self._capacity = initial_capacity
        self._size = 0
        self._max_load_factor = max_load_factor

    @property
    def capacity(self) -> int:
        """Return the number of allocated buckets."""
        return self._capacity

    def size(self) -> int:
        """Return the number of stored key/value pairs."""
        return self._size

    def set(self, key: K, value: V) -> None:
        """Insert a key or replace its existing value."""
        bucket_index = self._bucket_index(key)
        node = self._buckets._get_slot(bucket_index)
        while node is not None:
            if node.key == key:
                node.value = value
                return
            node = node.next

        if (self._size + 1) / self._capacity > self._max_load_factor:
            self._resize(self._capacity * 2)
            bucket_index = self._bucket_index(key)
        head = self._buckets._get_slot(bucket_index)
        self._buckets._set_slot(bucket_index, _Node(key, value, head))
        self._size += 1

    def put(self, key: K, value: V) -> None:
        """Alias for set(key, value), matching the SRS operation name."""
        self.set(key, value)

    def get(self, key: K) -> V:
        """Return a value or raise KeyError when its key is absent."""
        node = self._find_node(key)
        if node is None:
            raise KeyError(key)
        return node.value

    def remove(self, key: K) -> V:
        """Remove and return a value or raise KeyError when absent."""
        bucket_index = self._bucket_index(key)
        previous: _Node[K, V] | None = None
        node = self._buckets._get_slot(bucket_index)
        while node is not None:
            if node.key == key:
                if previous is None:
                    self._buckets._set_slot(bucket_index, node.next)
                else:
                    previous.next = node.next
                self._size -= 1
                if (
                    self._capacity > self._minimum_capacity
                    and self._size <= self._capacity // 4
                ):
                    self._resize(max(self._minimum_capacity, self._capacity // 2))
                return node.value
            previous = node
            node = node.next
        raise KeyError(key)

    def contains(self, key: K) -> bool:
        """Return whether key is present."""
        return self._find_node(key) is not None

    def _find_node(self, key: K) -> _Node[K, V] | None:
        node = self._buckets._get_slot(self._bucket_index(key))
        while node is not None:
            if node.key == key:
                return node
            node = node.next
        return None

    def _bucket_index(self, key: K) -> int:
        return hash(key) % self._capacity

    def _resize(self, new_capacity: int) -> None:
        old_buckets = self._buckets
        self._buckets = DynamicArray(new_capacity)
        self._capacity = new_capacity
        for index in range(old_buckets.capacity):
            node = old_buckets._get_slot(index)
            while node is not None:
                next_node = node.next
                bucket_index = self._bucket_index(node.key)
                head = self._buckets._get_slot(bucket_index)
                self._buckets._set_slot(
                    bucket_index,
                    _Node(node.key, node.value, head),
                )
                node = next_node

    def items(self) -> Iterator[tuple[K, V]]:
        """Yield all key/value pairs in bucket order."""
        for index in range(self._capacity):
            node = self._buckets._get_slot(index)
            while node is not None:
                yield node.key, node.value
                node = node.next

    def __iter__(self) -> Iterator[K]:
        for key, _ in self.items():
            yield key

    def __len__(self) -> int:
        return self._size

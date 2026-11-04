"""Tests for the custom separate-chaining hash table."""

import unittest

from data_structures import HashTable


class CollisionKey:
    def __init__(self, value: str) -> None:
        self.value = value

    def __hash__(self) -> int:
        return 7

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CollisionKey) and self.value == other.value


class HashTableTests(unittest.TestCase):
    def test_empty_state_and_missing_keys(self) -> None:
        table: HashTable[str, int] = HashTable()

        self.assertEqual(table.size(), 0)
        self.assertFalse(table.contains("absent"))
        with self.assertRaises(KeyError):
            table.get("absent")
        with self.assertRaises(KeyError):
            table.remove("absent")

    def test_set_get_update_remove_and_iteration(self) -> None:
        table: HashTable[str, int] = HashTable(initial_capacity=2)
        table.set("one", 1)
        table.put("two", 2)
        table.set("one", 10)

        self.assertGreaterEqual(table.capacity, 4)
        self.assertEqual(table.get("one"), 10)
        self.assertEqual(table.get("two"), 2)
        self.assertEqual(table.size(), 2)
        self.assertTrue(table.contains("one"))
        self.assertEqual(tuple(sorted(table)), ("one", "two"))
        self.assertEqual(
            tuple(sorted(table.items())),
            (("one", 10), ("two", 2)),
        )
        self.assertEqual(table.remove("one"), 10)
        self.assertFalse(table.contains("one"))
        self.assertEqual(table.size(), 1)

    def test_collisions_retain_independent_entries_and_remove_head_middle_tail(self) -> None:
        table: HashTable[CollisionKey, str] = HashTable(initial_capacity=8)
        keys = [CollisionKey(value) for value in ("tail", "middle", "head")]
        for key in keys:
            table.set(key, key.value)

        self.assertEqual(table.get(keys[0]), "tail")
        self.assertEqual(table.get(keys[1]), "middle")
        self.assertEqual(table.get(keys[2]), "head")
        self.assertEqual(table.remove(keys[2]), "head")
        self.assertEqual(table.size(), 2)
        self.assertEqual(table.get(keys[0]), "tail")
        self.assertEqual(table.get(keys[1]), "middle")
        self.assertEqual(table.remove(keys[1]), "middle")
        self.assertEqual(table.size(), 1)
        self.assertEqual(table.get(keys[0]), "tail")
        self.assertEqual(table.remove(keys[0]), "tail")
        self.assertEqual(table.size(), 0)
        self.assertEqual(len(tuple(table.items())), 0)

    def test_resize_after_growth_and_removals(self) -> None:
        table: HashTable[int, int] = HashTable(initial_capacity=2)
        for value in range(20):
            table.set(value, value)
            self.assertEqual(table.size(), value + 1)
            self.assertEqual(len(table), value + 1)
            self.assertEqual(len(tuple(table.items())), value + 1)
        expanded_capacity = table.capacity

        for remaining, value in zip(range(19, 0, -1), range(19)):
            self.assertEqual(table.remove(value), value)
            self.assertEqual(table.size(), remaining)
            self.assertEqual(len(table), remaining)
            self.assertEqual(len(tuple(table.items())), remaining)

        self.assertGreater(expanded_capacity, table.capacity)
        self.assertEqual(table.get(19), 19)
        self.assertEqual(table.size(), 1)

    def test_rehashing_preserves_each_colliding_key_once(self) -> None:
        table: HashTable[CollisionKey, int] = HashTable(initial_capacity=2)
        keys = [CollisionKey(str(value)) for value in range(40)]

        for expected_size, key in enumerate(keys, start=1):
            table.set(key, expected_size)
            self.assertEqual(table.size(), expected_size)

        entries = tuple(table.items())
        self.assertEqual(len(entries), len(keys))
        self.assertEqual(len(tuple(table)), len(keys))
        self.assertEqual(
            sorted(key.value for key in table),
            sorted(key.value for key in keys),
        )
        self.assertEqual(
            sorted(value for _, value in entries),
            list(range(1, len(keys) + 1)),
        )
        for index, key in enumerate(keys, start=1):
            self.assertEqual(table.get(key), index)

    def test_none_is_supported_as_key_and_value(self) -> None:
        table: HashTable[object | None, object | None] = HashTable()
        table.set(None, None)

        self.assertTrue(table.contains(None))
        self.assertIsNone(table.get(None))
        self.assertEqual(table.size(), 1)
        self.assertEqual(tuple(table.items()), ((None, None),))
        self.assertIsNone(table.remove(None))
        self.assertEqual(table.size(), 0)
        self.assertFalse(table.contains(None))

    def test_update_existing_key_does_not_increase_size(self) -> None:
        table: HashTable[str, int] = HashTable()
        table.set("existing", 1)
        table.set("existing", 2)

        self.assertEqual(table.get("existing"), 2)
        self.assertEqual(table.size(), 1)
        self.assertEqual(len(tuple(table.items())), 1)

    def test_missing_get_and_remove_raise_key_error(self) -> None:
        table: HashTable[str, int] = HashTable()

        with self.assertRaises(KeyError):
            table.get("missing")
        with self.assertRaises(KeyError):
            table.remove("missing")
        self.assertEqual(table.size(), 0)

    def test_invalid_configuration_and_unhashable_keys(self) -> None:
        with self.assertRaises(ValueError):
            HashTable(initial_capacity=0)
        with self.assertRaises(ValueError):
            HashTable(max_load_factor=1.0)
        table: HashTable[object, int] = HashTable()
        with self.assertRaises(TypeError):
            table.set([], 1)


if __name__ == "__main__":
    unittest.main()

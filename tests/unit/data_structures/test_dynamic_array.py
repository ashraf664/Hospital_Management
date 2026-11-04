"""Tests for the custom dynamic array."""

import unittest

from data_structures import DynamicArray


class DynamicArrayTests(unittest.TestCase):
    def test_empty_state_and_invalid_indexes(self) -> None:
        array: DynamicArray[int] = DynamicArray()

        self.assertEqual(array.size(), 0)
        self.assertEqual(array.capacity, 4)
        self.assertEqual(tuple(array), ())
        self.assertEqual(array.find(10), -1)
        with self.assertRaises(IndexError):
            array.get(0)
        with self.assertRaises(IndexError):
            array.set(0, 10)
        with self.assertRaises(IndexError):
            array.remove(0)
        with self.assertRaises(IndexError):
            array.insert(1, 10)

    def test_append_get_set_find_and_iteration(self) -> None:
        array: DynamicArray[object] = DynamicArray(initial_capacity=2)
        array.append("first")
        array.append(None)
        array.append("third")

        self.assertEqual(array.capacity, 4)
        self.assertEqual(array.get(0), "first")
        self.assertIsNone(array.get(1))
        self.assertEqual(array.find(None), 1)
        self.assertEqual(array.find("missing"), -1)
        array.set(1, "second")
        self.assertEqual(tuple(array), ("first", "second", "third"))

    def test_insert_and_remove_preserve_order_and_resize(self) -> None:
        array = DynamicArray[int](initial_capacity=2)
        array.append(1)
        array.append(3)
        array.insert(1, 2)
        array.insert(0, 0)
        self.assertEqual(tuple(array), (0, 1, 2, 3))
        self.assertEqual(array.capacity, 4)

        self.assertEqual(array.remove(0), 0)
        self.assertEqual(array.remove_at(1), 2)
        self.assertEqual(tuple(array), (1, 3))
        self.assertEqual(array.remove(1), 3)
        self.assertEqual(array.capacity, 2)

    def test_index_boundaries_and_initial_capacity(self) -> None:
        array = DynamicArray[int](initial_capacity=1)
        array.insert(0, 5)
        with self.assertRaises(IndexError):
            array.get(-1)
        with self.assertRaises(IndexError):
            array.set(1, 7)
        with self.assertRaises(IndexError):
            array.insert(-1, 8)
        with self.assertRaises(IndexError):
            array.insert(2, 8)
        with self.assertRaises(ValueError):
            DynamicArray(initial_capacity=0)

    def test_internal_slots_store_none_and_clear_to_empty_sentinel(self) -> None:
        array: DynamicArray[int | None] = DynamicArray(initial_capacity=2)

        self.assertTrue(array._is_slot_empty(0))
        self.assertIsNone(array._get_slot(0))

        array._set_slot(0, None)
        self.assertFalse(array._is_slot_empty(0))
        self.assertIsNone(array._get_slot(0))

        array._set_slot(0, 42)
        self.assertFalse(array._is_slot_empty(0))
        self.assertEqual(array._get_slot(0), 42)

        array._clear_slot(0)
        self.assertTrue(array._is_slot_empty(0))
        self.assertIsNone(array._get_slot(0))

    def test_none_remains_a_valid_value_in_public_array_operations(self) -> None:
        array: DynamicArray[int | None] = DynamicArray(initial_capacity=2)
        array.append(None)
        array.append(1)

        self.assertIsNone(array.get(0))
        array.set(1, None)
        self.assertIsNone(array.get(1))
        self.assertEqual(tuple(array), (None, None))
        self.assertIsNone(array.remove(0))
        self.assertEqual(tuple(array), (None,))

    def test_index_operations_reject_non_integer_indexes_with_type_error(self) -> None:
        array = DynamicArray[int]()
        array.append(10)

        for invalid_index in (1.5, "1", True):
            with self.subTest(index=invalid_index):
                with self.assertRaises(TypeError):
                    array.get(invalid_index)
                with self.assertRaises(TypeError):
                    array.set(invalid_index, 20)
                with self.assertRaises(TypeError):
                    array.insert(invalid_index, 20)
                with self.assertRaises(TypeError):
                    array.remove(invalid_index)
                with self.assertRaises(TypeError):
                    array.remove_at(invalid_index)

    def test_internal_slot_operations_reject_non_integer_indexes(self) -> None:
        array = DynamicArray[int]()

        for invalid_index in (1.5, "1", True):
            with self.subTest(index=invalid_index):
                with self.assertRaises(TypeError):
                    array._get_slot(invalid_index)
                with self.assertRaises(TypeError):
                    array._set_slot(invalid_index, 1)
                with self.assertRaises(TypeError):
                    array._clear_slot(invalid_index)
                with self.assertRaises(TypeError):
                    array._is_slot_empty(invalid_index)


if __name__ == "__main__":
    unittest.main()

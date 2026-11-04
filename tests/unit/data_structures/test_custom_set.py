"""Tests for the hash-table-backed custom set."""

import unittest

from data_structures import CustomSet


class CustomSetTests(unittest.TestCase):
    def test_add_prevents_duplicates_and_remove_reports_missing(self) -> None:
        values = CustomSet[str]()

        self.assertTrue(values.add("alpha"))
        self.assertFalse(values.add("alpha"))
        self.assertTrue(values.contains("alpha"))
        self.assertEqual(values.size(), 1)
        values.remove("alpha")
        self.assertFalse(values.contains("alpha"))
        with self.assertRaises(KeyError):
            values.remove("alpha")

    def test_union_and_intersection_do_not_mutate_inputs(self) -> None:
        first = CustomSet[int]()
        second = CustomSet[int]()
        for value in (1, 2, 3):
            first.add(value)
        for value in (3, 4):
            second.add(value)

        combined = first.union(second)
        common = first.intersection(second)

        self.assertEqual(tuple(sorted(combined)), (1, 2, 3, 4))
        self.assertEqual(tuple(common), (3,))
        self.assertEqual(first.size(), 3)
        self.assertEqual(second.size(), 2)

    def test_empty_operations_and_unhashable_values(self) -> None:
        values: CustomSet[object] = CustomSet()
        empty: CustomSet[object] = CustomSet()

        self.assertFalse(values.contains("absent"))
        self.assertEqual(values.union(empty).size(), 0)
        self.assertEqual(values.intersection(empty).size(), 0)
        with self.assertRaises(TypeError):
            values.add([])


if __name__ == "__main__":
    unittest.main()

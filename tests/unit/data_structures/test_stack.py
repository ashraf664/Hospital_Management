"""Tests for the custom LIFO stack."""

import unittest

from data_structures import Stack


class StackTests(unittest.TestCase):
    def test_empty_state_errors_and_none_value(self) -> None:
        stack: Stack[int | None] = Stack()

        self.assertTrue(stack.is_empty())
        self.assertEqual(stack.size(), 0)
        with self.assertRaises(IndexError):
            stack.pop()
        with self.assertRaises(IndexError):
            stack.peek()

        stack.push(None)
        self.assertIsNone(stack.peek())
        self.assertIsNone(stack.pop())
        self.assertTrue(stack.is_empty())

    def test_lifo_order_find_and_growth(self) -> None:
        stack = Stack[int](initial_capacity=1)
        stack.push(1)
        stack.push(2)
        stack.push(3)

        self.assertEqual(stack.size(), 3)
        self.assertEqual(stack.peek(), 3)
        self.assertTrue(stack.find(1))
        self.assertFalse(stack.find(9))
        self.assertEqual((stack.pop(), stack.pop(), stack.pop()), (3, 2, 1))
        self.assertTrue(stack.is_empty())

    def test_invalid_initial_capacity(self) -> None:
        with self.assertRaises(ValueError):
            Stack(initial_capacity=0)


if __name__ == "__main__":
    unittest.main()

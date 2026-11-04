"""Tests for the custom circular FIFO queue."""

import unittest

from data_structures import Queue


class QueueTests(unittest.TestCase):
    def test_empty_state_and_empty_operations_raise_index_error(self) -> None:
        queue: Queue[int] = Queue()

        self.assertTrue(queue.is_empty())
        self.assertEqual(queue.size(), 0)
        with self.assertRaises(IndexError):
            queue.dequeue()
        with self.assertRaises(IndexError):
            queue.peek()

    def test_none_is_a_regular_queue_value(self) -> None:
        queue: Queue[int | None] = Queue()
        queue.enqueue(None)
        self.assertTrue(queue.find(None))
        self.assertIsNone(queue.peek())
        self.assertEqual(queue.size(), 1)
        self.assertIsNone(queue.dequeue())
        self.assertFalse(queue.find(None))
        self.assertTrue(queue.is_empty())

    def test_circular_buffer_wraps_after_dequeue_and_enqueue(self) -> None:
        queue: Queue[int] = Queue(initial_capacity=3)
        queue.enqueue(1)
        queue.enqueue(2)
        self.assertEqual(queue.dequeue(), 1)
        queue.enqueue(3)
        queue.enqueue(4)

        self.assertEqual(queue.capacity, 3)
        self.assertEqual(tuple(queue), (2, 3, 4))
        self.assertEqual((queue.dequeue(), queue.dequeue(), queue.dequeue()), (2, 3, 4))
        self.assertTrue(queue.is_empty())

    def test_resize_when_head_is_in_middle_preserves_fifo_and_none(self) -> None:
        queue: Queue[int | None] = Queue(initial_capacity=4)
        queue.enqueue(None)
        queue.enqueue(1)
        queue.enqueue(2)
        queue.enqueue(3)
        self.assertIsNone(queue.dequeue())
        self.assertEqual(queue.dequeue(), 1)
        queue.enqueue(4)
        queue.enqueue(None)

        self.assertEqual(queue.capacity, 4)
        self.assertEqual(queue._head, 2)
        queue.enqueue(5)

        self.assertEqual(queue.capacity, 8)
        self.assertEqual(queue._head, 0)
        self.assertEqual(tuple(queue), (2, 3, 4, None, 5))
        self.assertEqual(queue.peek(), 2)
        self.assertTrue(queue.find(None))
        self.assertEqual(
            (
                queue.dequeue(),
                queue.dequeue(),
                queue.dequeue(),
                queue.dequeue(),
                queue.dequeue(),
            ),
            (2, 3, 4, None, 5),
        )
        self.assertTrue(queue.is_empty())

    def test_fifo_order_survives_multiple_wraparounds(self) -> None:
        queue: Queue[int] = Queue(initial_capacity=3)
        expected = [0, 1, 2]
        for value in expected:
            queue.enqueue(value)

        self.assertEqual(queue.dequeue(), 0)
        expected.pop(0)
        queue.enqueue(3)
        expected.append(3)
        self.assertEqual(queue.dequeue(), 1)
        expected.pop(0)
        queue.enqueue(4)
        expected.append(4)
        self.assertEqual(queue.dequeue(), 2)
        expected.pop(0)
        queue.enqueue(5)
        expected.append(5)

        self.assertEqual(tuple(queue), tuple(expected))
        while expected:
            self.assertEqual(queue.dequeue(), expected.pop(0))
            self.assertEqual(tuple(queue), tuple(expected))
        self.assertTrue(queue.is_empty())

    def test_find_and_invalid_capacity(self) -> None:
        queue = Queue[str]()
        queue.enqueue("oldest")
        queue.enqueue("newest")
        self.assertTrue(queue.find("oldest"))
        self.assertFalse(queue.find("missing"))
        with self.assertRaises(ValueError):
            Queue(initial_capacity=0)


if __name__ == "__main__":
    unittest.main()

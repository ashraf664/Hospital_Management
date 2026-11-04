"""Tests for the binary-heap max-priority queue."""

import unittest

from data_structures import PriorityQueue


class PriorityQueueTests(unittest.TestCase):
    def test_empty_state_errors_and_single_item(self) -> None:
        queue: PriorityQueue[str, int] = PriorityQueue()

        self.assertTrue(queue.is_empty())
        self.assertEqual(queue.size(), 0)
        with self.assertRaises(IndexError):
            queue.peek()
        with self.assertRaises(IndexError):
            queue.dequeue()

        queue.enqueue("only", 5)
        self.assertEqual(queue.peek(), "only")
        self.assertEqual(queue.dequeue(), "only")
        self.assertTrue(queue.is_empty())

    def test_max_heap_order_and_resize(self) -> None:
        queue: PriorityQueue[str, int] = PriorityQueue()
        for item, priority in (
            ("low", 1),
            ("high", 10),
            ("middle", 5),
            ("highest", 20),
        ):
            queue.enqueue(item, priority)

        self.assertEqual(queue.size(), 4)
        self.assertEqual(queue.peek(), "highest")
        self.assertTrue(queue.find("low"))
        self.assertFalse(queue.find("missing"))
        self.assertEqual(
            (queue.dequeue(), queue.dequeue(), queue.dequeue(), queue.dequeue()),
            ("highest", "high", "middle", "low"),
        )

    def test_equal_priorities_are_dequeued_fifo(self) -> None:
        queue: PriorityQueue[str, int] = PriorityQueue()
        queue.enqueue("first", 3)
        queue.enqueue("second", 3)
        queue.enqueue("third", 3)

        self.assertEqual(
            (queue.dequeue(), queue.dequeue(), queue.dequeue()),
            ("first", "second", "third"),
        )

    def test_zero_and_negative_priorities_are_ordered_largest_first(self) -> None:
        queue: PriorityQueue[str, int] = PriorityQueue()
        for item, priority in (
            ("negative-two", -2),
            ("zero", 0),
            ("negative-five", -5),
            ("positive", 4),
        ):
            queue.enqueue(item, priority)

        self.assertEqual(
            [queue.dequeue() for _ in range(4)],
            ["positive", "zero", "negative-two", "negative-five"],
        )

    def test_peek_does_not_remove_highest_priority_item(self) -> None:
        queue: PriorityQueue[str, int] = PriorityQueue()
        queue.enqueue("highest", 10)
        queue.enqueue("lower", 2)

        self.assertEqual(queue.peek(), "highest")
        self.assertEqual(queue.size(), 2)
        self.assertEqual(queue.peek(), "highest")
        self.assertEqual(queue.dequeue(), "highest")
        self.assertEqual(queue.size(), 1)

    def test_repeated_heapify_up_and_down_preserve_priority_order(self) -> None:
        queue: PriorityQueue[str, int] = PriorityQueue()
        initial_entries = (
            ("four", 4),
            ("ten", 10),
            ("three", 3),
            ("twelve", 12),
            ("eight", 8),
            ("two", 2),
            ("eleven", 11),
            ("one", 1),
            ("seven", 7),
            ("nine", 9),
        )
        for item, priority in initial_entries:
            queue.enqueue(item, priority)

        self.assertEqual(queue.dequeue(), "twelve")
        self.assertEqual(queue.dequeue(), "eleven")
        queue.enqueue("thirteen", 13)
        queue.enqueue("six", 6)
        self.assertEqual(queue.dequeue(), "thirteen")
        queue.enqueue("fifteen", 15)

        self.assertEqual(
            [queue.dequeue() for _ in range(queue.size())],
            [
                "fifteen",
                "ten",
                "nine",
                "eight",
                "seven",
                "six",
                "four",
                "three",
                "two",
                "one",
            ],
        )
        self.assertTrue(queue.is_empty())

    def test_duplicate_items_can_be_dequeued_once_per_enqueue(self) -> None:
        queue: PriorityQueue[str, int] = PriorityQueue()
        queue.enqueue("repeat", 2)
        queue.enqueue("repeat", 8)
        queue.enqueue("other", 5)
        queue.enqueue("repeat", 2)

        self.assertEqual(queue.size(), 4)
        self.assertTrue(queue.find("repeat"))
        self.assertEqual(
            [queue.dequeue() for _ in range(4)],
            ["repeat", "other", "repeat", "repeat"],
        )
        self.assertFalse(queue.find("repeat"))

    def test_consecutive_dequeues_keep_remaining_heap_order(self) -> None:
        queue: PriorityQueue[str, int] = PriorityQueue()
        for item, priority in (
            ("first", 6),
            ("second", 15),
            ("third", 3),
            ("fourth", 12),
            ("fifth", 9),
            ("sixth", 1),
        ):
            queue.enqueue(item, priority)

        self.assertEqual(queue.dequeue(), "second")
        self.assertEqual(queue.dequeue(), "fourth")
        self.assertEqual(queue.dequeue(), "fifth")
        self.assertEqual(
            [queue.dequeue() for _ in range(queue.size())],
            ["first", "third", "sixth"],
        )

    def test_incomparable_priority_does_not_mutate_queue(self) -> None:
        queue: PriorityQueue[str, int | str] = PriorityQueue()
        queue.enqueue("numeric", 3)

        with self.assertRaises(TypeError):
            queue.enqueue("text", "high")

        self.assertEqual(queue.size(), 1)
        self.assertEqual(queue.peek(), "numeric")


if __name__ == "__main__":
    unittest.main()

"""Bounded, deterministically ordered repository results."""

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from data_structures import DynamicArray


T = TypeVar("T")

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200


@dataclass(slots=True)
class Page(Generic[T]):
    """A single page of results and the matching total result count."""

    items: DynamicArray[T] = field(default_factory=DynamicArray)
    total_count: int = 0
    limit: int = DEFAULT_PAGE_LIMIT
    offset: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.items, DynamicArray):
            raise TypeError("items must be a DynamicArray.")
        if type(self.total_count) is not int or self.total_count < 0:
            raise ValueError("total_count must be a non-negative integer.")
        if type(self.limit) is not int:
            raise TypeError("limit must be an integer.")
        if not 1 <= self.limit <= MAX_PAGE_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {MAX_PAGE_LIMIT}."
            )
        if type(self.offset) is not int:
            raise TypeError("offset must be an integer.")
        if self.offset < 0:
            raise ValueError("offset must be non-negative.")
        if len(self.items) > self.limit:
            raise ValueError("items cannot contain more entries than limit.")
        if len(self.items) > self.total_count:
            raise ValueError("items cannot exceed total_count.")

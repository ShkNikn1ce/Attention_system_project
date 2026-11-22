"""Измерение времени прохождения таблиц."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from attention_system.markup import stereotype


@stereotype("интерфейс")
class Clock(ABC):
    @abstractmethod
    def start_clock(self) -> None:
        """Запускает отсчёт времени."""

    @abstractmethod
    def stop(self) -> float:
        """Останавливает отсчёт и возвращает время в секундах."""


@stereotype("граничный")
class SystemClock(Clock):
    def __init__(self) -> None:
        self._started: float = 0.0

    def start_clock(self) -> None:
        self._started = time.perf_counter()

    def stop(self) -> float:
        return time.perf_counter() - self._started


@stereotype("граничный")
class ScriptedClock(Clock):
    """Возвращает заранее заданные значения времени: для демонстрации и автоматических тестов."""

    def __init__(self, values: list[float]) -> None:
        self._scripted: list[float] = list(values)

    def start_clock(self) -> None:
        return None

    def stop(self) -> float:
        return self._scripted.pop(0)

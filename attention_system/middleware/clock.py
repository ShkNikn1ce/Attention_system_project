"""Измерение времени прохождения таблиц."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from attention_system.markup import стереотип


@стереотип("интерфейс")
class Секундомер(ABC):
    @abstractmethod
    def начать(self) -> None:
        """Запускает отсчёт времени."""

    @abstractmethod
    def остановить(self) -> float:
        """Останавливает отсчёт и возвращает время в секундах."""


@стереотип("граничный")
class СекундомерСистемный(Секундомер):
    def __init__(self) -> None:
        self._старт: float = 0.0

    def начать(self) -> None:
        self._старт = time.perf_counter()

    def остановить(self) -> float:
        return time.perf_counter() - self._старт


@стереотип("граничный")
class СекундомерПоСценарию(Секундомер):
    """Возвращает заранее заданные значения времени: для демонстрации и автоматических тестов."""

    def __init__(self, значения: list[float]) -> None:
        self._значения: list[float] = list(значения)

    def начать(self) -> None:
        return None

    def остановить(self) -> float:
        return self._значения.pop(0)

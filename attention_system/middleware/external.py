"""Интерфейсы с внешними системами: уведомления пилотов и служба безопасности полётов."""
from __future__ import annotations

from abc import ABC, abstractmethod

from attention_system.business.entities import (
    Conclusion, Pilot, SummaryReport, TestSession)
from attention_system.markup import stereotype


@stereotype("интерфейс")
class Notifier(ABC):
    @abstractmethod
    def notify(self, pilot: Pilot, session: TestSession) -> None:
        """Сообщает пилоту о назначенной сессии тестирования."""


@stereotype("граничный")
class MemoryNotifier(Notifier):
    def __init__(self) -> None:
        self.log: list[str] = []

    def notify(self, pilot: Pilot, session: TestSession) -> None:
        self.log.append(
            f"{pilot.full_name}: назначена {session.check_type.value} проверка на {session.occurred_at:%Y-%m-%d %H:%M}")


@stereotype("интерфейс")
class SafetyService(ABC):
    @abstractmethod
    def hand_conclusion(self, conclusion: Conclusion) -> None:
        """Передаёт заключение о допуске в службу безопасности полётов."""

    @abstractmethod
    def hand_report(self, report: SummaryReport) -> None:
        """Передаёт сводный отчёт в службу безопасности полётов."""


@stereotype("граничный")
class MemorySafetyService(SafetyService):
    def __init__(self) -> None:
        self.conclusions: list[Conclusion] = []
        self.reports: list[SummaryReport] = []

    def hand_conclusion(self, conclusion: Conclusion) -> None:
        self.conclusions.append(conclusion)

    def hand_report(self, report: SummaryReport) -> None:
        self.reports.append(report)

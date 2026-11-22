"""Перечисления предметной области."""
from enum import Enum


class Role(Enum):
    PILOT = "pilot"
    PSYCHOLOGIST = "psychologist"
    ADMINISTRATOR = "admin"

    def label(self) -> str:
        return {"pilot": "пилот", "psychologist": "авиационный психолог",
                "admin": "администратор системы"}[self.value]


class CheckType(Enum):
    PLANNED = "плановая"
    PERIODIC = "периодическая"
    PREFLIGHT = "предполётная"


class SessionStatus(Enum):
    ASSIGNED = "назначена"
    COMPLETED = "завершена"
    CANCELLED = "отменена"


class NumberOrder(Enum):
    ORDERED = "по порядку"
    SHUFFLED = "вперемешку"


class Decision(Enum):
    FIT = "годен"
    FIT_LIMITED = "годен с ограничением"
    EXTRA_EXAM = "направлен на дополнительное обследование"

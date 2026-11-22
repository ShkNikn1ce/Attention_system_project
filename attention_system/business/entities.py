"""Классы-сущности предметной области (бизнес-уровень)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from attention_system.business.calculations import SchulteMath
from attention_system.business.enums import (
    NumberOrder, Decision, Role, SessionStatus, CheckType)
from attention_system.business.errors import DataError, StateError
from attention_system.markup import stereotype
from attention_system.middleware.password import PasswordHash


@stereotype("сущность")
@dataclass(kw_only=True)
class User:
    """Учётная запись пользователя системы."""
    login: str
    password_hash: str
    role: Role
    last_login: Optional[datetime] = None
    pk: Optional[int] = None

    def check_password(self, password: str) -> bool:
        return PasswordHash.verify(password, self.password_hash)

    def resolve_role(self) -> Role:
        return self.role

    def mark_login(self, moment: datetime) -> None:
        self.last_login = moment


@stereotype("сущность")
@dataclass(kw_only=True)
class Pilot(User):
    """Пилот авиакомпании (подкласс пользователя)."""
    role: Role = Role.PILOT
    full_name: str
    employee_number: str
    position: str = ""


@stereotype("сущность")
@dataclass(kw_only=True)
class Psychologist(User):
    role: Role = Role.PSYCHOLOGIST
    full_name: str


@stereotype("сущность")
@dataclass(kw_only=True)
class Administrator(User):
    role: Role = Role.ADMINISTRATOR
    full_name: str


@stereotype("сущность")
@dataclass(kw_only=True)
class TestSession:
    """Одно прохождение пилотом комплекта из пяти таблиц Шульте.
    Объект зависит от состояния: назначена -> завершена | отменена."""
    pilot_id: int
    psychologist_id: int
    occurred_at: datetime
    check_type: CheckType
    method: str = "Шульте"
    status: SessionStatus = SessionStatus.ASSIGNED
    pk: Optional[int] = None

    def is_assigned(self) -> bool:
        return self.status == SessionStatus.ASSIGNED

    def complete(self) -> None:
        self.__move(SessionStatus.COMPLETED)

    def cancel(self) -> None:
        self.__move(SessionStatus.CANCELLED)

    def __move(self, is_new: SessionStatus) -> None:
        if self.status != SessionStatus.ASSIGNED:
            raise StateError(
                f"Сессия в состоянии «{self.status.value}» не может стать «{is_new.value}»")
        self.status = is_new


@stereotype("сущность")
@dataclass(kw_only=True)
class SchulteTable:
    """Таблица n×n с числами от 1 до n²."""
    session_id: int
    order_no: int
    size: int
    number_order: NumberOrder
    time_sec: Optional[float] = None
    numbers: list[int] = field(default_factory=list)
    pk: Optional[int] = None

    def generate_numbers(self, rng: Optional[random.Random] = None) -> list[int]:
        if self.size < 2:
            raise DataError("Размер таблицы должен быть не меньше 2")
        numbers = list(range(1, self.size ** 2 + 1))
        if self.number_order == NumberOrder.SHUFFLED:
            (rng or random.Random()).shuffle(numbers)
        self.numbers = numbers
        return numbers

    def record_time(self, seconds: float) -> None:
        if seconds <= 0:
            raise DataError("Время прохождения должно быть положительным")
        self.time_sec = seconds


@stereotype("сущность")
@dataclass(kw_only=True)
class TestResult:
    """Расчётные показатели сессии: ЭР, ВР, ПУ."""
    session_id: int
    er: float = 0.0
    vr: float = 0.0
    pu: float = 0.0
    pk: Optional[int] = None

    def calculate_metrics(self, times: list[float]) -> None:
        self.er, self.vr, self.pu = SchulteMath.calculate(times)


@stereotype("сущность")
@dataclass(kw_only=True)
class AdmissionNorm:
    """Допустимые диапазоны показателей, при которых пилот годен к полётам."""
    er_min: float
    er_max: float
    vr_min: float
    vr_max: float
    pu_min: float
    pu_max: float
    pk: Optional[int] = None

    def check_ranges(self) -> None:
        for title, low, high in (("ЭР", self.er_min, self.er_max),
                                           ("ВР", self.vr_min, self.vr_max),
                                           ("ПУ", self.pu_min, self.pu_max)):
            if low > high:
                raise DataError(f"Диапазон {title}: нижняя граница больше верхней")

    def matches(self, result: TestResult) -> bool:
        return (self.er_min <= result.er <= self.er_max
                and self.vr_min <= result.vr <= self.vr_max
                and self.pu_min <= result.pu <= self.pu_max)


@stereotype("сущность")
@dataclass(kw_only=True)
class Conclusion:
    result_id: int
    psychologist_id: int
    norm_id: int
    decision: Decision
    on_date: date
    comment: str = ""
    pk: Optional[int] = None


@stereotype("структура данных")
@dataclass(kw_only=True)
class ReportLine:
    pilot_id: int
    full_name: str
    session_count: int
    avg_er: float
    avg_vr: float
    avg_pu: float


@stereotype("сущность")
@dataclass(kw_only=True)
class SummaryReport:
    admin_id: int
    period_start: date
    period_end: date
    created_at: datetime
    lines: list[ReportLine] = field(default_factory=list)
    pk: Optional[int] = None

    def add_line(self, row: ReportLine) -> None:
        self.lines.append(row)

    def pilot_ids(self) -> list[int]:
        return [s.pilot_id for s in self.lines]

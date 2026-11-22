"""Управляющие классы: по одному на вариант использования."""
from __future__ import annotations

import random
import threading
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from attention_system.business.entities import (
    Conclusion, AdmissionNorm, Pilot, TestResult, SummaryReport, TestSession,
    SchulteTable)
from attention_system.business.enums import (
    NumberOrder, Decision, Role, SessionStatus, CheckType)
from attention_system.business.errors import (
    LockoutError, LoginError, DataError, AccessError, StateError, NotFoundError)
from attention_system.business.calculations import SchulteMath
from attention_system.business.services import (
    DynamicsAnalysis, DynamicsChart, SessionDetails, Admission, SuggestedConclusion, ReportService)
from attention_system.markup import stereotype
from attention_system.middleware.external import SafetyService, Notifier
from attention_system.middleware.password import PasswordHash
from attention_system.middleware.security import Access, WorkSession
from attention_system.middleware.storage import Storage


@stereotype("управляющий")
class AuthController:
    """Прецедент 1. Войти в систему."""

    def __init__(self, storage: Storage, max_attempts: int = 3) -> None:
        self._storage: Storage = storage
        self._max_attempts: int = max_attempts
        self._attempts: dict[str, int] = {}
        self._lock: threading.Lock = threading.Lock()

    def authenticate(self, login: str, password: str) -> WorkSession:
        with self._lock:
            if self._attempts.get(login, 0) >= self._max_attempts:
                raise LockoutError("Превышено число попыток входа")
        user = self._storage.user_by_login(login)
        if user is None or not user.check_password(password):
            with self._lock:
                self._attempts[login] = self._attempts.get(login, 0) + 1
            raise LoginError("Неверный логин или пароль")
        with self._lock:
            self._attempts.pop(login, None)
        moment = datetime.now()
        user.mark_login(moment)
        self._storage.mark_login(user.pk, moment)
        return WorkSession(user, moment)


@stereotype("управляющий")
class TestingController:
    """Прецедент 2. Пройти тестирование по методике Шульте."""

    def __init__(self, storage: Storage, work: WorkSession,
                 rng: Optional[random.Random] = None) -> None:
        Access.require(work, Role.PILOT)
        self._storage: Storage = storage
        self._session_user: WorkSession = work
        self._rng: Optional[random.Random] = rng

    def start_testing(self) -> TestSession:
        session = self._storage.assigned_session(self._session_user.user.pk)
        if session is None:
            raise NotFoundError("Для вас не назначено тестирование")
        return session

    def create_table(self, session: TestSession, order: int, size: int = 3,
                       layout: NumberOrder = NumberOrder.ORDERED) -> SchulteTable:
        table = SchulteTable(session_id=session.pk, order_no=order, size=size,
                                number_order=layout)
        table.generate_numbers(self._rng)
        return table

    def record_time(self, table: SchulteTable, seconds: float) -> None:
        table.record_time(seconds)
        self._storage.create_table(table)

    def finish_testing(self, session: TestSession,
                              tables: list[SchulteTable]) -> TestResult:
        result = TestResult(session_id=session.pk)
        result.calculate_metrics([t.time_sec for t in tables])
        session.complete()
        self._storage.save_result(session, result)
        return result

    def cancel_testing(self, session: TestSession) -> None:
        session.cancel()
        self._storage.save_session(session)
        self._storage.delete_tables(session.pk)


@stereotype("управляющий")
class OwnResultsController:
    """Прецедент 3. Просмотреть свои результаты."""

    def __init__(self, storage: Storage, work: WorkSession) -> None:
        Access.require(work, Role.PILOT)
        self._storage: Storage = storage
        self._session_user: WorkSession = work

    def completed_sessions(self) -> list[TestSession]:
        sessions = self._storage.sessions_of(self._session_user.user.pk, SessionStatus.COMPLETED)
        if not sessions:
            raise NotFoundError("Сохранённых результатов нет")
        return sessions

    def metrics_of(self, session_id: int) -> TestResult:
        session = self._storage.session_by_id(session_id)
        if session is None or session.pilot_id != self._session_user.user.pk:
            raise AccessError("Можно просматривать только свои результаты")
        result = self._storage.result_of(session_id)
        if result is None:
            raise NotFoundError("Результат сессии отсутствует")
        return result


@stereotype("управляющий")
class AssignmentController:
    """Прецедент 4. Назначить тестирование пилоту."""

    def __init__(self, storage: Storage, work: WorkSession, notifier: Notifier) -> None:
        Access.require(work, Role.PSYCHOLOGIST)
        self._storage: Storage = storage
        self._session_user: WorkSession = work
        self._notifier: Notifier = notifier

    def all_pilots(self) -> list[Pilot]:
        pilots = self._storage.all_pilots()
        if not pilots:
            raise NotFoundError("Пилоты в базе не найдены")
        return pilots

    def assign_test(self, pilot_id: int, format_type: CheckType,
                              moment: Optional[datetime] = None) -> TestSession:
        pilot = self._storage.pilot_by_id(pilot_id)
        if pilot is None:
            raise NotFoundError("Пилот не найден в базе")
        session = TestSession(pilot_id=pilot.pk, psychologist_id=self._session_user.user.pk,
                                    occurred_at=moment or datetime.now(), check_type=format_type)
        self._storage.create_session(session)
        self._notifier.notify(pilot, session)
        return session


@stereotype("управляющий")
class ReviewController:
    """Прецедент 5. Просмотреть результаты тестирования."""

    def __init__(self, storage: Storage, work: WorkSession) -> None:
        Access.require(work, Role.PSYCHOLOGIST)
        self._storage: Storage = storage

    def completed_sessions(self, pilot_id: int) -> list[TestSession]:
        sessions = self._storage.sessions_of(pilot_id, SessionStatus.COMPLETED)
        if not sessions:
            raise NotFoundError("У пилота нет завершённых сессий")
        return sessions

    def session_details(self, session_id: int) -> SessionDetails:
        session = self._storage.session_by_id(session_id)
        result = self._storage.result_of(session_id)
        if session is None or result is None:
            raise NotFoundError("Результат сессии отсутствует")
        tables = self._storage.tables_of(session_id)
        return SessionDetails(session=session, tables=tables, result=result)


@stereotype("управляющий")
class ConclusionController:
    """Прецедент 6. Сформировать заключение о допуске."""

    def __init__(self, storage: Storage, work: WorkSession, safety: SafetyService) -> None:
        Access.require(work, Role.PSYCHOLOGIST)
        self._storage: Storage = storage
        self._session_user: WorkSession = work
        self._safety: SafetyService = safety

    def suggest_conclusion(self, session_id: int) -> SuggestedConclusion:
        result = self._storage.result_of(session_id)
        if result is None:
            raise NotFoundError("Для сессии нет результата тестирования")
        norm = self._storage.current_norm_row()
        if norm is None:
            raise NotFoundError("Нормы допуска не заданы")
        decision = Admission.suggest(result, norm)
        return SuggestedConclusion(result=result, norm=norm, decision=decision,
                                         within_norm=decision == Decision.FIT)

    def save_conclusion(self, draft: SuggestedConclusion,
                            decision: Optional[Decision] = None,
                            comment: str = "") -> Conclusion:
        conclusion = Conclusion(
            result_id=draft.result.pk, psychologist_id=self._session_user.user.pk,
            norm_id=draft.norm.pk, decision=decision or draft.decision,
            on_date=date.today(), comment=comment)
        self._storage.create_conclusion(conclusion)
        self._safety.hand_conclusion(conclusion)
        return conclusion


@stereotype("управляющий")
class DynamicsController:
    """Прецедент 7. Отслеживать динамику результатов."""

    def __init__(self, storage: Storage, work: WorkSession) -> None:
        Access.require(work, Role.PSYCHOLOGIST)
        self._storage: Storage = storage

    def load_dynamics(self, pilot_id: int) -> DynamicsChart:
        if self._storage.pilot_by_id(pilot_id) is None:
            raise NotFoundError("Пилот не найден в базе")
        pairs = self._storage.results_of_pilot(pilot_id)
        if len(pairs) < 2:
            raise NotFoundError("Недостаточно данных: нужно не менее двух завершённых сессий")
        return DynamicsAnalysis.build(pairs)


@dataclass(kw_only=True)
@stereotype("структура данных")
class PilotData:
    login: str
    password: str
    full_name: str
    employee_number: str
    position: str = ""


@stereotype("управляющий")
class PilotAdminController:
    """Прецедент 8. Вести данные о пилотах."""

    MIN_PASSWORD_LENGTH = 6

    def __init__(self, storage: Storage, work: WorkSession) -> None:
        Access.require(work, Role.ADMINISTRATOR)
        self._storage: Storage = storage

    def all_pilots(self) -> list[Pilot]:
        return self._storage.all_pilots()

    def validate(self, payload: PilotData, is_new: bool = True) -> None:
        if not (payload.login.strip() and payload.full_name.strip() and payload.employee_number.strip()):
            raise DataError("Логин, ФИО и табельный номер обязательны")
        if is_new and len(payload.password) < self.MIN_PASSWORD_LENGTH:
            raise DataError(f"Пароль должен содержать не менее {self.MIN_PASSWORD_LENGTH} символов")

    def add_pilot(self, payload: PilotData) -> Pilot:
        self.validate(payload, is_new=True)
        pilot = Pilot(login=payload.login, password_hash=PasswordHash.make(payload.password), full_name=payload.full_name,
                      employee_number=payload.employee_number, position=payload.position)
        self._storage.create_pilot(pilot)
        return pilot

    def update_pilot(self, pilot_id: int, payload: PilotData) -> Pilot:
        self.validate(payload, is_new=False)
        pilot = self._storage.pilot_by_id(pilot_id)
        if pilot is None:
            raise NotFoundError("Пилот не найден в базе")
        pilot.login, pilot.full_name = payload.login, payload.full_name
        pilot.employee_number, pilot.position = payload.employee_number, payload.position
        if payload.password:
            pilot.password_hash = PasswordHash.make(payload.password)
        self._storage.save_pilot(pilot)
        return pilot

    def delete_pilot(self, pilot_id: int) -> None:
        if self._storage.sessions_of(pilot_id):
            raise StateError("Нельзя удалить пилота: у него есть сессии тестирования")
        self._storage.delete_pilot(pilot_id)


@stereotype("управляющий")
class NormController:
    """Прецедент 9. Настраивать нормы допуска."""

    def __init__(self, storage: Storage, work: WorkSession) -> None:
        Access.require(work, Role.ADMINISTRATOR)
        self._storage: Storage = storage

    def current_norms(self) -> AdmissionNorm:
        norm = self._storage.current_norm_row()
        if norm is None:
            raise NotFoundError("Нормы допуска ещё не заданы")
        return norm

    def save_norms(self, values: AdmissionNorm) -> AdmissionNorm:
        values.check_ranges()
        current_norm = self._storage.current_norm_row()
        if current_norm is None or self._storage.norm_is_used(current_norm.pk):
            values.pk = None
            self._storage.create_norm(values)
        else:
            values.pk = current_norm.pk
            self._storage.update_norm(values)
        return values


@stereotype("управляющий")
class ReportController:
    """Прецедент 10. Формировать сводный отчёт."""

    def __init__(self, storage: Storage, work: WorkSession, safety: SafetyService) -> None:
        Access.require(work, Role.ADMINISTRATOR)
        self._storage: Storage = storage
        self._session_user: WorkSession = work
        self._safety: SafetyService = safety

    def build_report(self, start: date, end: date, pilot_ids: list[int]) -> SummaryReport:
        if start > end:
            raise DataError("Начало периода позже его конца")
        pilots = self._storage.pilots_in(pilot_ids)
        payload = self._storage.results_between(pilot_ids, start, end)
        if not payload:
            raise NotFoundError("Нет данных за указанный период")
        report = ReportService.aggregate(pilots, payload, self._session_user.user.pk, start, end)
        self._storage.create_report(report)
        self._safety.hand_report(report)
        return report

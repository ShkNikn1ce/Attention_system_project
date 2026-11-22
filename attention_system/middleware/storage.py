"""Хранилище данных: интерфейс подсистемы и реализация на SQLite (реляционная БД)."""
from __future__ import annotations

import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional

from attention_system.business.entities import (
    Administrator, Psychologist, Conclusion, AdmissionNorm, Pilot, User,
    TestResult, SummaryReport, TestSession, SchulteTable)
from attention_system.business.enums import (
    NumberOrder, Decision, Role, SessionStatus, CheckType)
from attention_system.business.errors import DataError, StateError
from attention_system.markup import stereotype


@stereotype("интерфейс")
class Storage(ABC):
    """Интерфейс подсистемы «Хранилище данных». Все операции атомарны."""

    # --- пользователи ---
    @abstractmethod
    def user_by_login(self, login: str) -> Optional[User]: ...

    @abstractmethod
    def mark_login(self, user_id: int, moment: datetime) -> None: ...

    @abstractmethod
    def create_psychologist(self, psychologist: Psychologist) -> int: ...

    @abstractmethod
    def create_administrator(self, administrator: Administrator) -> int: ...

    # --- пилоты ---
    @abstractmethod
    def create_pilot(self, pilot: Pilot) -> int: ...

    @abstractmethod
    def pilot_by_id(self, pk: int) -> Optional[Pilot]: ...

    @abstractmethod
    def all_pilots(self) -> list[Pilot]: ...

    @abstractmethod
    def pilots_in(self, ids: list[int]) -> list[Pilot]: ...

    @abstractmethod
    def save_pilot(self, pilot: Pilot) -> None: ...

    @abstractmethod
    def delete_pilot(self, pk: int) -> None: ...

    # --- сессии, таблицы, результаты ---
    @abstractmethod
    def create_session(self, session: TestSession) -> int: ...

    @abstractmethod
    def session_by_id(self, pk: int) -> Optional[TestSession]: ...

    @abstractmethod
    def assigned_session(self, pilot_id: int) -> Optional[TestSession]: ...

    @abstractmethod
    def sessions_of(self, pilot_id: int,
                          status: Optional[SessionStatus] = None) -> list[TestSession]: ...

    @abstractmethod
    def save_session(self, session: TestSession) -> None: ...

    @abstractmethod
    def create_table(self, table: SchulteTable) -> int: ...

    @abstractmethod
    def tables_of(self, session_id: int) -> list[SchulteTable]: ...

    @abstractmethod
    def delete_tables(self, session_id: int) -> None: ...

    @abstractmethod
    def save_result(self, session: TestSession,
                                 result: TestResult) -> int: ...

    @abstractmethod
    def result_of(self, session_id: int) -> Optional[TestResult]: ...

    @abstractmethod
    def results_of_pilot(self, pilot_id: int
                              ) -> list[tuple[TestSession, TestResult]]: ...

    @abstractmethod
    def results_between(self, ids: list[int], start: date, end: date
                              ) -> list[tuple[TestSession, TestResult]]: ...

    # --- нормы и заключения ---
    @abstractmethod
    def current_norm_row(self) -> Optional[AdmissionNorm]: ...

    @abstractmethod
    def create_norm(self, norm: AdmissionNorm) -> int: ...

    @abstractmethod
    def update_norm(self, norm: AdmissionNorm) -> None: ...

    @abstractmethod
    def norm_is_used(self, norm_id: int) -> bool: ...

    @abstractmethod
    def create_conclusion(self, conclusion: Conclusion) -> int: ...

    @abstractmethod
    def conclusions_for(self, result_id: int) -> list[Conclusion]: ...

    # --- отчёты ---
    @abstractmethod
    def create_report(self, report: SummaryReport) -> int: ...

    @abstractmethod
    def pilots_of_report(self, report_id: int) -> list[int]: ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('pilot','psychologist','admin')),
    last_login TEXT);
CREATE TABLE IF NOT EXISTS pilots (
    pilot_id INTEGER PRIMARY KEY REFERENCES users(user_id),
    full_name TEXT NOT NULL,
    personnel_number TEXT NOT NULL UNIQUE,
    position TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS psychologists (
    psychologist_id INTEGER PRIMARY KEY REFERENCES users(user_id),
    full_name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS administrators (
    admin_id INTEGER PRIMARY KEY REFERENCES users(user_id),
    full_name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS test_sessions (
    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pilot_id INTEGER NOT NULL REFERENCES pilots(pilot_id),
    psychologist_id INTEGER NOT NULL REFERENCES psychologists(psychologist_id),
    date_time TEXT NOT NULL,
    method TEXT NOT NULL,
    check_type TEXT NOT NULL,
    status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schedule_tables (
    table_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES test_sessions(session_id),
    order_number INTEGER NOT NULL,
    size INTEGER NOT NULL,
    arrangement TEXT NOT NULL,
    time_seconds REAL);
CREATE TABLE IF NOT EXISTS test_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL UNIQUE REFERENCES test_sessions(session_id),
    er REAL NOT NULL, vr REAL NOT NULL, pu REAL NOT NULL);
CREATE TABLE IF NOT EXISTS admission_norms (
    norm_id INTEGER PRIMARY KEY AUTOINCREMENT,
    er_min REAL NOT NULL, er_max REAL NOT NULL,
    vr_min REAL NOT NULL, vr_max REAL NOT NULL,
    pu_min REAL NOT NULL, pu_max REAL NOT NULL);
CREATE TABLE IF NOT EXISTS admission_conclusions (
    conclusion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL REFERENCES test_results(result_id),
    psychologist_id INTEGER NOT NULL REFERENCES psychologists(psychologist_id),
    norm_id INTEGER NOT NULL REFERENCES admission_norms(norm_id),
    status TEXT NOT NULL, date TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS summary_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL REFERENCES administrators(admin_id),
    period_start TEXT NOT NULL, period_end TEXT NOT NULL, formation_date TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS summary_report_pilots (
    report_id INTEGER NOT NULL REFERENCES summary_reports(report_id),
    pilot_id INTEGER NOT NULL REFERENCES pilots(pilot_id),
    PRIMARY KEY (report_id, pilot_id));
"""


@stereotype("граничный")
class SqliteStorage(Storage):
    """Реализация интерфейса хранилища; играет роль посредника подсистемы (subsystem proxy).
    Одно соединение защищено блокировкой, поэтому объект безопасно использовать из многих потоков."""

    def __init__(self, path: str = ":memory:") -> None:
        self._connection: sqlite3.Connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._lock: threading.RLock = threading.RLock()
        with self._lock, self._connection:
            self._connection.executescript(SCHEMA)

    # ---------- вспомогательные операции ----------
    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._connection.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        lines = self._query(sql, params)
        return lines[0] if lines else None

    def _insert(self, sql: str, params: tuple) -> int:
        try:
            with self._lock, self._connection:
                return self._connection.execute(sql, params).lastrowid
        except sqlite3.IntegrityError as error:
            raise DataError(f"Нарушено ограничение целостности: {error}") from error

    def _insert_user(self, p: User) -> int:
        cursor = self._connection.execute(
            "INSERT INTO users(login, password_hash, role, last_login) VALUES (?,?,?,?)",
            (p.login, p.password_hash, p.role.value, p.last_login.isoformat() if p.last_login else None))
        p.pk = cursor.lastrowid
        return p.pk

    def _create_profile(self, user: User, sql: str, values: tuple) -> int:
        try:
            with self._lock, self._connection:
                pk = self._insert_user(user)
                self._connection.execute(sql, (pk, *values))
                return pk
        except sqlite3.IntegrityError as error:
            user.pk = None
            raise DataError(f"Нарушено ограничение целостности: {error}") from error

    @staticmethod
    def _parse_time(text: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(text) if text else None

    # ---------- пользователи ----------
    def user_by_login(self, login: str) -> Optional[User]:
        row = self._one("SELECT * FROM users WHERE login = ?", (login,))
        return self._load_user(row) if row else None

    def _load_user(self, u: sqlite3.Row) -> User:
        common = dict(login=u["login"], password_hash=u["password_hash"], pk=u["user_id"],
                     last_login=self._parse_time(u["last_login"]))
        role = Role(u["role"])
        if role == Role.PILOT:
            p = self._one("SELECT * FROM pilots WHERE pilot_id = ?", (u["user_id"],))
            return Pilot(**common, full_name=p["full_name"], employee_number=p["personnel_number"],
                         position=p["position"])
        if role == Role.PSYCHOLOGIST:
            p = self._one("SELECT * FROM psychologists WHERE psychologist_id = ?", (u["user_id"],))
            return Psychologist(**common, full_name=p["full_name"])
        p = self._one("SELECT * FROM administrators WHERE admin_id = ?", (u["user_id"],))
        return Administrator(**common, full_name=p["full_name"])

    def mark_login(self, user_id: int, moment: datetime) -> None:
        with self._lock, self._connection:
            self._connection.execute("UPDATE users SET last_login = ? WHERE user_id = ?",
                                     (moment.isoformat(), user_id))

    def create_psychologist(self, psychologist: Psychologist) -> int:
        return self._create_profile(psychologist, "INSERT INTO psychologists VALUES (?,?)", (psychologist.full_name,))

    def create_administrator(self, administrator: Administrator) -> int:
        return self._create_profile(administrator, "INSERT INTO administrators VALUES (?,?)",
                                    (administrator.full_name,))

    # ---------- пилоты ----------
    def create_pilot(self, pilot: Pilot) -> int:
        return self._create_profile(pilot, "INSERT INTO pilots VALUES (?,?,?,?)",
                                    (pilot.full_name, pilot.employee_number, pilot.position))

    def pilot_by_id(self, pk: int) -> Optional[Pilot]:
        row = self._one("SELECT * FROM users WHERE user_id = ? AND role = 'pilot'", (pk,))
        return self._load_user(row) if row else None

    def all_pilots(self) -> list[Pilot]:
        lines = self._query("SELECT u.* FROM users u JOIN pilots p ON p.pilot_id = u.user_id "
                              "ORDER BY p.full_name")
        return [self._load_user(s) for s in lines]

    def pilots_in(self, ids: list[int]) -> list[Pilot]:
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        lines = self._query(f"SELECT u.* FROM users u JOIN pilots p ON p.pilot_id = u.user_id "
                              f"WHERE u.user_id IN ({placeholders}) ORDER BY p.full_name", tuple(ids))
        return [self._load_user(s) for s in lines]

    def save_pilot(self, pilot: Pilot) -> None:
        try:
            with self._lock, self._connection:
                self._connection.execute("UPDATE users SET login = ?, password_hash = ? WHERE user_id = ?",
                                         (pilot.login, pilot.password_hash, pilot.pk))
                self._connection.execute(
                    "UPDATE pilots SET full_name = ?, personnel_number = ?, position = ? WHERE pilot_id = ?",
                    (pilot.full_name, pilot.employee_number, pilot.position, pilot.pk))
        except sqlite3.IntegrityError as error:
            raise DataError(f"Нарушено ограничение целостности: {error}") from error

    def delete_pilot(self, pk: int) -> None:
        try:
            with self._lock, self._connection:
                self._connection.execute("DELETE FROM pilots WHERE pilot_id = ?", (pk,))
                self._connection.execute("DELETE FROM users WHERE user_id = ?", (pk,))
        except sqlite3.IntegrityError as error:
            raise StateError("Нельзя удалить пилота: есть связанные записи") from error

    # ---------- сессии ----------
    @staticmethod
    def _session(s: sqlite3.Row) -> TestSession:
        return TestSession(
            pk=s["session_id"], pilot_id=s["pilot_id"], psychologist_id=s["psychologist_id"],
            occurred_at=datetime.fromisoformat(s["date_time"]), method=s["method"],
            check_type=CheckType(s["check_type"]), status=SessionStatus(s["status"]))

    def create_session(self, session: TestSession) -> int:
        session.pk = self._insert(
            "INSERT INTO test_sessions(pilot_id, psychologist_id, date_time, method, check_type, status) "
            "VALUES (?,?,?,?,?,?)",
            (session.pilot_id, session.psychologist_id, session.occurred_at.isoformat(), session.method,
             session.check_type.value, session.status.value))
        return session.pk

    def session_by_id(self, pk: int) -> Optional[TestSession]:
        row = self._one("SELECT * FROM test_sessions WHERE session_id = ?", (pk,))
        return self._session(row) if row else None

    def assigned_session(self, pilot_id: int) -> Optional[TestSession]:
        row = self._one("SELECT * FROM test_sessions WHERE pilot_id = ? AND status = ? "
                            "ORDER BY date_time LIMIT 1", (pilot_id, SessionStatus.ASSIGNED.value))
        return self._session(row) if row else None

    def sessions_of(self, pilot_id: int,
                          status: Optional[SessionStatus] = None) -> list[TestSession]:
        sql, params = "SELECT * FROM test_sessions WHERE pilot_id = ?", [pilot_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value)
        return [self._session(s) for s in self._query(sql + " ORDER BY date_time", tuple(params))]

    def save_session(self, session: TestSession) -> None:
        with self._lock, self._connection:
            self._connection.execute("UPDATE test_sessions SET status = ? WHERE session_id = ?",
                                     (session.status.value, session.pk))

    # ---------- таблицы ----------
    def create_table(self, table: SchulteTable) -> int:
        table.pk = self._insert(
            "INSERT INTO schedule_tables(session_id, order_number, size, arrangement, time_seconds) "
            "VALUES (?,?,?,?,?)",
            (table.session_id, table.order_no, table.size,
             table.number_order.value, table.time_sec))
        return table.pk

    def tables_of(self, session_id: int) -> list[SchulteTable]:
        lines = self._query("SELECT * FROM schedule_tables WHERE session_id = ? ORDER BY order_number",
                              (session_id,))
        return [SchulteTable(pk=s["table_id"], session_id=s["session_id"], order_no=s["order_number"],
                              size=s["size"], number_order=NumberOrder(s["arrangement"]),
                              time_sec=s["time_seconds"]) for s in lines]

    def delete_tables(self, session_id: int) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM schedule_tables WHERE session_id = ?", (session_id,))

    # ---------- результаты ----------
    @staticmethod
    def _result_row(r: sqlite3.Row) -> TestResult:
        return TestResult(pk=r["result_id"], session_id=r["session_id"],
                                     er=r["er"], vr=r["vr"], pu=r["pu"])

    def save_result(self, session: TestSession, result: TestResult) -> int:
        """Одна транзакция: результат сохраняется вместе с новым статусом сессии."""
        try:
            with self._lock, self._connection:
                cursor = self._connection.execute(
                    "INSERT INTO test_results(session_id, er, vr, pu) VALUES (?,?,?,?)",
                    (result.session_id, result.er, result.vr, result.pu))
                self._connection.execute("UPDATE test_sessions SET status = ? WHERE session_id = ?",
                                         (session.status.value, session.pk))
                result.pk = cursor.lastrowid
                return result.pk
        except sqlite3.IntegrityError as error:
            raise DataError(f"Нарушено ограничение целостности: {error}") from error

    def result_of(self, session_id: int) -> Optional[TestResult]:
        row = self._one("SELECT * FROM test_results WHERE session_id = ?", (session_id,))
        return self._result_row(row) if row else None

    def _pairs(self, sql: str, params: tuple) -> list[tuple[TestSession, TestResult]]:
        result = []
        for s in self._query(sql, params):
            session = self._session(s)
            result.append((session, TestResult(
                pk=s["result_id"], session_id=session.pk, er=s["er"], vr=s["vr"], pu=s["pu"])))
        return result

    def results_of_pilot(self, pilot_id: int) -> list[tuple[TestSession, TestResult]]:
        return self._pairs("SELECT s.*, r.result_id, r.er, r.vr, r.pu FROM test_sessions s "
                          "JOIN test_results r ON r.session_id = s.session_id "
                          "WHERE s.pilot_id = ? AND s.status = 'завершена' ORDER BY s.date_time", (pilot_id,))

    def results_between(self, ids: list[int], start: date, end: date
                              ) -> list[tuple[TestSession, TestResult]]:
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        return self._pairs(
            f"SELECT s.*, r.result_id, r.er, r.vr, r.pu FROM test_sessions s "
            f"JOIN test_results r ON r.session_id = s.session_id "
            f"WHERE s.pilot_id IN ({placeholders}) AND s.status = 'завершена' "
            f"AND date(s.date_time) BETWEEN ? AND ? ORDER BY s.date_time",
            (*ids, start.isoformat(), end.isoformat()))

    # ---------- нормы и заключения ----------
    @staticmethod
    def _norm(n: sqlite3.Row) -> AdmissionNorm:
        return AdmissionNorm(pk=n["norm_id"], er_min=n["er_min"], er_max=n["er_max"], vr_min=n["vr_min"],
                            vr_max=n["vr_max"], pu_min=n["pu_min"], pu_max=n["pu_max"])

    def current_norm_row(self) -> Optional[AdmissionNorm]:
        row = self._one("SELECT * FROM admission_norms ORDER BY norm_id DESC LIMIT 1")
        return self._norm(row) if row else None

    def create_norm(self, norm: AdmissionNorm) -> int:
        norm.pk = self._insert(
            "INSERT INTO admission_norms(er_min, er_max, vr_min, vr_max, pu_min, pu_max) VALUES (?,?,?,?,?,?)",
            (norm.er_min, norm.er_max, norm.vr_min, norm.vr_max, norm.pu_min, norm.pu_max))
        return norm.pk

    def update_norm(self, norm: AdmissionNorm) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE admission_norms SET er_min=?, er_max=?, vr_min=?, vr_max=?, pu_min=?, pu_max=? "
                "WHERE norm_id = ?",
                (norm.er_min, norm.er_max, norm.vr_min, norm.vr_max, norm.pu_min, norm.pu_max, norm.pk))

    def norm_is_used(self, norm_id: int) -> bool:
        return self._one("SELECT 1 FROM admission_conclusions WHERE norm_id = ? LIMIT 1", (norm_id,)) is not None

    def create_conclusion(self, conclusion: Conclusion) -> int:
        conclusion.pk = self._insert(
            "INSERT INTO admission_conclusions(result_id, psychologist_id, norm_id, status, date, comment) "
            "VALUES (?,?,?,?,?,?)",
            (conclusion.result_id, conclusion.psychologist_id, conclusion.norm_id,
             conclusion.decision.value, conclusion.on_date.isoformat(), conclusion.comment))
        return conclusion.pk

    def conclusions_for(self, result_id: int) -> list[Conclusion]:
        lines = self._query("SELECT * FROM admission_conclusions WHERE result_id = ? ORDER BY conclusion_id",
                              (result_id,))
        return [Conclusion(pk=s["conclusion_id"], result_id=s["result_id"],
                                   psychologist_id=s["psychologist_id"], norm_id=s["norm_id"],
                                   decision=Decision(s["status"]), on_date=date.fromisoformat(s["date"]),
                                   comment=s["comment"]) for s in lines]

    # ---------- отчёты ----------
    def create_report(self, report: SummaryReport) -> int:
        try:
            with self._lock, self._connection:
                cursor = self._connection.execute(
                    "INSERT INTO summary_reports(admin_id, period_start, period_end, formation_date) VALUES (?,?,?,?)",
                    (report.admin_id, report.period_start.isoformat(),
                     report.period_end.isoformat(), report.created_at.isoformat()))
                report.pk = cursor.lastrowid
                for pilot_id in report.pilot_ids():
                    self._connection.execute("INSERT INTO summary_report_pilots VALUES (?,?)",
                                             (report.pk, pilot_id))
                return report.pk
        except sqlite3.IntegrityError as error:
            raise DataError(f"Нарушено ограничение целостности: {error}") from error

    def pilots_of_report(self, report_id: int) -> list[int]:
        return [s["pilot_id"] for s in self._query(
            "SELECT pilot_id FROM summary_report_pilots WHERE report_id = ? ORDER BY pilot_id", (report_id,))]

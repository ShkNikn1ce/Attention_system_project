"""Хранилище данных: интерфейс подсистемы и реализация на SQLite (реляционная БД)."""
from __future__ import annotations

import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Optional

from attention_system.business.entities import (
    Администратор, АвиационныйПсихолог, ЗаключениеОДопуске, НормаДопуска, Пилот, Пользователь,
    РезультатТестирования, СводныйОтчёт, СессияТестирования, ТаблицаШульте)
from attention_system.business.enums import (
    РасположениеЧисел, РешениеОДопуске, Роль, СтатусСессии, ТипПроверки)
from attention_system.business.errors import ОшибкаДанных, ОшибкаСостояния
from attention_system.markup import стереотип


@стереотип("интерфейс")
class IХранилище(ABC):
    """Интерфейс подсистемы «Хранилище данных». Все операции атомарны."""

    # --- пользователи ---
    @abstractmethod
    def найтиПользователяПоЛогину(self, логин: str) -> Optional[Пользователь]: ...

    @abstractmethod
    def отметитьВход(self, кодПользователя: int, момент: datetime) -> None: ...

    @abstractmethod
    def создатьПсихолога(self, психолог: АвиационныйПсихолог) -> int: ...

    @abstractmethod
    def создатьАдминистратора(self, администратор: Администратор) -> int: ...

    # --- пилоты ---
    @abstractmethod
    def создатьПилота(self, пилот: Пилот) -> int: ...

    @abstractmethod
    def найтиПилота(self, код: int) -> Optional[Пилот]: ...

    @abstractmethod
    def найтиПилотов(self) -> list[Пилот]: ...

    @abstractmethod
    def найтиПилотовГруппы(self, коды: list[int]) -> list[Пилот]: ...

    @abstractmethod
    def обновитьПилота(self, пилот: Пилот) -> None: ...

    @abstractmethod
    def удалитьПилота(self, код: int) -> None: ...

    # --- сессии, таблицы, результаты ---
    @abstractmethod
    def создатьСессию(self, сессия: СессияТестирования) -> int: ...

    @abstractmethod
    def найтиСессию(self, код: int) -> Optional[СессияТестирования]: ...

    @abstractmethod
    def найтиНазначеннуюСессию(self, кодПилота: int) -> Optional[СессияТестирования]: ...

    @abstractmethod
    def найтиСессииПилота(self, кодПилота: int,
                          статус: Optional[СтатусСессии] = None) -> list[СессияТестирования]: ...

    @abstractmethod
    def обновитьСессию(self, сессия: СессияТестирования) -> None: ...

    @abstractmethod
    def создатьТаблицу(self, таблица: ТаблицаШульте) -> int: ...

    @abstractmethod
    def найтиТаблицыСессии(self, кодСессии: int) -> list[ТаблицаШульте]: ...

    @abstractmethod
    def удалитьТаблицыСессии(self, кодСессии: int) -> None: ...

    @abstractmethod
    def сохранитьРезультатСессии(self, сессия: СессияТестирования,
                                 результат: РезультатТестирования) -> int: ...

    @abstractmethod
    def найтиРезультатСессии(self, кодСессии: int) -> Optional[РезультатТестирования]: ...

    @abstractmethod
    def найтиРезультатыПилота(self, кодПилота: int
                              ) -> list[tuple[СессияТестирования, РезультатТестирования]]: ...

    @abstractmethod
    def найтиРезультатыГруппы(self, коды: list[int], начало: date, конец: date
                              ) -> list[tuple[СессияТестирования, РезультатТестирования]]: ...

    # --- нормы и заключения ---
    @abstractmethod
    def найтиДействующуюНорму(self) -> Optional[НормаДопуска]: ...

    @abstractmethod
    def создатьНорму(self, норма: НормаДопуска) -> int: ...

    @abstractmethod
    def обновитьНорму(self, норма: НормаДопуска) -> None: ...

    @abstractmethod
    def нормаИспользуется(self, кодНормы: int) -> bool: ...

    @abstractmethod
    def создатьЗаключение(self, заключение: ЗаключениеОДопуске) -> int: ...

    @abstractmethod
    def найтиЗаключенияРезультата(self, кодРезультата: int) -> list[ЗаключениеОДопуске]: ...

    # --- отчёты ---
    @abstractmethod
    def создатьОтчёт(self, отчёт: СводныйОтчёт) -> int: ...

    @abstractmethod
    def найтиПилотовОтчёта(self, кодОтчёта: int) -> list[int]: ...


СХЕМА = """
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


@стереотип("граничный")
class ХранилищеSQLite(IХранилище):
    """Реализация интерфейса хранилища; играет роль посредника подсистемы (subsystem proxy).
    Одно соединение защищено блокировкой, поэтому объект безопасно использовать из многих потоков."""

    def __init__(self, путь: str = ":memory:") -> None:
        self._соединение: sqlite3.Connection = sqlite3.connect(путь, check_same_thread=False)
        self._соединение.row_factory = sqlite3.Row
        self._соединение.execute("PRAGMA foreign_keys = ON")
        self._замок: threading.RLock = threading.RLock()
        with self._замок, self._соединение:
            self._соединение.executescript(СХЕМА)

    # ---------- вспомогательные операции ----------
    def _запрос(self, sql: str, параметры: tuple = ()) -> list[sqlite3.Row]:
        with self._замок:
            return self._соединение.execute(sql, параметры).fetchall()

    def _одна(self, sql: str, параметры: tuple = ()) -> Optional[sqlite3.Row]:
        строки = self._запрос(sql, параметры)
        return строки[0] if строки else None

    def _вставить(self, sql: str, параметры: tuple) -> int:
        try:
            with self._замок, self._соединение:
                return self._соединение.execute(sql, параметры).lastrowid
        except sqlite3.IntegrityError as ошибка:
            raise ОшибкаДанных(f"Нарушено ограничение целостности: {ошибка}") from ошибка

    def _вставитьПользователя(self, п: Пользователь) -> int:
        курсор = self._соединение.execute(
            "INSERT INTO users(login, password_hash, role, last_login) VALUES (?,?,?,?)",
            (п.логин, п.хэшПароля, п.роль.value, п.последнийВход.isoformat() if п.последнийВход else None))
        п.код = курсор.lastrowid
        return п.код

    def _создатьПрофиль(self, пользователь: Пользователь, sql: str, значения: tuple) -> int:
        try:
            with self._замок, self._соединение:
                код = self._вставитьПользователя(пользователь)
                self._соединение.execute(sql, (код, *значения))
                return код
        except sqlite3.IntegrityError as ошибка:
            пользователь.код = None
            raise ОшибкаДанных(f"Нарушено ограничение целостности: {ошибка}") from ошибка

    @staticmethod
    def _время(текст: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(текст) if текст else None

    # ---------- пользователи ----------
    def найтиПользователяПоЛогину(self, логин: str) -> Optional[Пользователь]:
        строка = self._одна("SELECT * FROM users WHERE login = ?", (логин,))
        return self._собратьПользователя(строка) if строка else None

    def _собратьПользователя(self, у: sqlite3.Row) -> Пользователь:
        общие = dict(логин=у["login"], хэшПароля=у["password_hash"], код=у["user_id"],
                     последнийВход=self._время(у["last_login"]))
        роль = Роль(у["role"])
        if роль == Роль.ПИЛОТ:
            п = self._одна("SELECT * FROM pilots WHERE pilot_id = ?", (у["user_id"],))
            return Пилот(**общие, фио=п["full_name"], табельныйНомер=п["personnel_number"],
                         должность=п["position"])
        if роль == Роль.ПСИХОЛОГ:
            п = self._одна("SELECT * FROM psychologists WHERE psychologist_id = ?", (у["user_id"],))
            return АвиационныйПсихолог(**общие, фио=п["full_name"])
        п = self._одна("SELECT * FROM administrators WHERE admin_id = ?", (у["user_id"],))
        return Администратор(**общие, фио=п["full_name"])

    def отметитьВход(self, кодПользователя: int, момент: datetime) -> None:
        with self._замок, self._соединение:
            self._соединение.execute("UPDATE users SET last_login = ? WHERE user_id = ?",
                                     (момент.isoformat(), кодПользователя))

    def создатьПсихолога(self, психолог: АвиационныйПсихолог) -> int:
        return self._создатьПрофиль(психолог, "INSERT INTO psychologists VALUES (?,?)", (психолог.фио,))

    def создатьАдминистратора(self, администратор: Администратор) -> int:
        return self._создатьПрофиль(администратор, "INSERT INTO administrators VALUES (?,?)",
                                    (администратор.фио,))

    # ---------- пилоты ----------
    def создатьПилота(self, пилот: Пилот) -> int:
        return self._создатьПрофиль(пилот, "INSERT INTO pilots VALUES (?,?,?,?)",
                                    (пилот.фио, пилот.табельныйНомер, пилот.должность))

    def найтиПилота(self, код: int) -> Optional[Пилот]:
        строка = self._одна("SELECT * FROM users WHERE user_id = ? AND role = 'pilot'", (код,))
        return self._собратьПользователя(строка) if строка else None

    def найтиПилотов(self) -> list[Пилот]:
        строки = self._запрос("SELECT u.* FROM users u JOIN pilots p ON p.pilot_id = u.user_id "
                              "ORDER BY p.full_name")
        return [self._собратьПользователя(с) for с in строки]

    def найтиПилотовГруппы(self, коды: list[int]) -> list[Пилот]:
        if not коды:
            return []
        метки = ",".join("?" * len(коды))
        строки = self._запрос(f"SELECT u.* FROM users u JOIN pilots p ON p.pilot_id = u.user_id "
                              f"WHERE u.user_id IN ({метки}) ORDER BY p.full_name", tuple(коды))
        return [self._собратьПользователя(с) for с in строки]

    def обновитьПилота(self, пилот: Пилот) -> None:
        try:
            with self._замок, self._соединение:
                self._соединение.execute("UPDATE users SET login = ?, password_hash = ? WHERE user_id = ?",
                                         (пилот.логин, пилот.хэшПароля, пилот.код))
                self._соединение.execute(
                    "UPDATE pilots SET full_name = ?, personnel_number = ?, position = ? WHERE pilot_id = ?",
                    (пилот.фио, пилот.табельныйНомер, пилот.должность, пилот.код))
        except sqlite3.IntegrityError as ошибка:
            raise ОшибкаДанных(f"Нарушено ограничение целостности: {ошибка}") from ошибка

    def удалитьПилота(self, код: int) -> None:
        try:
            with self._замок, self._соединение:
                self._соединение.execute("DELETE FROM pilots WHERE pilot_id = ?", (код,))
                self._соединение.execute("DELETE FROM users WHERE user_id = ?", (код,))
        except sqlite3.IntegrityError as ошибка:
            raise ОшибкаСостояния("Нельзя удалить пилота: есть связанные записи") from ошибка

    # ---------- сессии ----------
    @staticmethod
    def _сессия(с: sqlite3.Row) -> СессияТестирования:
        return СессияТестирования(
            код=с["session_id"], кодПилота=с["pilot_id"], кодПсихолога=с["psychologist_id"],
            датаВремя=datetime.fromisoformat(с["date_time"]), методика=с["method"],
            типПроверки=ТипПроверки(с["check_type"]), статус=СтатусСессии(с["status"]))

    def создатьСессию(self, сессия: СессияТестирования) -> int:
        сессия.код = self._вставить(
            "INSERT INTO test_sessions(pilot_id, psychologist_id, date_time, method, check_type, status) "
            "VALUES (?,?,?,?,?,?)",
            (сессия.кодПилота, сессия.кодПсихолога, сессия.датаВремя.isoformat(), сессия.методика,
             сессия.типПроверки.value, сессия.статус.value))
        return сессия.код

    def найтиСессию(self, код: int) -> Optional[СессияТестирования]:
        строка = self._одна("SELECT * FROM test_sessions WHERE session_id = ?", (код,))
        return self._сессия(строка) if строка else None

    def найтиНазначеннуюСессию(self, кодПилота: int) -> Optional[СессияТестирования]:
        строка = self._одна("SELECT * FROM test_sessions WHERE pilot_id = ? AND status = ? "
                            "ORDER BY date_time LIMIT 1", (кодПилота, СтатусСессии.НАЗНАЧЕНА.value))
        return self._сессия(строка) if строка else None

    def найтиСессииПилота(self, кодПилота: int,
                          статус: Optional[СтатусСессии] = None) -> list[СессияТестирования]:
        sql, параметры = "SELECT * FROM test_sessions WHERE pilot_id = ?", [кодПилота]
        if статус is not None:
            sql += " AND status = ?"
            параметры.append(статус.value)
        return [self._сессия(с) for с in self._запрос(sql + " ORDER BY date_time", tuple(параметры))]

    def обновитьСессию(self, сессия: СессияТестирования) -> None:
        with self._замок, self._соединение:
            self._соединение.execute("UPDATE test_sessions SET status = ? WHERE session_id = ?",
                                     (сессия.статус.value, сессия.код))

    # ---------- таблицы ----------
    def создатьТаблицу(self, таблица: ТаблицаШульте) -> int:
        таблица.код = self._вставить(
            "INSERT INTO schedule_tables(session_id, order_number, size, arrangement, time_seconds) "
            "VALUES (?,?,?,?,?)",
            (таблица.кодСессии, таблица.номерПоПорядку, таблица.размер,
             таблица.расположениеЧисел.value, таблица.времяСек))
        return таблица.код

    def найтиТаблицыСессии(self, кодСессии: int) -> list[ТаблицаШульте]:
        строки = self._запрос("SELECT * FROM schedule_tables WHERE session_id = ? ORDER BY order_number",
                              (кодСессии,))
        return [ТаблицаШульте(код=с["table_id"], кодСессии=с["session_id"], номерПоПорядку=с["order_number"],
                              размер=с["size"], расположениеЧисел=РасположениеЧисел(с["arrangement"]),
                              времяСек=с["time_seconds"]) for с in строки]

    def удалитьТаблицыСессии(self, кодСессии: int) -> None:
        with self._замок, self._соединение:
            self._соединение.execute("DELETE FROM schedule_tables WHERE session_id = ?", (кодСессии,))

    # ---------- результаты ----------
    @staticmethod
    def _результат(р: sqlite3.Row) -> РезультатТестирования:
        return РезультатТестирования(код=р["result_id"], кодСессии=р["session_id"],
                                     эр=р["er"], вр=р["vr"], пу=р["pu"])

    def сохранитьРезультатСессии(self, сессия: СессияТестирования, результат: РезультатТестирования) -> int:
        """Одна транзакция: результат сохраняется вместе с новым статусом сессии."""
        try:
            with self._замок, self._соединение:
                курсор = self._соединение.execute(
                    "INSERT INTO test_results(session_id, er, vr, pu) VALUES (?,?,?,?)",
                    (результат.кодСессии, результат.эр, результат.вр, результат.пу))
                self._соединение.execute("UPDATE test_sessions SET status = ? WHERE session_id = ?",
                                         (сессия.статус.value, сессия.код))
                результат.код = курсор.lastrowid
                return результат.код
        except sqlite3.IntegrityError as ошибка:
            raise ОшибкаДанных(f"Нарушено ограничение целостности: {ошибка}") from ошибка

    def найтиРезультатСессии(self, кодСессии: int) -> Optional[РезультатТестирования]:
        строка = self._одна("SELECT * FROM test_results WHERE session_id = ?", (кодСессии,))
        return self._результат(строка) if строка else None

    def _пары(self, sql: str, параметры: tuple) -> list[tuple[СессияТестирования, РезультатТестирования]]:
        результат = []
        for с in self._запрос(sql, параметры):
            сессия = self._сессия(с)
            результат.append((сессия, РезультатТестирования(
                код=с["result_id"], кодСессии=сессия.код, эр=с["er"], вр=с["vr"], пу=с["pu"])))
        return результат

    def найтиРезультатыПилота(self, кодПилота: int) -> list[tuple[СессияТестирования, РезультатТестирования]]:
        return self._пары("SELECT s.*, r.result_id, r.er, r.vr, r.pu FROM test_sessions s "
                          "JOIN test_results r ON r.session_id = s.session_id "
                          "WHERE s.pilot_id = ? AND s.status = 'завершена' ORDER BY s.date_time", (кодПилота,))

    def найтиРезультатыГруппы(self, коды: list[int], начало: date, конец: date
                              ) -> list[tuple[СессияТестирования, РезультатТестирования]]:
        if not коды:
            return []
        метки = ",".join("?" * len(коды))
        return self._пары(
            f"SELECT s.*, r.result_id, r.er, r.vr, r.pu FROM test_sessions s "
            f"JOIN test_results r ON r.session_id = s.session_id "
            f"WHERE s.pilot_id IN ({метки}) AND s.status = 'завершена' "
            f"AND date(s.date_time) BETWEEN ? AND ? ORDER BY s.date_time",
            (*коды, начало.isoformat(), конец.isoformat()))

    # ---------- нормы и заключения ----------
    @staticmethod
    def _норма(н: sqlite3.Row) -> НормаДопуска:
        return НормаДопуска(код=н["norm_id"], эрМин=н["er_min"], эрМакс=н["er_max"], врМин=н["vr_min"],
                            врМакс=н["vr_max"], пуМин=н["pu_min"], пуМакс=н["pu_max"])

    def найтиДействующуюНорму(self) -> Optional[НормаДопуска]:
        строка = self._одна("SELECT * FROM admission_norms ORDER BY norm_id DESC LIMIT 1")
        return self._норма(строка) if строка else None

    def создатьНорму(self, норма: НормаДопуска) -> int:
        норма.код = self._вставить(
            "INSERT INTO admission_norms(er_min, er_max, vr_min, vr_max, pu_min, pu_max) VALUES (?,?,?,?,?,?)",
            (норма.эрМин, норма.эрМакс, норма.врМин, норма.врМакс, норма.пуМин, норма.пуМакс))
        return норма.код

    def обновитьНорму(self, норма: НормаДопуска) -> None:
        with self._замок, self._соединение:
            self._соединение.execute(
                "UPDATE admission_norms SET er_min=?, er_max=?, vr_min=?, vr_max=?, pu_min=?, pu_max=? "
                "WHERE norm_id = ?",
                (норма.эрМин, норма.эрМакс, норма.врМин, норма.врМакс, норма.пуМин, норма.пуМакс, норма.код))

    def нормаИспользуется(self, кодНормы: int) -> bool:
        return self._одна("SELECT 1 FROM admission_conclusions WHERE norm_id = ? LIMIT 1", (кодНормы,)) is not None

    def создатьЗаключение(self, заключение: ЗаключениеОДопуске) -> int:
        заключение.код = self._вставить(
            "INSERT INTO admission_conclusions(result_id, psychologist_id, norm_id, status, date, comment) "
            "VALUES (?,?,?,?,?,?)",
            (заключение.кодРезультата, заключение.кодПсихолога, заключение.кодНормы,
             заключение.решение.value, заключение.дата.isoformat(), заключение.комментарий))
        return заключение.код

    def найтиЗаключенияРезультата(self, кодРезультата: int) -> list[ЗаключениеОДопуске]:
        строки = self._запрос("SELECT * FROM admission_conclusions WHERE result_id = ? ORDER BY conclusion_id",
                              (кодРезультата,))
        return [ЗаключениеОДопуске(код=с["conclusion_id"], кодРезультата=с["result_id"],
                                   кодПсихолога=с["psychologist_id"], кодНормы=с["norm_id"],
                                   решение=РешениеОДопуске(с["status"]), дата=date.fromisoformat(с["date"]),
                                   комментарий=с["comment"]) for с in строки]

    # ---------- отчёты ----------
    def создатьОтчёт(self, отчёт: СводныйОтчёт) -> int:
        try:
            with self._замок, self._соединение:
                курсор = self._соединение.execute(
                    "INSERT INTO summary_reports(admin_id, period_start, period_end, formation_date) VALUES (?,?,?,?)",
                    (отчёт.кодАдминистратора, отчёт.началоПериода.isoformat(),
                     отчёт.конецПериода.isoformat(), отчёт.датаСоздания.isoformat()))
                отчёт.код = курсор.lastrowid
                for кодПилота in отчёт.кодыПилотов():
                    self._соединение.execute("INSERT INTO summary_report_pilots VALUES (?,?)",
                                             (отчёт.код, кодПилота))
                return отчёт.код
        except sqlite3.IntegrityError as ошибка:
            raise ОшибкаДанных(f"Нарушено ограничение целостности: {ошибка}") from ошибка

    def найтиПилотовОтчёта(self, кодОтчёта: int) -> list[int]:
        return [с["pilot_id"] for с in self._запрос(
            "SELECT pilot_id FROM summary_report_pilots WHERE report_id = ? ORDER BY pilot_id", (кодОтчёта,))]

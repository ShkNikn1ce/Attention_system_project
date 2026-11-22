"""Тесты подсистемы «Хранилище данных»."""
import threading
import unittest
from datetime import date, datetime

from tests.helpers import World
from attention_system.business.entities import (
    Conclusion, Pilot, TestResult, SummaryReport, SchulteTable)
from attention_system.business.enums import NumberOrder, Decision, SessionStatus
from attention_system.business.errors import DataError, StateError
from attention_system.middleware.password import PasswordHash


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.s = World()
        self.db = self.s.storage

    def test_lookup_returns_subclass(self):
        """Поиск по логину возвращает объект подкласса с данными профиля."""
        p = self.db.user_by_login("pilot1")
        self.assertIsInstance(p, Pilot)
        self.assertEqual(p.employee_number, "T-001")
        self.assertIsNone(self.db.user_by_login("нет-такого"))

    def test_duplicate_login(self):
        """Повторный логин отклоняется, частично созданная запись откатывается."""
        before = len(self.db.all_pilots())
        with self.assertRaises(DataError):
            self.s.new_pilot("pilot1", "T-777", "Другой Д.Д.")
        self.assertEqual(len(self.db.all_pilots()), before)

    def test_duplicate_employee_number(self):
        """Повторный табельный номер отклоняется, учётная запись не остаётся «висеть»."""
        with self.assertRaises(DataError):
            self.s.new_pilot("pilot2", "T-001", "Другой Д.Д.")
        self.assertIsNone(self.db.user_by_login("pilot2"))

    def test_update_pilot(self):
        """Изменения профиля пилота сохраняются."""
        p = self.db.pilot_by_id(self.s.pilot.pk)
        p.position = "Второй пилот"
        self.db.save_pilot(p)
        self.assertEqual(self.db.pilot_by_id(p.pk).position, "Второй пилот")

    def test_delete_pilot_without_sessions(self):
        """Пилот без связанных записей удаляется вместе с учётной записью."""
        p = self.s.new_pilot("temp", "T-900", "Временный В.В.")
        self.db.delete_pilot(p.pk)
        self.assertIsNone(self.db.pilot_by_id(p.pk))
        self.assertIsNone(self.db.user_by_login("temp"))

    def test_delete_pilot_with_session_blocked(self):
        """Внешний ключ не даёт удалить пилота, у которого есть сессии."""
        self.s.assign()
        with self.assertRaises(StateError):
            self.db.delete_pilot(self.s.pilot.pk)
        self.assertIsNotNone(self.db.pilot_by_id(self.s.pilot.pk))

    def test_assigned_session_found_by_pilot(self):
        """Назначенная сессия находится по коду пилота, завершённая — нет."""
        session = self.s.assign()
        self.assertEqual(self.db.assigned_session(self.s.pilot.pk).pk, session.pk)
        session.complete()
        self.db.save_session(session)
        self.assertIsNone(self.db.assigned_session(self.s.pilot.pk))

    def test_tables_are_ordered(self):
        """Таблицы сессии возвращаются по порядковому номеру; удаление очищает их."""
        session = self.s.assign()
        for order in (3, 1, 2):
            self.db.create_table(SchulteTable(session_id=session.pk, order_no=order, size=3,
                                                number_order=NumberOrder.ORDERED, time_sec=4.0))
        self.assertEqual([t.order_no for t in self.db.tables_of(session.pk)], [1, 2, 3])
        self.db.delete_tables(session.pk)
        self.assertEqual(self.db.tables_of(session.pk), [])

    def test_result_saved_with_status(self):
        """Результат и новый статус сессии сохраняются одной транзакцией."""
        session = self.s.assign()
        session.complete()
        result = TestResult(session_id=session.pk, er=8.2, vr=0.97, pu=0.85)
        self.db.save_result(session, result)
        self.assertEqual(self.db.session_by_id(session.pk).status, SessionStatus.COMPLETED)
        self.assertAlmostEqual(self.db.result_of(session.pk).er, 8.2)

    def test_second_result_rolls_back(self):
        """Повторное сохранение результата отклоняется и не меняет статус сессии."""
        session = self.s.assign()
        session.complete()
        self.db.save_result(session, TestResult(session_id=session.pk, er=1))
        session.status = SessionStatus.CANCELLED
        with self.assertRaises(DataError):
            self.db.save_result(session, TestResult(session_id=session.pk, er=2))
        self.assertEqual(self.db.session_by_id(session.pk).status, SessionStatus.COMPLETED)

    def test_current_norm_is_latest(self):
        """Действующей считается последняя созданная норма."""
        fresh = self.s.norm.__class__(er_min=1, er_max=30, vr_min=0.5, vr_max=1.5, pu_min=0.5, pu_max=1.5)
        self.db.create_norm(fresh)
        self.assertEqual(self.db.current_norm_row().pk, fresh.pk)

    def test_norm_in_use(self):
        """Хранилище определяет, использована ли норма в заключениях."""
        session = self.s.finish_run([5, 5, 5, 5, 5])
        r = self.db.result_of(session.pk)
        self.assertFalse(self.db.norm_is_used(self.s.norm.pk))
        self.db.create_conclusion(Conclusion(result_id=r.pk, psychologist_id=self.s.psychologist.pk,
                                                    norm_id=self.s.norm.pk, decision=Decision.FIT,
                                                    on_date=date.today()))
        self.assertTrue(self.db.norm_is_used(self.s.norm.pk))
        self.assertEqual(len(self.db.conclusions_for(r.pk)), 1)

    def test_report_stores_pilots(self):
        """Сводный отчёт сохраняется вместе со списком пилотов (связь «многие ко многим»)."""
        report = SummaryReport(admin_id=self.s.admin_user.pk, period_start=date(2026, 1, 1),
                             period_end=date(2026, 12, 31), created_at=datetime.now())
        from attention_system.business.entities import ReportLine
        report.add_line(ReportLine(pilot_id=self.s.pilot.pk, full_name="Ф", session_count=1, avg_er=1, avg_vr=1, avg_pu=1))
        self.db.create_report(report)
        self.assertEqual(self.db.pilots_of_report(report.pk), [self.s.pilot.pk])

    def test_parallel_session_writes(self):
        """Из 20 потоков одновременно создаются сессии без ошибок и потерь."""
        errors = []

        def task():
            try:
                for _ in range(5):
                    self.s.assign()
            except Exception as error:  # noqa: BLE001
                errors.append(error)

        threads = [threading.Thread(target=task) for _ in range(20)]
        [p.start() for p in threads]
        [p.join() for p in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len(self.db.sessions_of(self.s.pilot.pk)), 100)


if __name__ == "__main__":
    unittest.main()

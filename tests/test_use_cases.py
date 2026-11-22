"""Тесты вариантов использования: основные и альтернативные потоки через формы и контроллеры."""
import random
import unittest
from datetime import date, datetime, timedelta

from tests.helpers import World
from attention_system.application import controllers as ctl
from attention_system.application import forms as ui
from attention_system.application.screen import Screen
from attention_system.business.entities import AdmissionNorm
from attention_system.business.enums import (
    NumberOrder, Decision, Role, SessionStatus, CheckType)
from attention_system.business.errors import LockoutError, AccessError, StateError
from attention_system.middleware.clock import ScriptedClock


def login_form(world, max_attempts=3):
    return ui.LoginForm(ctl.AuthController(world.storage, max_attempts), world.screen)


class UseCase1Login(unittest.TestCase):
    def setUp(self):
        self.s = World()

    def test_main_flow_pilot_login(self):
        """Основной поток: верные данные открывают интерфейс роли и обновляют время входа."""
        frm = login_form(self.s)
        frm.open_system()
        self.assertTrue(frm.enter_credentials("pilot1", "pilot123"))
        self.assertEqual(frm.work.role(), Role.PILOT)
        self.assertIn("Открыт интерфейс: пилот", self.s.screen.log)
        self.assertIsNotNone(self.s.storage.user_by_login("pilot1").last_login)

    def test_main_flow_staff_roles(self):
        """Основной поток: психолог и администратор получают свои интерфейсы."""
        frm = login_form(self.s)
        frm.enter_credentials("psy", "psy12345")
        self.assertEqual(frm.work.role(), Role.PSYCHOLOGIST)
        frm.enter_credentials("admin", "admin123")
        self.assertEqual(frm.work.role(), Role.ADMINISTRATOR)

    def test_alt_wrong_password(self):
        """Альтернативный поток 1: неверный пароль — сообщение об ошибке и предложение повторить ввод."""
        frm = login_form(self.s)
        self.assertFalse(frm.enter_credentials("pilot1", "неверный"))
        self.assertIsNone(frm.work)
        self.assertTrue(any("Ошибка входа" in s for s in self.s.screen.log))
        self.assertEqual(self.s.screen.last(), "Повторите ввод логина и пароля")

    def test_alt_unknown_login(self):
        """Альтернативный поток 1: неизвестный логин обрабатывается как неверные данные."""
        frm = login_form(self.s)
        self.assertFalse(frm.enter_credentials("нет-такого", "x"))

    def test_alt_attempt_limit(self):
        """Альтернативный поток 1: после исчерпания попыток вход блокируется даже с верным паролем."""
        frm = login_form(self.s, max_attempts=3)
        for _ in range(3):
            frm.enter_credentials("pilot1", "неверный")
        self.assertFalse(frm.enter_credentials("pilot1", "pilot123"))
        self.assertIn("Превышено число попыток входа", self.s.screen.last())

    def test_success_resets_counter(self):
        """Успешный вход сбрасывает счётчик неудачных попыток."""
        frm = login_form(self.s, max_attempts=3)
        for _ in range(2):
            frm.enter_credentials("pilot1", "неверный")
        self.assertTrue(frm.enter_credentials("pilot1", "pilot123"))
        for _ in range(2):
            frm.enter_credentials("pilot1", "неверный")
        self.assertTrue(frm.enter_credentials("pilot1", "pilot123"))


class UseCase2Schulte(unittest.TestCase):
    def setUp(self):
        self.s = World()
        self.session = self.s.assign()

    def form(self, times, pilot=None):
        controller = ctl.TestingController(self.s.storage, self.s.work(pilot or self.s.pilot), random.Random(5))
        return ui.TestingForm(controller, self.s.screen, ScriptedClock(times))

    def test_main_flow(self):
        """Основной поток: пять таблиц пройдены, показатели рассчитаны, результат и сессия сохранены."""
        frm = self.form([8, 9, 8, 7, 9])
        self.assertTrue(frm.open_testing())
        frm.confirm_ready(3, NumberOrder.SHUFFLED)
        for _ in range(5):
            frm.enter_numbers()
        r = self.s.storage.result_of(self.session.pk)
        self.assertAlmostEqual(r.er, 8.2)
        self.assertAlmostEqual(r.vr, 8 / 8.2)
        self.assertAlmostEqual(r.pu, 7 / 8.2)
        self.assertEqual(self.s.storage.session_by_id(self.session.pk).status, SessionStatus.COMPLETED)
        self.assertEqual([t.time_sec for t in self.s.storage.tables_of(self.session.pk)], [8, 9, 8, 7, 9])
        self.assertTrue(self.s.screen.last().startswith("Тестирование завершено"))

    def test_tables_4x4_shown_in_order(self):
        """Основной поток: форма последовательно показывает пять таблиц 4×4 с числами от 1 до 16."""
        frm = self.form([20, 18, 19, 22, 21])
        frm.open_testing()
        frm.confirm_ready(4, NumberOrder.SHUFFLED)
        for _ in range(5):
            frm.enter_numbers()
        shown_tables = [s for s in self.s.screen.log if s.startswith("Таблица")]
        self.assertEqual(len(shown_tables), 5)
        self.assertTrue(all(str(n) in shown_tables[0] for n in range(1, 17)))

    def test_alt_no_assigned_session(self):
        """Альтернативный поток 1: без назначенной сессии выводится сообщение, тест не начинается."""
        other = self.s.new_pilot("pilot2", "T-002", "Сидоров С.С.")
        frm = self.form([], pilot=other)
        self.assertFalse(frm.open_testing())
        self.assertEqual(self.s.screen.last(), "Для вас не назначено тестирование")

    def test_alt_abort(self):
        """Альтернативный поток 2: прерывание отменяет сессию и не сохраняет результат и таблицы."""
        frm = self.form([5, 6])
        frm.open_testing()
        frm.confirm_ready()
        frm.enter_numbers()
        frm.enter_numbers()
        frm.abort_testing()
        self.assertEqual(self.s.storage.session_by_id(self.session.pk).status, SessionStatus.CANCELLED)
        self.assertIsNone(self.s.storage.result_of(self.session.pk))
        self.assertEqual(self.s.storage.tables_of(self.session.pk), [])
        self.assertEqual(self.s.screen.last(), "Тестирование прервано, результат не сохранён")

    def test_finished_session_is_not_assigned(self):
        """После завершения сессии повторный запуск без нового назначения невозможен."""
        frm = self.form([5, 5, 5, 5, 5])
        frm.open_testing()
        frm.confirm_ready()
        for _ in range(5):
            frm.enter_numbers()
        self.assertFalse(self.form([]).open_testing())

    def test_pilot_only(self):
        """Психолог не может запустить тестирование (проверка роли)."""
        with self.assertRaises(AccessError):
            ctl.TestingController(self.s.storage, self.s.work(self.s.psychologist))


class UseCase3OwnResults(unittest.TestCase):
    def setUp(self):
        self.s = World()

    def form(self, pilot=None):
        return ui.OwnResultsForm(ctl.OwnResultsController(self.s.storage, self.s.work(pilot or self.s.pilot)),
                                      self.s.screen)

    def test_main_flow(self):
        """Основной поток: пилот видит список своих сессий и показатели выбранной."""
        session = self.s.finish_run([8, 9, 8, 7, 9])
        frm = self.form()
        self.assertTrue(frm.open_own_results())
        frm.choose_session(session.pk)
        self.assertEqual(self.s.screen.last(), "ЭР=8.20, ВР=0.976, ПУ=0.854")

    def test_alt_no_results(self):
        """Альтернативный поток 1: нет завершённых сессий — сообщение об отсутствии результатов."""
        self.assertFalse(self.form().open_own_results())
        self.assertEqual(self.s.screen.last(), "Сохранённых результатов нет")

    def test_foreign_results_forbidden(self):
        """Пилот не может просмотреть результаты другого пилота."""
        session = self.s.finish_run([5, 5, 5, 5, 5])
        other = self.s.new_pilot("pilot2", "T-002", "Сидоров С.С.")
        with self.assertRaises(AccessError):
            self.form(other).choose_session(session.pk)


class UseCase4Assign(unittest.TestCase):
    def setUp(self):
        self.s = World()

    def form(self, world=None):
        world = world or self.s
        return ui.AssignmentForm(
            ctl.AssignmentController(world.storage, world.work(world.psychologist), world.notifier), world.screen)

    def test_main_flow(self):
        """Основной поток: создаётся назначенная сессия, пилот получает уведомление."""
        frm = self.form()
        self.assertTrue(frm.open_assignment())
        frm.choose_pilot_and_check(self.s.pilot.pk, CheckType.PREFLIGHT)
        session = frm.confirm_assignment()
        saved = self.s.storage.session_by_id(session.pk)
        self.assertEqual(saved.status, SessionStatus.ASSIGNED)
        self.assertEqual(saved.check_type, CheckType.PREFLIGHT)
        self.assertEqual(saved.psychologist_id, self.s.psychologist.pk)
        self.assertEqual(len(self.s.notifier.log), 1)
        self.assertIn(self.s.pilot.full_name, self.s.notifier.log[0])

    def test_alt_pilots_not_found(self):
        """Альтернативный поток 1: в базе нет пилотов — сообщение об отсутствии пилота."""
        empty_world = World(with_pilot=False)
        self.assertFalse(self.form(empty_world).open_assignment())
        self.assertEqual(empty_world.screen.last(), "Пилоты в базе не найдены")

    def test_alt_pilot_not_found(self):
        """Альтернативный поток 1: назначение несуществующему пилоту не создаёт сессию и уведомление."""
        frm = self.form()
        frm.choose_pilot_and_check(999, CheckType.PLANNED)
        self.assertIsNone(frm.confirm_assignment())
        self.assertEqual(self.s.notifier.log, [])

    def test_psychologist_only(self):
        """Пилот не может назначать тестирование (проверка роли)."""
        with self.assertRaises(AccessError):
            ctl.AssignmentController(self.s.storage, self.s.work(self.s.pilot), self.s.notifier)


class UseCase5Review(unittest.TestCase):
    def setUp(self):
        self.s = World()
        self.frm = ui.ReviewForm(ctl.ReviewController(self.s.storage, self.s.work(self.s.psychologist)),
                                          self.s.screen)

    def test_main_flow(self):
        """Основной поток: психолог видит время каждой таблицы и показатели ЭР, ВР, ПУ."""
        session = self.s.finish_run([20, 18, 19, 22, 21])
        self.assertTrue(self.frm.choose_pilot(self.s.pilot.pk))
        self.frm.choose_session(session.pk)
        self.assertEqual(self.s.screen.last(),
                         "Время таблиц: 20.0, 18.0, 19.0, 22.0, 21.0; ЭР=20.00, ВР=1.000, ПУ=1.100")

    def test_alt_no_sessions(self):
        """Альтернативный поток 1: у пилота нет завершённых сессий — сообщение."""
        self.assertFalse(self.frm.choose_pilot(self.s.pilot.pk))
        self.assertEqual(self.s.screen.last(), "У пилота нет завершённых сессий")

    def test_session_has_no_result(self):
        """Запрос показателей несуществующей сессии отклоняется."""
        from attention_system.business.errors import NotFoundError
        with self.assertRaises(NotFoundError):
            self.frm.choose_session(999)


class UseCase6Conclusion(unittest.TestCase):
    def setUp(self):
        self.s = World()

    def form(self, world=None):
        world = world or self.s
        return ui.ConclusionForm(ctl.ConclusionController(world.storage, world.work(world.psychologist), world.safety), world.screen)

    def test_main_flow_within_norm(self):
        """Основной поток: показатели в норме — заключение «годен» сохранено и передано в службу безопасности."""
        session = self.s.finish_run([10, 10, 10, 10, 10])
        frm = self.form()
        self.assertTrue(frm.request_conclusion(session.pk))
        conclusion = frm.confirm_conclusion()
        self.assertEqual(conclusion.decision, Decision.FIT)
        result = self.s.storage.result_of(session.pk)
        self.assertEqual(len(self.s.storage.conclusions_for(result.pk)), 1)
        self.assertEqual(self.s.safety.conclusions, [conclusion])

    def test_alt_outside_norm(self):
        """Альтернативный поток 1: показатели вне нормы — предупреждение и направление на обследование."""
        session = self.s.finish_run([10, 10, 10, 14, 10])  # ПУ = 14 / 10,8 > 1,1
        frm = self.form()
        frm.request_conclusion(session.pk)
        self.assertTrue(self.s.screen.last().startswith("Внимание: показатели вне нормы"))
        conclusion = frm.confirm_conclusion(comment="повторное обследование")
        self.assertEqual(conclusion.decision, Decision.EXTRA_EXAM)
        self.assertEqual(self.s.safety.conclusions, [conclusion])

    def test_psychologist_overrides_decision(self):
        """Психолог может скорректировать предложенное заключение."""
        session = self.s.finish_run([10, 10, 10, 14, 10])
        frm = self.form()
        frm.request_conclusion(session.pk)
        conclusion = frm.confirm_conclusion(Decision.FIT_LIMITED, "допуск с ограничением")
        self.assertEqual(conclusion.decision, Decision.FIT_LIMITED)
        self.assertEqual(conclusion.comment, "допуск с ограничением")

    def test_norms_missing(self):
        """Без заданных норм допуска заключение не формируется."""
        world = World(with_norm=False)
        session = world.finish_run([10, 10, 10, 10, 10])
        frm = self.form(world)
        self.assertFalse(frm.request_conclusion(session.pk))
        self.assertEqual(world.screen.last(), "Нормы допуска не заданы")

    def test_no_result(self):
        """Для сессии без результата заключение не формируется."""
        session = self.s.assign()
        self.assertFalse(self.form().request_conclusion(session.pk))


class UseCase7Dynamics(unittest.TestCase):
    def setUp(self):
        self.s = World()
        self.frm = ui.DynamicsForm(ctl.DynamicsController(self.s.storage, self.s.work(self.s.psychologist)), self.s.screen)

    def test_main_flow(self):
        """Основной поток: две сессии дают график с точками, упорядоченными по дате."""
        now = datetime.now()
        self.s.finish_run([20, 18, 19, 22, 21], moment=now)
        self.s.finish_run([8, 9, 8, 7, 9], moment=now - timedelta(days=30))
        self.assertTrue(self.frm.open_dynamics(self.s.pilot.pk))
        lines = self.s.screen.last().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("8.20", lines[1])
        self.assertIn("20.00", lines[2])

    def test_alt_single_session(self):
        """Альтернативный поток 1: меньше двух сессий — сообщение о недостатке данных."""
        self.s.finish_run([8, 9, 8, 7, 9])
        self.assertFalse(self.frm.open_dynamics(self.s.pilot.pk))
        self.assertIn("Недостаточно данных", self.s.screen.last())

    def test_pilot_not_found(self):
        """Динамика несуществующего пилота не строится."""
        self.assertFalse(self.frm.open_dynamics(999))


class UseCase8Pilots(unittest.TestCase):
    def setUp(self):
        self.s = World(with_pilot=False)
        self.frm = ui.PilotAdminForm(ctl.PilotAdminController(self.s.storage, self.s.work(self.s.admin_user)), self.s.screen)
        self.payload = ctl.PilotData(login="pilot9", password="secret99", full_name="Орлов О.О.", employee_number="T-009", position="КВС")

    def test_create(self):
        """Основной поток: пилот добавлен, пароль хранится в виде хэша, вход возможен."""
        self.assertTrue(self.frm.enter_pilot(self.payload))
        p = self.s.storage.user_by_login("pilot9")
        self.assertNotIn("secret99", p.password_hash)
        self.assertTrue(p.check_password("secret99"))
        self.assertEqual(self.s.screen.last(), "Пилот добавлен")

    def test_update(self):
        """Подчинённый поток: данные пилота изменены и сохранены."""
        self.frm.enter_pilot(self.payload)
        pk = self.s.storage.user_by_login("pilot9").pk
        updated = ctl.PilotData(login="pilot9", password="", full_name="Орлов О.О.", employee_number="T-009", position="Второй пилот")
        self.assertTrue(self.frm.enter_update(pk, updated))
        p = self.s.storage.pilot_by_id(pk)
        self.assertEqual(p.position, "Второй пилот")
        self.assertTrue(p.check_password("secret99"))  # пустой пароль — прежний сохраняется

    def test_delete(self):
        """Подчинённый поток: пилот без сессий удалён."""
        self.frm.enter_pilot(self.payload)
        pk = self.s.storage.user_by_login("pilot9").pk
        self.assertTrue(self.frm.delete_pilot(pk))
        self.assertIsNone(self.s.storage.pilot_by_id(pk))

    def test_delete_pilot_with_sessions_blocked(self):
        """Пилота с сессиями тестирования удалить нельзя."""
        self.frm.enter_pilot(self.payload)
        pilot = self.s.storage.user_by_login("pilot9")
        self.s.assign(pilot)
        self.assertFalse(self.frm.delete_pilot(pilot.pk))
        self.assertIsNotNone(self.s.storage.pilot_by_id(pilot.pk))

    def test_alt_empty_name(self):
        """Альтернативный поток 1: пустое ФИО — ошибка и просьба повторить ввод."""
        self.payload.full_name = " "
        self.assertFalse(self.frm.enter_pilot(self.payload))
        self.assertEqual(self.s.screen.last(), "Исправьте данные и повторите ввод")

    def test_alt_short_password(self):
        """Альтернативный поток 1: пароль короче шести символов отклоняется."""
        self.payload.password = "123"
        self.assertFalse(self.frm.enter_pilot(self.payload))
        self.assertEqual(self.s.storage.all_pilots(), [])

    def test_alt_duplicate_employee_number(self):
        """Альтернативный поток 1: повторный табельный номер отклоняется, пилот не добавляется."""
        self.frm.enter_pilot(self.payload)
        again = ctl.PilotData(login="pilot10", password="secret99", full_name="Другой Д.Д.", employee_number="T-009")
        self.assertFalse(self.frm.enter_pilot(again))
        self.assertEqual(len(self.s.storage.all_pilots()), 1)

    def test_admin_only(self):
        """Психолог не может изменять данные пилотов (проверка роли)."""
        with self.assertRaises(AccessError):
            ctl.PilotAdminController(self.s.storage, self.s.work(self.s.psychologist))


class UseCase9Norms(unittest.TestCase):
    def setUp(self):
        self.s = World(with_norm=False)
        self.frm = ui.NormForm(ctl.NormController(self.s.storage, self.s.work(self.s.admin_user)), self.s.screen)

    def values(self, **overrides):
        params = dict(er_min=3, er_max=25, vr_min=0.8, vr_max=1.1, pu_min=0.8, pu_max=1.1)
        params.update(overrides)
        return AdmissionNorm(**params)

    def test_no_norms(self):
        """Если нормы ещё не заданы, форма сообщает об этом."""
        self.frm.open_norms()
        self.assertEqual(self.s.screen.last(), "Нормы допуска ещё не заданы")

    def test_main_flow_first_norm(self):
        """Основной поток: первая норма сохраняется и отображается."""
        self.assertTrue(self.frm.change_values(self.values()))
        self.frm.open_norms()
        self.assertEqual(self.s.screen.last(), "ЭР 3.0–25.0; ВР 0.8–1.1; ПУ 0.8–1.1")

    def test_unused_norm_is_updated(self):
        """Норма, не применявшаяся в заключениях, обновляется на месте."""
        self.frm.change_values(self.values())
        first_id = self.s.storage.current_norm_row().pk
        self.frm.change_values(self.values(er_max=30))
        current_norm = self.s.storage.current_norm_row()
        self.assertEqual(current_norm.pk, first_id)
        self.assertEqual(current_norm.er_max, 30)

    def test_used_norm_is_versioned(self):
        """Норма, применённая в заключении, не меняется: создаётся новая версия."""
        self.frm.change_values(self.values())
        norm = self.s.storage.current_norm_row()
        session = self.s.finish_run([10, 10, 10, 10, 10])
        form = ui.ConclusionForm(ctl.ConclusionController(self.s.storage, self.s.work(self.s.psychologist), self.s.safety),
                                  self.s.screen)
        form.request_conclusion(session.pk)
        form.confirm_conclusion()
        self.frm.change_values(self.values(er_max=40))
        fresh = self.s.storage.current_norm_row()
        self.assertNotEqual(fresh.pk, norm.pk)
        self.assertEqual(fresh.er_max, 40)

    def test_alt_bad_range(self):
        """Альтернативный поток 1: нижняя граница больше верхней — ошибка, нормы не меняются."""
        self.frm.change_values(self.values())
        self.assertFalse(self.frm.change_values(self.values(vr_min=1.5)))
        self.assertIn("Диапазон ВР", self.s.screen.last())
        self.assertEqual(self.s.storage.current_norm_row().vr_min, 0.8)


class UseCase10Report(unittest.TestCase):
    def setUp(self):
        self.s = World()
        self.frm = ui.ReportForm(ctl.ReportController(self.s.storage, self.s.work(self.s.admin_user), self.s.safety),
                                       self.s.screen)

    def test_main_flow(self):
        """Основной поток: отчёт по группе сформирован, сохранён и передан в службу безопасности."""
        self.s.finish_run([8, 9, 8, 7, 9])
        self.s.finish_run([20, 18, 19, 22, 21])
        self.assertTrue(self.frm.set_period_and_group(date(2000, 1, 1), date.today() + timedelta(days=1), [self.s.pilot.pk]))
        report = self.s.safety.reports[0]
        self.assertEqual(len(report.lines), 1)
        self.assertEqual(report.lines[0].session_count, 2)
        self.assertAlmostEqual(report.lines[0].avg_er, (8.2 + 20.0) / 2)
        self.assertEqual(self.s.storage.pilots_of_report(report.pk), [self.s.pilot.pk])

    def test_report_includes_only_group(self):
        """Пилоты вне выбранной группы в отчёт не попадают."""
        other = self.s.new_pilot("pilot2", "T-002", "Сидоров С.С.")
        self.s.finish_run([5, 5, 5, 5, 5])
        self.s.finish_run([6, 6, 6, 6, 6], pilot=other)
        self.frm.set_period_and_group(date(2000, 1, 1), date.today() + timedelta(days=1), [other.pk])
        self.assertEqual([s.pilot_id for s in self.s.safety.reports[0].lines], [other.pk])

    def test_alt_no_data(self):
        """Альтернативный поток 1: нет данных за период — сообщение, отчёт не создаётся."""
        self.assertFalse(self.frm.set_period_and_group(date(2000, 1, 1), date.today(), [self.s.pilot.pk]))
        self.assertEqual(self.s.screen.last(), "Нет данных за указанный период")
        self.assertEqual(self.s.safety.reports, [])

    def test_period_outside_data(self):
        """Сессии вне указанного периода в отчёт не включаются."""
        self.s.finish_run([5, 5, 5, 5, 5], moment=datetime(2020, 1, 15))
        self.assertFalse(self.frm.set_period_and_group(date(2021, 1, 1), date(2021, 12, 31), [self.s.pilot.pk]))

    def test_start_after_end(self):
        """Период с началом позже конца отклоняется."""
        self.assertFalse(self.frm.set_period_and_group(date(2026, 5, 2), date(2026, 5, 1), [self.s.pilot.pk]))

    def test_admin_only(self):
        """Пилот не может формировать сводный отчёт (проверка роли)."""
        with self.assertRaises(AccessError):
            ctl.ReportController(self.s.storage, self.s.work(self.s.pilot), self.s.safety)


if __name__ == "__main__":
    unittest.main()

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from schulte.models import (
    AdmissionNorm, Conclusion, LoginThrottle, SchulteTable, TestSession, User,
)
from schulte.services import (
    DomainError, assign_session, build_report, calculate, cancel_session, record_table,
    save_conclusion, save_norm, suggest_decision,
)


def make_user(username, role, **extra):
    password = extra.pop("password", "secret12")
    user = User(username=username, role=role, full_name=extra.pop("full_name", username), **extra)
    user.set_password(password)
    user.save()
    return user


def finish(session, times):
    for index, seconds in enumerate(times[:5], start=1):
        record_table(
            session, index, 3, session.number_order,
            list(range(1, 10)), seconds,
        )
    session.refresh_from_db()
    return session


class FormulaTests(TestCase):
    def test_short_name_uses_initials(self):
        user = User(full_name="Шкодин Никита Романович", username="shk", role=User.Role.PILOT)
        self.assertEqual(user.short_name(), "Шкодин Н. Р.")
        compact = User(full_name="Петрова А.С.", username="psy", role=User.Role.PSYCHOLOGIST)
        self.assertEqual(compact.short_name(), "Петрова А. С.")
    def test_known_times(self):
        efficiency, warmup, stability = calculate([8, 9, 8, 7, 9])
        self.assertAlmostEqual(efficiency, 8.2)
        self.assertAlmostEqual(warmup, 8 / 8.2)
        self.assertAlmostEqual(stability, 7 / 8.2)

    def test_rejects_bad_input(self):
        with self.assertRaises(DomainError):
            calculate([1, 2, 3])
        with self.assertRaises(DomainError):
            calculate([1, 2, 3, 0, 5])


class LoginTests(TestCase):
    def setUp(self):
        self.pilot = make_user("pilot1", User.Role.PILOT, password="pilot123", employee_number="T-001")

    def test_wrong_password_then_lock(self):
        url = reverse("login")
        for _ in range(3):
            response = self.client.post(url, {"username": "pilot1", "password": "неверный"})
            self.assertContains(response, "Неверный логин или пароль")
        response = self.client.post(url, {"username": "pilot1", "password": "pilot123"})
        self.assertContains(response, "Превышено число попыток входа")
        self.assertEqual(LoginThrottle.objects.get(username="pilot1").failures, 3)

    def test_success_resets_counter(self):
        url = reverse("login")
        self.client.post(url, {"username": "pilot1", "password": "неверный"})
        response = self.client.post(url, {"username": "pilot1", "password": "pilot123"})
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(LoginThrottle.objects.get(username="pilot1").failures, 0)

    def test_other_role_is_forbidden(self):
        self.client.force_login(self.pilot)
        response = self.client.get(reverse("norms"))
        self.assertEqual(response.status_code, 403)


class RegistrationTests(TestCase):
    def test_pilot_registers_and_logs_in(self):
        response = self.client.post(reverse("register"), {
            "username": "newpilot",
            "password": "secret1",
            "full_name": "Иванов И.И.",
            "employee_number": "T-100",
            "position": "Второй пилот",
        })
        self.assertRedirects(response, reverse("login"))
        pilot = User.objects.get(username="newpilot")
        self.assertEqual(pilot.role, User.Role.PILOT)
        self.assertEqual(pilot.full_name, "Иванов И.И.")
        logged = self.client.post(reverse("login"), {"username": "newpilot", "password": "secret1"})
        self.assertRedirects(logged, reverse("dashboard"))
        home = self.client.get(reverse("dashboard"))
        self.assertNotContains(home, "Открыт интерфейс")

    def test_psychologist_sees_only_assignment_notice(self):
        make_user("psy", User.Role.PSYCHOLOGIST)
        pilot = make_user("pilot1", User.Role.PILOT, employee_number="T-001")
        logged = self.client.post(reverse("login"), {"username": "psy", "password": "secret12"})
        self.assertRedirects(logged, reverse("dashboard"))
        home = self.client.get(reverse("dashboard"))
        self.assertNotContains(home, "Открыт интерфейс")
        assigned = self.client.post(reverse("assign_test"), {
            "pilot": pilot.pk,
            "check_type": TestSession.CheckType.PLANNED,
            "table_size": 3,
            "number_order": "по порядку",
        }, follow=True)
        self.assertContains(assigned, "Тестирование назначено, пилот уведомлён.")
        self.assertNotContains(assigned, "сессия")

    def test_admin_hides_green_notice(self):
        make_user("admin", User.Role.ADMIN)
        logged = self.client.post(
            reverse("login"), {"username": "admin", "password": "secret12"}, follow=True)
        self.assertContains(logged, "Админ")
        self.assertNotContains(logged, "Администратор")
        self.assertNotContains(logged, "Открыт интерфейс")

    def test_short_password_is_rejected(self):
        response = self.client.post(reverse("register"), {
            "username": "newpilot",
            "password": "123",
            "full_name": "Иванов И.И.",
            "employee_number": "T-100",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newpilot").exists())

    def test_staff_username_is_not_taken_by_registration(self):
        make_user("admin", User.Role.ADMIN)
        response = self.client.post(reverse("register"), {
            "username": "admin",
            "password": "secret1",
            "full_name": "Чужой Ч.Ч.",
            "employee_number": "T-100",
        })
        self.assertContains(response, "Логин уже занят")
        self.assertEqual(User.objects.get(username="admin").role, User.Role.ADMIN)


class SessionFlowTests(TestCase):
    def setUp(self):
        self.pilot = make_user("pilot1", User.Role.PILOT, employee_number="T-001", position="КВС")
        self.other = make_user("pilot2", User.Role.PILOT, employee_number="T-002")
        self.psy = make_user("psy", User.Role.PSYCHOLOGIST)
        self.admin = make_user("admin", User.Role.ADMIN)
        self.norm = AdmissionNorm.objects.create(
            er_min=3, er_max=25, vr_min=0.8, vr_max=1.1, pu_min=0.8, pu_max=1.1)

    def test_ordered_layout_pauses_between_five_tables(self):
        session = assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED)
        session.practice_done = True
        session.save(update_fields=["practice_done"])
        self.client.force_login(self.pilot)
        self.assertRedirects(
            self.client.post(reverse("test_start"), {"mode": "real"}), reverse("test_table"))
        sequence = ",".join(str(number) for number in range(1, 10))
        for index in range(1, 5):
            self.assertEqual(self.client.get(reverse("test_table")).status_code, 200)
            paused = self.client.post(reverse("test_table"), {"action": "done", "sequence": sequence})
            self.assertRedirects(paused, reverse("test_table"))
            screen = self.client.get(reverse("test_table"))
            self.assertContains(screen, f"Перейти к таблице {index + 1}")
            self.assertContains(screen, " с")
            self.assertNotContains(screen, 'class="cell"')
            session.refresh_from_db()
            self.assertEqual(session.tables.count(), index)
            self.assertEqual(session.status, TestSession.Status.ASSIGNED)
            self.client.post(reverse("test_table"), {"action": "next"})
        self.client.get(reverse("test_table"))
        done = self.client.post(reverse("test_table"), {"action": "done", "sequence": sequence})
        self.assertRedirects(done, reverse("test_table"))
        summary = self.client.get(reverse("test_table"))
        self.assertContains(summary, "Результат наблюдений")
        self.assertContains(summary, "ЭР, эффективность")
        self.assertContains(summary, "Таблица 5")
        session.refresh_from_db()
        self.assertEqual(session.tables.count(), 5)
        self.assertEqual(session.status, TestSession.Status.COMPLETED)
        self.assertAlmostEqual(session.result.er, sum(table.time_sec for table in session.tables.all()) / 5)
        finished = self.client.post(reverse("test_table"), {"action": "finish"})
        self.assertRedirects(finished, reverse("my_result", args=[session.pk]))

    def test_five_tables_calculate_and_finish(self):
        session = assign_session(
            self.psy, self.pilot, TestSession.CheckType.PLANNED,
            layout=SchulteTable.Layout.SHUFFLED)
        self.assertIn("назначена", session.pilot.notifications.get().text)
        finish(session, [8, 9, 8, 7, 9])
        self.assertEqual(session.status, TestSession.Status.COMPLETED)
        self.assertAlmostEqual(session.result.er, 8.2)
        self.assertEqual(suggest_decision(session.result, self.norm), Conclusion.Decision.FIT)

    def test_cancel_drops_tables(self):
        session = assign_session(
            self.psy, self.pilot, TestSession.CheckType.PLANNED,
            layout=SchulteTable.Layout.SHUFFLED)
        record_table(session, 1, 3, SchulteTable.Layout.SHUFFLED, [2, 1, 3, 4, 5, 6, 7, 8, 9], 4)
        cancel_session(session)
        session.refresh_from_db()
        self.assertEqual(session.status, TestSession.Status.CANCELLED)
        self.assertEqual(session.tables.count(), 0)

    def test_pilot_cannot_open_foreign_result(self):
        session = assign_session(self.psy, self.other, TestSession.CheckType.PLANNED)
        finish(session, [8, 9, 8, 7, 9])
        self.client.force_login(self.pilot)
        response = self.client.get(reverse("my_result", args=[session.pk]))
        self.assertEqual(response.status_code, 404)

    def test_conclusion_outside_norm_and_versioning(self):
        session = assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED)
        finish(session, [40, 40, 40, 40, 40])
        self.assertEqual(suggest_decision(session.result, self.norm), Conclusion.Decision.EXTRA)
        updated = save_norm({
            "er_min": 3, "er_max": 20, "vr_min": 0.8, "vr_max": 1.1, "pu_min": 0.8, "pu_max": 1.1,
        })
        self.assertEqual(updated.pk, self.norm.pk)
        save_conclusion(session.result, self.psy, self.norm, Conclusion.Decision.EXTRA, "")
        self.client.force_login(self.pilot)
        own = self.client.get(reverse("my_result", args=[session.pk]))
        self.assertContains(own, "Требуется дополнительное обследование")
        self.assertNotContains(own, "Направить")
        newer = save_norm({
            "er_min": 4, "er_max": 30, "vr_min": 0.7, "vr_max": 1.2, "pu_min": 0.7, "pu_max": 1.2,
        })
        self.assertNotEqual(newer.pk, self.norm.pk)
        self.norm.refresh_from_db()
        self.assertEqual(self.norm.er_max, 20)

    def test_delete_pilot_with_session_is_blocked(self):
        assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("pilot_delete", args=[self.pilot.pk]))
        self.assertRedirects(response, reverse("pilot_list"))
        self.assertTrue(User.objects.filter(pk=self.pilot.pk).exists())

    def test_report_uses_period_and_group(self):
        now = timezone.now()
        inside = assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED)
        finish(inside, [8, 9, 8, 7, 9])
        outside = TestSession.objects.create(
            pilot=self.other, psychologist=self.psy,
            scheduled_at=now - timedelta(days=40),
            check_type=TestSession.CheckType.PLANNED,
            status=TestSession.Status.ASSIGNED,
        )
        finish(outside, [10, 10, 10, 10, 10])
        report = build_report(
            self.admin, timezone.localdate(), timezone.localdate(), [self.pilot, self.other])
        self.assertEqual(report.lines.count(), 1)
        self.assertEqual(report.lines.get().full_name, self.pilot.display_name())
        with self.assertRaises(DomainError):
            build_report(self.admin, timezone.localdate() + timedelta(days=2), timezone.localdate(), [self.pilot])

    def test_assignment_fixes_size_and_order(self):
        session = assign_session(
            self.psy, self.pilot, TestSession.CheckType.PLANNED,
            table_size=4, layout=SchulteTable.Layout.SHUFFLED)
        note = session.pilot.notifications.get().text
        self.assertIn("4×4", note)
        self.assertIn("вперемешку", note)
        self.client.force_login(self.pilot)
        start = self.client.get(reverse("test_start"))
        self.assertContains(start, "4×4")
        self.assertContains(start, "вперемешку")
        self.assertNotContains(start, 'name="size"')
        self.assertContains(start, "Пройти пробную таблицу")
        self.assertContains(start, 'class="center-action"')
        self.client.post(reverse("test_start"), {"mode": "practice"})
        table = self.client.get(reverse("test_table"))
        html = table.content.decode()
        self.assertEqual(html.count('class="cell"'), 16)
        self.assertIn("focus-test", html)
        self.assertNotIn("<aside", html)
        self.assertNotIn("Прервать", html)
        self.assertNotIn("Ищите число", html)

    def test_practice_table_is_once_and_not_scored(self):
        session = assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED, table_size=4)
        self.client.force_login(self.pilot)
        self.client.post(reverse("test_start"), {"mode": "practice"})
        sequence = ",".join(str(number) for number in range(1, 17))
        done = self.client.post(reverse("test_table"), {"action": "done", "sequence": sequence})
        self.assertRedirects(done, reverse("test_start"))
        session.refresh_from_db()
        self.assertTrue(session.practice_done)
        self.assertEqual(session.tables.count(), 0)
        self.assertEqual(session.status, TestSession.Status.ASSIGNED)
        again = self.client.post(reverse("test_start"), {"mode": "practice"})
        self.assertEqual(again.status_code, 200)
        self.assertContains(again, "Подтвердить готовность")
        self.assertNotContains(again, "Пройти пробную таблицу")

    def test_browser_flow_completes_five_tables(self):
        session = assign_session(
            self.psy, self.pilot, TestSession.CheckType.PLANNED,
            layout=SchulteTable.Layout.SHUFFLED)
        session.practice_done = True
        session.save(update_fields=["practice_done"])
        self.client.force_login(self.pilot)
        start = self.client.post(reverse("test_start"), {"mode": "real"})
        self.assertRedirects(start, reverse("test_table"))
        sequence = ",".join(str(number) for number in range(1, 10))
        for _ in range(5):
            self.assertEqual(self.client.get(reverse("test_table")).status_code, 200)
            response = self.client.post(reverse("test_table"), {"action": "done", "sequence": sequence})
        session = TestSession.objects.get(pilot=self.pilot)
        self.assertRedirects(response, reverse("my_result", args=[session.pk]))
        self.assertEqual(session.status, TestSession.Status.COMPLETED)
        self.assertEqual(session.tables.count(), 5)

    def test_dynamics_needs_two_sessions(self):
        session = assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED)
        finish(session, [8, 9, 8, 7, 9])
        self.client.force_login(self.psy)
        response = self.client.get(reverse("dynamics_pilot", args=[self.pilot.pk]))
        self.assertContains(response, "Недостаточно данных")

    def test_dynamics_chart_marks_each_attempt(self):
        finish(assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED), [8, 9, 8, 7, 9])
        finish(assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED), [10, 10, 10, 12, 10])
        self.client.force_login(self.psy)
        response = self.client.get(reverse("dynamics_pilot", args=[self.pilot.pk]))
        self.assertContains(response, "Время, с")
        self.assertContains(response, "Попытки")
        self.assertContains(response, ">0</text>")
        self.assertContains(response, "<th>Попытка</th><th>ЭР</th><th>ВР</th><th>ПУ</th><th>Дата и время</th>")
        review = self.client.get(reverse("review_pilot", args=[self.pilot.pk]))
        self.assertContains(review, "<th>Попытка</th><th>Тип</th><th>ЭР</th><th>ВР</th><th>ПУ</th><th>Дата</th>")
        first = TestSession.objects.filter(
            pilot=self.pilot, status=TestSession.Status.COMPLETED,
        ).order_by("scheduled_at", "id").first()
        detail = self.client.get(reverse("review_session", args=[first.pk]))
        self.assertContains(detail, "Попытка 1")
        self.assertNotContains(detail, "сессия")
        self.assertEqual(response.content.decode().count('class="point"'), 6)

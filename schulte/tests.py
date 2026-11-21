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
    for index, seconds in enumerate(times, start=1):
        record_table(
            session, index, 3, SchulteTable.Layout.ORDERED,
            list(range(1, 10)), seconds,
        )
    session.refresh_from_db()
    return session


class FormulaTests(TestCase):
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

    def test_five_tables_calculate_and_finish(self):
        session = assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED)
        self.assertIn("назначена", session.pilot.notifications.get().text)
        finish(session, [8, 9, 8, 7, 9])
        self.assertEqual(session.status, TestSession.Status.COMPLETED)
        self.assertAlmostEqual(session.result.er, 8.2)
        self.assertEqual(suggest_decision(session.result, self.norm), Conclusion.Decision.FIT)

    def test_cancel_drops_tables(self):
        session = assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED)
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

    def test_browser_flow_completes_five_tables(self):
        assign_session(self.psy, self.pilot, TestSession.CheckType.PLANNED)
        self.client.force_login(self.pilot)
        start = self.client.post(reverse("test_start"), {"size": "3", "layout": SchulteTable.Layout.ORDERED})
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

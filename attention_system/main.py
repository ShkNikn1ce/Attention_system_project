"""Демонстрация работы всех вариантов использования на тестовых данных.
Запуск:  python -m attention_system.main"""
from __future__ import annotations

import random
from datetime import date, datetime

from attention_system.application import controllers as ctl
from attention_system.application import forms as ui
from attention_system.application.screen import Screen
from attention_system.business.entities import Administrator, Psychologist, AdmissionNorm
from attention_system.business.enums import NumberOrder, CheckType
from attention_system.middleware.clock import ScriptedClock
from attention_system.middleware.external import MemorySafetyService, MemoryNotifier
from attention_system.middleware.password import PasswordHash
from attention_system.middleware.storage import SqliteStorage


def sign_in(storage, login, password, screen):
    form = ui.LoginForm(ctl.AuthController(storage), screen)
    form.open_system()
    form.enter_credentials(login, password)
    return form.work


def main() -> None:
    screen = Screen(echo=True)
    storage = SqliteStorage()
    notifier, safety = MemoryNotifier(), MemorySafetyService()
    storage.create_administrator(Administrator(login="admin", password_hash=PasswordHash.make("admin123"), full_name="Администратор"))
    storage.create_psychologist(Psychologist(login="psy", password_hash=PasswordHash.make("psy12345"), full_name="Петрова А.С."))

    print("\n=== Прецедент 1. Вход: неверный пароль, затем верный ===")
    sign_in(storage, "admin", "неверный", screen)
    admin_user = sign_in(storage, "admin", "admin123", screen)

    print("\n=== Прецедент 9. Нормы допуска ===")
    norm_form = ui.NormForm(ctl.NormController(storage, admin_user), screen)
    norm_form.change_values(AdmissionNorm(er_min=3, er_max=25, vr_min=0.8, vr_max=1.1, pu_min=0.8, pu_max=1.1))
    norm_form.open_norms()

    print("\n=== Прецедент 8. Данные о пилотах ===")
    pilots_form = ui.PilotAdminForm(ctl.PilotAdminController(storage, admin_user), screen)
    pilots_form.enter_pilot(ctl.PilotData(login="pilot1", password="pilot123", full_name="Шкодин Н.Р.", employee_number="T-001", position="КВС"))
    pilots_form.open_pilot_list()
    pilot = storage.all_pilots()[0]

    print("\n=== Прецедент 4. Назначение тестирования ===")
    psychologist = sign_in(storage, "psy", "psy12345", screen)
    assign_form = ui.AssignmentForm(ctl.AssignmentController(storage, psychologist, notifier), screen)
    assign_form.open_assignment()
    assign_form.choose_pilot_and_check(pilot.pk, CheckType.PLANNED)
    assign_form.confirm_assignment()

    print("\n=== Прецедент 2. Тестирование по методике Шульте (4×4, вперемешку) ===")
    pilot_work = sign_in(storage, "pilot1", "pilot123", screen)
    clock = ScriptedClock([20, 18, 19, 22, 21])
    test_form = ui.TestingForm(ctl.TestingController(storage, pilot_work, random.Random(1)), screen, clock)
    test_form.open_testing()
    test_form.confirm_ready(4, NumberOrder.SHUFFLED)
    for _ in range(5):
        test_form.enter_numbers()

    print("\n=== Прецедент 3. Мои результаты ===")
    own_form = ui.OwnResultsForm(ctl.OwnResultsController(storage, pilot_work), screen)
    own_form.open_own_results()
    session_id = storage.sessions_of(pilot.pk)[0].pk
    own_form.choose_session(session_id)

    print("\n=== Прецедент 5. Результаты глазами психолога ===")
    review_form = ui.ReviewForm(ctl.ReviewController(storage, psychologist), screen)
    review_form.choose_pilot(pilot.pk)
    review_form.choose_session(session_id)

    print("\n=== Прецедент 6. Заключение о допуске ===")
    conclusion_form = ui.ConclusionForm(ctl.ConclusionController(storage, psychologist, safety), screen)
    conclusion_form.request_conclusion(session_id)
    conclusion_form.confirm_conclusion()

    print("\n=== Прецедент 7. Динамика (нужны две сессии) ===")
    dynamics_form = ui.DynamicsForm(ctl.DynamicsController(storage, psychologist), screen)
    dynamics_form.open_dynamics(pilot.pk)

    print("\n=== Прецедент 10. Сводный отчёт ===")
    report_form = ui.ReportForm(ctl.ReportController(storage, admin_user, safety), screen)
    report_form.open_report()
    report_form.set_period_and_group(date(2000, 1, 1), date.today(), [pilot.pk])
    print("\nУведомления:", notifier.log)


if __name__ == "__main__":
    main()

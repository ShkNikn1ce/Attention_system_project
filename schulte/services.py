"""Правила методики Шульте: показатели, допуск, динамика, отчёт."""
from __future__ import annotations

import random
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from schulte.models import (
    AdmissionNorm, Conclusion, Notification, ReportLine, SecurityHandoff, SchulteTable,
    SummaryReport, TestResult, TestSession, User)

TABLE_COUNT = 5


class DomainError(Exception):
    """Нарушение правила предметной области."""


def calculate(times: list[float]) -> tuple[float, float, float]:
    """ЭР = (T1+...+T5)/5, ВР = T1/ЭР, ПУ = T4/ЭР."""
    if len(times) != TABLE_COUNT:
        raise DomainError("Для расчёта нужно время прохождения ровно пяти таблиц")
    if any(t is None or t <= 0 for t in times):
        raise DomainError("Время прохождения таблицы должно быть положительным")
    efficiency = sum(times) / TABLE_COUNT
    return efficiency, times[0] / efficiency, times[3] / efficiency


def suggest_decision(result: TestResult, norm: AdmissionNorm) -> str:
    """Все показатели в норме — годен, иначе направление на обследование."""
    if norm.contains(result):
        return Conclusion.Decision.FIT
    return Conclusion.Decision.EXTRA


def generate_numbers(size: int, layout: str) -> list[int]:
    if size < 2:
        raise DomainError("Размер таблицы должен быть не меньше 2")
    numbers = list(range(1, size * size + 1))
    if layout == SchulteTable.Layout.SHUFFLED:
        random.shuffle(numbers)
    return numbers


def record_table(session: TestSession, order: int, size: int, layout: str,
                 numbers: list[int], time_sec: float) -> bool:
    """Сохраняет таблицу. Возвращает True, когда сессия завершена пятой таблицей."""
    if time_sec <= 0:
        raise DomainError("Время прохождения должно быть положительным")
    if size < 2:
        raise DomainError("Размер таблицы должен быть не меньше 2")
    if session.status != TestSession.Status.ASSIGNED:
        raise DomainError(
            f"Сессия в состоянии «{session.get_status_display().lower()}» не может быть продолжена")
    with transaction.atomic():
        locked = TestSession.objects.select_for_update().get(pk=session.pk)
        if locked.status != TestSession.Status.ASSIGNED:
            raise DomainError("Сессия уже завершена или отменена")
        if not SchulteTable.objects.filter(session=locked, order=order).exists():
            SchulteTable.objects.create(
                session=locked, order=order, size=size, layout=layout,
                numbers=numbers, time_sec=time_sec)
        saved = list(locked.tables.order_by("order"))
        if len(saved) < TABLE_COUNT:
            return False
        if TestResult.objects.filter(session=locked).exists():
            return True
        efficiency, warmup, stability = calculate([table.time_sec for table in saved[:TABLE_COUNT]])
        TestResult.objects.create(session=locked, er=efficiency, vr=warmup, pu=stability)
        locked.status = TestSession.Status.COMPLETED
        locked.save(update_fields=["status"])
        session.status = locked.status
        return True


def cancel_session(session: TestSession) -> None:
    if session.status != TestSession.Status.ASSIGNED:
        raise DomainError(
            f"Сессия в состоянии «{session.get_status_display().lower()}» не может стать «отменена»")
    with transaction.atomic():
        locked = TestSession.objects.select_for_update().get(pk=session.pk)
        locked.tables.all().delete()
        locked.status = TestSession.Status.CANCELLED
        locked.save(update_fields=["status"])
        session.status = locked.status


def assign_session(psychologist: User, pilot: User, check_type: str) -> TestSession:
    if pilot.role != User.Role.PILOT:
        raise DomainError("Тестирование назначается только пилоту")
    moment = timezone.now()
    with transaction.atomic():
        session = TestSession.objects.create(
            pilot=pilot, psychologist=psychologist, scheduled_at=moment, check_type=check_type)
        Notification.objects.create(
            recipient=pilot,
            text=(
                f"{pilot.display_name()}: назначена {session.get_check_type_display().lower()} "
                f"проверка на {timezone.localtime(moment):%Y-%m-%d %H:%M}"
            ),
        )
    return session


def save_conclusion(result: TestResult, psychologist: User, norm: AdmissionNorm,
                    decision: str, comment: str) -> Conclusion:
    with transaction.atomic():
        conclusion = Conclusion.objects.create(
            result=result, psychologist=psychologist, norm=norm,
            decision=decision, date=timezone.localdate(), comment=comment.strip())
        pilot = result.session.pilot
        SecurityHandoff.objects.create(
            kind=SecurityHandoff.Kind.CONCLUSION,
            summary=f"Заключение по {pilot.display_name()}: {conclusion.get_decision_display()}",
            conclusion=conclusion,
        )
    return conclusion


def save_norm(values: dict) -> AdmissionNorm:
    for title, low, high in (
        ("ЭР", values["er_min"], values["er_max"]),
        ("ВР", values["vr_min"], values["vr_max"]),
        ("ПУ", values["pu_min"], values["pu_max"]),
    ):
        if low > high:
            raise DomainError(f"Диапазон {title}: нижняя граница больше верхней")
    current = AdmissionNorm.objects.order_by("-id").first()
    if current is not None and not current.conclusions.exists():
        for key, value in values.items():
            setattr(current, key, value)
        current.save()
        return current
    return AdmissionNorm.objects.create(**values)


def dynamics_points(pilot: User) -> list[dict]:
    sessions = (
        TestSession.objects.filter(pilot=pilot, status=TestSession.Status.COMPLETED)
        .select_related("result")
        .order_by("scheduled_at", "id")
    )
    return [
        {
            "at": session.scheduled_at,
            "er": session.result.er,
            "vr": session.result.vr,
            "pu": session.result.pu,
        }
        for session in sessions
    ]


def chart_polyline(values: list[float], width: int = 640, height: int = 180, pad: int = 28) -> str:
    if not values:
        return ""
    low, high = min(values), max(values)
    if low == high:
        low -= 1
        high += 1
    span = high - low
    count = len(values)
    points = []
    for index, value in enumerate(values):
        if count == 1:
            x = width / 2
        else:
            x = pad + (width - 2 * pad) * index / (count - 1)
        y = pad + (height - 2 * pad) * (1 - (value - low) / span)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def build_report(administrator: User, start, end, pilots) -> SummaryReport:
    if start > end:
        raise DomainError("Начало периода позже его конца")
    pilot_list = list(pilots)
    if not pilot_list:
        raise DomainError("Выберите хотя бы одного пилота")
    sessions = (
        TestSession.objects.filter(
            pilot__in=pilot_list,
            status=TestSession.Status.COMPLETED,
            scheduled_at__date__gte=start,
            scheduled_at__date__lte=end,
        )
        .select_related("result", "pilot")
    )
    grouped: dict[int, list[TestResult]] = defaultdict(list)
    for session in sessions:
        grouped[session.pilot_id].append(session.result)
    if not grouped:
        raise DomainError("Нет данных за указанный период")
    with transaction.atomic():
        report = SummaryReport.objects.create(
            administrator=administrator, period_start=start, period_end=end)
        lines = []
        for pilot in sorted(pilot_list, key=lambda item: item.display_name()):
            results = grouped.get(pilot.id)
            if not results:
                continue
            count = len(results)
            lines.append(ReportLine(
                report=report, pilot=pilot, full_name=pilot.display_name(), session_count=count,
                avg_er=sum(item.er for item in results) / count,
                avg_vr=sum(item.vr for item in results) / count,
                avg_pu=sum(item.pu for item in results) / count,
            ))
        ReportLine.objects.bulk_create(lines)
        SecurityHandoff.objects.create(
            kind=SecurityHandoff.Kind.REPORT,
            summary=(
                f"Сводный отчёт {start:%Y-%m-%d}–{end:%Y-%m-%d}: пилотов {len(lines)}"
            ),
            report=report,
        )
    return report

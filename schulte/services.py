"""Правила методики Шульте: показатели, допуск, динамика, отчёт."""
from __future__ import annotations

import random
from collections import defaultdict

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from schulte.models import (
    AdmissionNorm, Conclusion, Notification, ReportLine, SecurityHandoff, SchulteTable,
    SummaryReport, TestResult, TestSession, User)

TABLE_COUNT = 5


def tables_required(_layout: str) -> int:
    """Оба порядка проходятся по пяти таблицам."""
    return TABLE_COUNT


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
    """Сохраняет таблицу. Возвращает True, когда набрано нужное число таблиц."""
    if time_sec <= 0:
        raise DomainError("Время прохождения должно быть положительным")
    if size < 2:
        raise DomainError("Размер таблицы должен быть не меньше 2")
    if session.status != TestSession.Status.ASSIGNED:
        raise DomainError(
            f"Попытка в состоянии «{session.get_status_display().lower()}» не может быть продолжена")
    with transaction.atomic():
        locked = TestSession.objects.select_for_update().get(pk=session.pk)
        if locked.status != TestSession.Status.ASSIGNED:
            raise DomainError("Попытка уже завершена или отменена")
        if not SchulteTable.objects.filter(session=locked, order=order).exists():
            SchulteTable.objects.create(
                session=locked, order=order, size=size, layout=layout,
                numbers=numbers, time_sec=time_sec)
        saved = list(locked.tables.order_by("order"))
        needed = tables_required(locked.number_order)
        if len(saved) < needed:
            return False
        if TestResult.objects.filter(session=locked).exists():
            return True
        efficiency, warmup, stability = calculate(
            [table.time_sec for table in saved[:TABLE_COUNT]])
        TestResult.objects.create(session=locked, er=efficiency, vr=warmup, pu=stability)
        locked.status = TestSession.Status.COMPLETED
        locked.save(update_fields=["status"])
        session.status = locked.status
        return True


def cancel_session(session: TestSession) -> None:
    if session.status != TestSession.Status.ASSIGNED:
        raise DomainError(
            f"Попытка в состоянии «{session.get_status_display().lower()}» не может стать «отменена»")
    with transaction.atomic():
        locked = TestSession.objects.select_for_update().get(pk=session.pk)
        locked.tables.all().delete()
        locked.status = TestSession.Status.CANCELLED
        locked.save(update_fields=["status"])
        session.status = locked.status


def assign_session(psychologist: User, pilot: User, check_type: str,
                   table_size: int = 3, layout: str = SchulteTable.Layout.ORDERED) -> TestSession:
    if pilot.role != User.Role.PILOT:
        raise DomainError("Тестирование назначается только пилоту")
    if table_size not in (3, 4, 5):
        raise DomainError("Размер таблиц должен быть 3×3, 4×4 или 5×5")
    if layout not in SchulteTable.Layout.values:
        raise DomainError("Неизвестный порядок следования чисел")
    moment = timezone.now()
    with transaction.atomic():
        session = TestSession.objects.create(
            pilot=pilot, psychologist=psychologist, scheduled_at=moment, check_type=check_type,
            table_size=table_size, number_order=layout)
        Notification.objects.create(
            recipient=pilot,
            text=(
                f"{pilot.display_name()}: назначена {session.get_check_type_display().lower()} "
                f"проверка на {timezone.localtime(moment):%Y-%m-%d %H:%M}. "
                f"Таблицы {table_size}×{table_size}, порядок: {session.get_number_order_display().lower()}."
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


def attempt_number(session: TestSession) -> int:
    """Номер завершённой попытки пилота: 1 — самая ранняя."""
    return (
        TestSession.objects.filter(pilot_id=session.pilot_id, status=TestSession.Status.COMPLETED)
        .filter(
            Q(scheduled_at__lt=session.scheduled_at)
            | Q(scheduled_at=session.scheduled_at, pk__lte=session.pk)
        )
        .count()
    )


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


def chart_series(values: list[float], digits: int = 2, width: int = 720, height: int = 280) -> dict:
    """Оси графика: по вертикали величина, по горизонтали номер попытки, точка на каждую попытку."""
    pad_left, pad_right, pad_top, pad_bottom = 78, 24, 20, 56
    low = 0.0
    high = max(values) if values else 1.0
    if high <= low:
        high = 1.0
    span = high - low
    plot_width = width - pad_left - pad_right
    plot_height = height - pad_top - pad_bottom
    count = len(values)
    coords = []
    for index, value in enumerate(values):
        fraction_x = 0.5 if count == 1 else index / (count - 1)
        coords.append({
            "x": f"{pad_left + plot_width * fraction_x:.1f}",
            "y": f"{pad_top + plot_height * (1 - (value - low) / span):.1f}",
            "attempt": index + 1,
        })
    ticks = []
    for step in range(5):
        fraction = step / 4
        value = low + span * fraction
        label = "0" if value == 0 else f"{value:.{digits}f}".replace(".", ",")
        ticks.append({
            "y": f"{pad_top + plot_height * (1 - fraction):.1f}",
            "label": label,
        })
    baseline = pad_top + plot_height
    return {
        "width": width,
        "height": height,
        "pad_left": pad_left,
        "end_x": width - pad_right,
        "top": pad_top,
        "baseline": f"{baseline:.1f}",
        "label_y": f"{baseline + 18:.1f}",
        "title_y": f"{baseline + 40:.1f}",
        "title_x": f"{pad_left + plot_width / 2:.1f}",
        "y_title_y": f"{pad_top + plot_height / 2:.1f}",
        "polyline": " ".join(f"{point['x']},{point['y']}" for point in coords),
        "coords": coords,
        "ticks": ticks,
    }


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

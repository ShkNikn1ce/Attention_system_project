"""Бизнес-службы: оценка допуска, анализ динамики, сводный отчёт."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from attention_system.business.entities import (
    AdmissionNorm, Pilot, TestResult, SummaryReport, TestSession,
    ReportLine, SchulteTable)
from attention_system.business.enums import Decision
from attention_system.markup import stereotype


@stereotype("структура данных")
@dataclass(kw_only=True)
class SuggestedConclusion:
    """Результат автоматического сопоставления показателей с нормами."""
    result: TestResult
    norm: AdmissionNorm
    decision: Decision
    within_norm: bool


@stereotype("структура данных")
@dataclass(kw_only=True)
class SessionDetails:
    session: TestSession
    tables: list[SchulteTable]
    result: TestResult


@stereotype("структура данных")
@dataclass(kw_only=True)
class DynamicsPoint:
    occurred_at: datetime
    er: float
    vr: float
    pu: float


@stereotype("структура данных")
@dataclass(kw_only=True)
class DynamicsChart:
    points: list[DynamicsPoint] = field(default_factory=list)

    def as_text(self) -> str:
        lines = ["Дата и время       ЭР     ВР     ПУ"]
        for t in self.points:
            lines.append(f"{t.occurred_at:%Y-%m-%d %H:%M}  {t.er:6.2f} {t.vr:6.3f} {t.pu:6.3f}")
        return "\n".join(lines)


@stereotype("служба")
class Admission:
    @staticmethod
    def suggest(result: TestResult, norm: AdmissionNorm) -> Decision:
        """Все показатели в норме -> годен, иначе -> направление на обследование."""
        if norm.matches(result):
            return Decision.FIT
        return Decision.EXTRA_EXAM


@stereotype("служба")
class DynamicsAnalysis:
    @staticmethod
    def build(pairs: list[tuple[TestSession, TestResult]]) -> DynamicsChart:
        points = [DynamicsPoint(occurred_at=s.occurred_at, er=r.er, vr=r.vr, pu=r.pu) for s, r in pairs]
        points.sort(key=lambda t: t.occurred_at)
        return DynamicsChart(points=points)


@stereotype("служба")
class ReportService:
    @staticmethod
    def aggregate(pilots: list[Pilot],
                     payload: list[tuple[TestSession, TestResult]],
                     admin_id: int, start: date, end: date) -> SummaryReport:
        by_pilot: dict[int, list[TestResult]] = defaultdict(list)
        for session, result in payload:
            by_pilot[session.pilot_id].append(result)
        report = SummaryReport(admin_id=admin_id, period_start=start,
                             period_end=end, created_at=datetime.now())
        for pilot in sorted(pilots, key=lambda p: p.full_name):
            results = by_pilot.get(pilot.pk)
            if not results:
                continue
            n = len(results)
            report.add_line(ReportLine(
                pilot_id=pilot.pk, full_name=pilot.full_name, session_count=n,
                avg_er=sum(r.er for r in results) / n,
                avg_vr=sum(r.vr for r in results) / n,
                avg_pu=sum(r.pu for r in results) / n))
        return report

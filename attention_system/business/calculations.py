"""Расчёт показателей внимания по методике Шульте."""
from __future__ import annotations

from attention_system.business.errors import DataError
from attention_system.markup import stereotype


@stereotype("служба")
class SchulteMath:
    """Формулы методики: ЭР = (T1+...+T5)/5, ВР = T1/ЭР, ПУ = T4/ЭР."""

    TABLE_COUNT = 5

    @staticmethod
    def calculate(times: list[float]) -> tuple[float, float, float]:
        if len(times) != SchulteMath.TABLE_COUNT:
            raise DataError("Для расчёта нужно время прохождения ровно пяти таблиц")
        if any(t is None or t <= 0 for t in times):
            raise DataError("Время прохождения таблицы должно быть положительным")
        er = sum(times) / SchulteMath.TABLE_COUNT
        vr = times[0] / er
        pu = times[3] / er
        return er, vr, pu

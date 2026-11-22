"""Тесты бизнес-правил: формулы методики Шульте, оценка допуска, динамика, отчёты."""
import unittest
from datetime import date, datetime

from tests import helpers  # noqa: F401  (ускоренное хэширование)
from attention_system.business.calculations import SchulteMath
from attention_system.business.entities import AdmissionNorm, Pilot, TestResult, TestSession
from attention_system.business.enums import Decision, CheckType
from attention_system.business.errors import DataError
from attention_system.business.services import DynamicsAnalysis, Admission, ReportService


class SchulteFormulaTests(unittest.TestCase):
    def verify(self, times, er, vr, pu):
        e, v, p = SchulteMath.calculate(times)
        self.assertAlmostEqual(e, er, places=4)
        self.assertAlmostEqual(v, vr, places=4)
        self.assertAlmostEqual(p, pu, places=4)

    def test_tables_3x3_shuffled(self):
        """Расчёт по данным 3×3 вперемешку: 8, 9, 8, 7, 9 с."""
        self.verify([8, 9, 8, 7, 9], 8.2, 8 / 8.2, 7 / 8.2)

    def test_tables_3x3_ordered(self):
        """Расчёт по данным 3×3 по порядку: 4, 3, 4, 4, 4 с."""
        self.verify([4, 3, 4, 4, 4], 3.8, 4 / 3.8, 4 / 3.8)

    def test_tables_4x4_ordered(self):
        """Расчёт по данным 4×4 по порядку: 10, 10, 11, 10, 10 с."""
        self.verify([10, 10, 11, 10, 10], 10.2, 10 / 10.2, 10 / 10.2)

    def test_tables_4x4_shuffled(self):
        """Расчёт по данным 4×4 вперемешку: 20, 18, 19, 22, 21 с."""
        self.verify([20, 18, 19, 22, 21], 20.0, 1.0, 1.1)

    def test_not_five_tables(self):
        """Расчёт отклоняется, если таблиц не пять."""
        with self.assertRaises(DataError):
            SchulteMath.calculate([1, 2, 3, 4])

    def test_non_positive_time(self):
        """Расчёт отклоняется при нулевом или отрицательном времени."""
        with self.assertRaises(DataError):
            SchulteMath.calculate([5, 5, 0, 5, 5])
        with self.assertRaises(DataError):
            SchulteMath.calculate([5, 5, -1, 5, 5])


class AdmissionTests(unittest.TestCase):
    norm = AdmissionNorm(er_min=3, er_max=25, vr_min=0.8, vr_max=1.1, pu_min=0.8, pu_max=1.1)

    def test_within_norm(self):
        """Все показатели в пределах нормы — решение «годен»."""
        r = TestResult(session_id=1, er=10, vr=1.0, pu=1.0)
        self.assertEqual(Admission.suggest(r, self.norm), Decision.FIT)

    def test_pu_outside_norm(self):
        """ПУ выше верхней границы — направление на дополнительное обследование."""
        r = TestResult(session_id=1, er=10, vr=1.0, pu=1.2)
        self.assertEqual(Admission.suggest(r, self.norm), Decision.EXTRA_EXAM)

    def test_bounds_are_inclusive(self):
        """Значения на границах диапазонов считаются нормой."""
        r = TestResult(session_id=1, er=25, vr=0.8, pu=1.1)
        self.assertTrue(self.norm.matches(r))


class DynamicsAndReportTests(unittest.TestCase):
    def test_chart_ordered_by_date(self):
        """Точки графика динамики упорядочены по дате сессии."""
        s1 = TestSession(pilot_id=1, psychologist_id=2, occurred_at=datetime(2026, 5, 2), check_type=CheckType.PLANNED)
        s2 = TestSession(pilot_id=1, psychologist_id=2, occurred_at=datetime(2026, 5, 1), check_type=CheckType.PLANNED)
        chart = DynamicsAnalysis.build([(s1, TestResult(session_id=1, er=9)),
                                           (s2, TestResult(session_id=2, er=8))])
        self.assertEqual([t.er for t in chart.points], [8, 9])
        self.assertIn("ЭР", chart.as_text())

    def test_averages(self):
        """Отчёт считает средние ЭР, ВР, ПУ по каждому пилоту."""
        pilot = Pilot(login="a", password_hash="x", full_name="Иванов", employee_number="1", pk=5)
        s = TestSession(pilot_id=5, psychologist_id=2, occurred_at=datetime(2026, 5, 1), check_type=CheckType.PLANNED)
        payload = [(s, TestResult(session_id=1, er=10, vr=1.0, pu=1.0)),
                  (s, TestResult(session_id=2, er=20, vr=0.8, pu=1.2))]
        report = ReportService.aggregate([pilot], payload, 1, date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(len(report.lines), 1)
        row = report.lines[0]
        self.assertEqual(row.session_count, 2)
        self.assertAlmostEqual(row.avg_er, 15)
        self.assertAlmostEqual(row.avg_vr, 0.9)
        self.assertAlmostEqual(row.avg_pu, 1.1)
        self.assertEqual(report.pilot_ids(), [5])


if __name__ == "__main__":
    unittest.main()

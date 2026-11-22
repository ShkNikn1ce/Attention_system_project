"""Тесты классов-сущностей."""
import random
import unittest
from datetime import datetime

from tests import helpers  # noqa: F401
from attention_system.business.entities import (
    AdmissionNorm, Pilot, User, TestResult, TestSession, SchulteTable)
from attention_system.business.enums import NumberOrder, Role, SessionStatus, CheckType
from attention_system.business.errors import DataError, StateError
from attention_system.middleware.password import PasswordHash


def fresh_session():
    return TestSession(pilot_id=1, psychologist_id=2, occurred_at=datetime.now(), check_type=CheckType.PLANNED)


class SessionStateTests(unittest.TestCase):
    def test_initial_state(self):
        """Новая сессия находится в состоянии «назначена»."""
        self.assertTrue(fresh_session().is_assigned())

    def test_complete(self):
        """Назначенная сессия может быть завершена."""
        s = fresh_session()
        s.complete()
        self.assertEqual(s.status, SessionStatus.COMPLETED)

    def test_cancel(self):
        """Назначенная сессия может быть отменена."""
        s = fresh_session()
        s.cancel()
        self.assertEqual(s.status, SessionStatus.CANCELLED)

    def test_completed_cannot_be_cancelled(self):
        """Завершённую сессию нельзя отменить."""
        s = fresh_session()
        s.complete()
        with self.assertRaises(StateError):
            s.cancel()

    def test_cancelled_cannot_be_completed(self):
        """Отменённую сессию нельзя завершить."""
        s = fresh_session()
        s.cancel()
        with self.assertRaises(StateError):
            s.complete()


class SchulteTableTests(unittest.TestCase):
    def table(self, size, layout):
        return SchulteTable(session_id=1, order_no=1, size=size, number_order=layout)

    def test_ordered_numbers(self):
        """Числа «по порядку» идут от 1 до n²."""
        self.assertEqual(self.table(3, NumberOrder.ORDERED).generate_numbers(), list(range(1, 10)))

    def test_shuffled_is_permutation(self):
        """Числа «вперемешку» — перестановка чисел от 1 до n², отличная от упорядоченной."""
        numbers = self.table(4, NumberOrder.SHUFFLED).generate_numbers(random.Random(3))
        self.assertEqual(sorted(numbers), list(range(1, 17)))
        self.assertNotEqual(numbers, list(range(1, 17)))

    def test_size_too_small(self):
        """Таблица размером меньше 2×2 не создаётся."""
        with self.assertRaises(DataError):
            self.table(1, NumberOrder.ORDERED).generate_numbers()

    def test_time_must_be_positive(self):
        """Время прохождения должно быть положительным."""
        t = self.table(3, NumberOrder.ORDERED)
        with self.assertRaises(DataError):
            t.record_time(0)
        t.record_time(4.5)
        self.assertEqual(t.time_sec, 4.5)


class NormAndUserTests(unittest.TestCase):
    def test_ranges_are_valid(self):
        """Норма с нижней границей выше верхней отклоняется."""
        n = AdmissionNorm(er_min=10, er_max=5, vr_min=0.8, vr_max=1.1, pu_min=0.8, pu_max=1.1)
        with self.assertRaises(DataError):
            n.check_ranges()

    def test_valid_norm(self):
        """Норма с корректными диапазонами проходит проверку."""
        AdmissionNorm(er_min=3, er_max=25, vr_min=0.8, vr_max=1.1, pu_min=0.8, pu_max=1.1).check_ranges()

    def test_password_is_hashed(self):
        """Пароль не хранится открыто и проверяется по хэшу."""
        digest = PasswordHash.make("секрет1")
        self.assertNotIn("секрет1", digest)
        p = User(login="u", password_hash=digest, role=Role.PILOT)
        self.assertTrue(p.check_password("секрет1"))
        self.assertFalse(p.check_password("другой"))

    def test_salt_differs(self):
        """Один и тот же пароль даёт разные хэши (разная соль)."""
        self.assertNotEqual(PasswordHash.make("abc"), PasswordHash.make("abc"))

    def test_pilot_subclass(self):
        """Пилот является пользователем с ролью «пилот»."""
        p = Pilot(login="p", password_hash="x", full_name="Ф", employee_number="1")
        self.assertIsInstance(p, User)
        self.assertEqual(p.resolve_role(), Role.PILOT)

    def test_result_calculates_metrics(self):
        """Результат рассчитывает ЭР, ВР, ПУ по пяти временам."""
        r = TestResult(session_id=1)
        r.calculate_metrics([20, 18, 19, 22, 21])
        self.assertAlmostEqual(r.er, 20.0)
        self.assertAlmostEqual(r.pu, 1.1)


if __name__ == "__main__":
    unittest.main()

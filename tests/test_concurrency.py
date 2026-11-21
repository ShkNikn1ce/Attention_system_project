"""Тест нефункционального требования: не менее 50 пилотов проходят тестирование одновременно."""
import random
import unittest

from tests.helpers import Среда
from attention_system.application import controllers as К
from attention_system.application import forms as Ф
from attention_system.application.screen import Экран
from attention_system.application.server import СерверПриложения
from attention_system.business.enums import СтатусСессии
from attention_system.middleware.clock import СекундомерПоСценарию


class ТестПараллельногоТестирования(unittest.TestCase):
    def test_пятьдесят_пилотов_одновременно(self):
        """50 пилотов одновременно проходят тестирование: все результаты сохранены без искажений."""
        среда = Среда(спилотом=False)
        пилоты = [среда.новыйПилот(f"p{i}", f"N-{i}", f"Пилот {i}") for i in range(50)]
        сессии = {п.код: среда.назначить(п) for п in пилоты}
        сервер = СерверПриложения(максПотоков=50)

        def задача(пилот):
            форма = Ф.ФормаТестирования(
                К.КонтроллерТестирования(среда.хранилище, среда.сеанс(пилот), random.Random(пилот.код)),
                Экран(), СекундомерПоСценарию([10, 10, 10, 10, 10]))
            форма.выбратьТестирование()
            форма.подтвердитьГотовность()
            for _ in range(5):
                форма.указатьЧисла()
            return форма.результат

        задания = [сервер.выполнить(lambda п=п: задача(п)) for п in пилоты]
        результаты = [з.result(timeout=60) for з in задания]
        сервер.остановить()
        self.assertEqual(len(результаты), 50)
        for п in пилоты:
            сессия = среда.хранилище.найтиСессию(сессии[п.код].код)
            self.assertEqual(сессия.статус, СтатусСессии.ЗАВЕРШЕНА)
            р = среда.хранилище.найтиРезультатСессии(сессия.код)
            self.assertAlmostEqual(р.эр, 10.0)
            self.assertEqual(len(среда.хранилище.найтиТаблицыСессии(сессия.код)), 5)


if __name__ == "__main__":
    unittest.main()

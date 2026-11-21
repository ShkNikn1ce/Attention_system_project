"""Запускает все тесты и сохраняет результаты (идентификатор, описание, статус) в diagrams/test_results.json."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


class Сбор(unittest.TextTestResult):
    записи = []

    def _записать(self, тест, статус):
        Сбор.записи.append({"модуль": тест.__class__.__module__.split(".")[-1], "класс": тест.__class__.__name__,
                            "имя": тест._testMethodName, "описание": (тест.shortDescription() or ""), "статус": статус})

    def addSuccess(self, тест):
        super().addSuccess(тест); self._записать(тест, "пройден")

    def addFailure(self, тест, err):
        super().addFailure(тест, err); self._записать(тест, "НЕ ПРОЙДЕН")

    def addError(self, тест, err):
        super().addError(тест, err); self._записать(тест, "ОШИБКА")


набор = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
итог = unittest.TextTestRunner(resultclass=Сбор, verbosity=0).run(набор)
pathlib.Path("diagrams/test_results.json").write_text(json.dumps(Сбор.записи, ensure_ascii=False, indent=1), encoding="utf-8")
print("всего:", итог.testsRun, "ошибок:", len(итог.errors), "падений:", len(итог.failures))

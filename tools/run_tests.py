"""Запускает все тесты и сохраняет результаты (идентификатор, описание, статус) в diagrams/test_results.json."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))


class CollectingResult(unittest.TextTestResult):
    rows_out = []

    def _record(self, test, status):
        CollectingResult.rows_out.append({"модуль": test.__class__.__module__.split(".")[-1], "класс": test.__class__.__name__,
                            "имя": test._testMethodName, "описание": (test.shortDescription() or ""), "статус": status})

    def addSuccess(self, test):
        super().addSuccess(test); self._record(test, "пройден")

    def addFailure(self, test, err):
        super().addFailure(test, err); self._record(test, "НЕ ПРОЙДЕН")

    def addError(self, test, err):
        super().addError(test, err); self._record(test, "ОШИБКА")


suite = unittest.defaultTestLoader.discover("tests", top_level_dir=".")
outcome = unittest.TextTestRunner(resultclass=CollectingResult, verbosity=0).run(suite)
pathlib.Path("diagrams/test_results.json").write_text(json.dumps(CollectingResult.rows_out, ensure_ascii=False, indent=1), encoding="utf-8")
print("всего:", outcome.testsRun, "ошибок:", len(outcome.errors), "падений:", len(outcome.failures))

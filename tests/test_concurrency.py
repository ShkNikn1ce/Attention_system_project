"""Тест нефункционального требования: не менее 50 пилотов проходят тестирование одновременно."""
import random
import unittest

from tests.helpers import World
from attention_system.application import controllers as ctl
from attention_system.application import forms as ui
from attention_system.application.screen import Screen
from attention_system.application.server import AppServer
from attention_system.business.enums import SessionStatus
from attention_system.middleware.clock import ScriptedClock


class ParallelTestingTests(unittest.TestCase):
    def test_fifty_pilots_at_once(self):
        """50 пилотов одновременно проходят тестирование: все результаты сохранены без искажений."""
        world = World(with_pilot=False)
        pilots = [world.new_pilot(f"p{i}", f"N-{i}", f"Пилот {i}") for i in range(50)]
        sessions = {p.pk: world.assign(p) for p in pilots}
        server = AppServer(max_workers=50)

        def task(pilot):
            form = ui.TestingForm(
                ctl.TestingController(world.storage, world.work(pilot), random.Random(pilot.pk)),
                Screen(), ScriptedClock([10, 10, 10, 10, 10]))
            form.open_testing()
            form.confirm_ready()
            for _ in range(5):
                form.enter_numbers()
            return form.result

        jobs = [server.submit(lambda p=p: task(p)) for p in pilots]
        results = [job.result(timeout=60) for job in jobs]
        server.stop()
        self.assertEqual(len(results), 50)
        for p in pilots:
            session = world.storage.session_by_id(sessions[p.pk].pk)
            self.assertEqual(session.status, SessionStatus.COMPLETED)
            r = world.storage.result_of(session.pk)
            self.assertAlmostEqual(r.er, 10.0)
            self.assertEqual(len(world.storage.tables_of(session.pk)), 5)


if __name__ == "__main__":
    unittest.main()

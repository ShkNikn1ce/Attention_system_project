"""Общая тестовая среда: хранилище в памяти, учётные записи, нормы и вспомогательные сценарии."""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

from attention_system.application import controllers as ctl
from attention_system.application import forms as ui
from attention_system.application.screen import Screen
from attention_system.business.entities import (
    Administrator, Psychologist, AdmissionNorm, Pilot, TestSession)
from attention_system.business.enums import NumberOrder, CheckType
from attention_system.middleware.clock import ScriptedClock
from attention_system.middleware.external import MemorySafetyService, MemoryNotifier
from attention_system.middleware.password import PasswordHash
from attention_system.middleware.security import WorkSession
from attention_system.middleware.storage import SqliteStorage

PasswordHash.ITERATIONS = 1000  # в тестах хэширование ускорено; алгоритм тот же


class World:
    """Готовая система: администратор, психолог, пилот, действующая норма допуска."""

    def __init__(self, with_pilot: bool = True, with_norm: bool = True) -> None:
        self.storage = SqliteStorage()
        self.notifier = MemoryNotifier()
        self.safety = MemorySafetyService()
        self.screen = Screen()
        self.admin_user = Administrator(login="admin", password_hash=PasswordHash.make("admin123"), full_name="Админов А.А.")
        self.storage.create_administrator(self.admin_user)
        self.psychologist = Psychologist(login="psy", password_hash=PasswordHash.make("psy12345"), full_name="Петрова А.С.")
        self.storage.create_psychologist(self.psychologist)
        self.pilot: Optional[Pilot] = None
        if with_pilot:
            self.pilot = self.new_pilot("pilot1", "T-001", "Шкодин Н.Р.")
        self.norm: Optional[AdmissionNorm] = None
        if with_norm:
            self.norm = AdmissionNorm(er_min=3, er_max=25, vr_min=0.8, vr_max=1.1, pu_min=0.8, pu_max=1.1)
            self.storage.create_norm(self.norm)

    def new_pilot(self, login: str, badge: str, full_name: str) -> Pilot:
        pilot = Pilot(login=login, password_hash=PasswordHash.make("pilot123"), full_name=full_name,
                      employee_number=badge, position="КВС")
        self.storage.create_pilot(pilot)
        return pilot

    @staticmethod
    def work(user) -> WorkSession:
        return WorkSession(user, datetime.now())

    def assign(self, pilot: Optional[Pilot] = None, moment: Optional[datetime] = None) -> TestSession:
        pilot = pilot or self.pilot
        session = TestSession(pilot_id=pilot.pk, psychologist_id=self.psychologist.pk,
                                    occurred_at=moment or datetime.now(), check_type=CheckType.PLANNED)
        self.storage.create_session(session)
        return session

    def finish_run(self, times: list[float], pilot: Optional[Pilot] = None, size: int = 3,
               layout: NumberOrder = NumberOrder.ORDERED,
               moment: Optional[datetime] = None) -> TestSession:
        """Назначает сессию и проходит все пять таблиц через форму тестирования."""
        pilot = pilot or self.pilot
        session = self.assign(pilot, moment)
        form = ui.TestingForm(ctl.TestingController(self.storage, self.work(pilot), random.Random(7)),
                                    Screen(), ScriptedClock(times))
        form.open_testing()
        form.confirm_ready(size, layout)
        for _ in range(5):
            form.enter_numbers()
        return self.storage.session_by_id(session.pk)

    def same_moment(self, moment: datetime) -> datetime:
        return moment

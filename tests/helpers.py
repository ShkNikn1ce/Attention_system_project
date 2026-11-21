"""Общая тестовая среда: хранилище в памяти, учётные записи, нормы и вспомогательные сценарии."""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

from attention_system.application import controllers as К
from attention_system.application import forms as Ф
from attention_system.application.screen import Экран
from attention_system.business.entities import (
    Администратор, АвиационныйПсихолог, НормаДопуска, Пилот, СессияТестирования)
from attention_system.business.enums import РасположениеЧисел, ТипПроверки
from attention_system.middleware.clock import СекундомерПоСценарию
from attention_system.middleware.external import СлужбаБезопасностиВПамяти, УведомленияВПамяти
from attention_system.middleware.password import ХэшПароля
from attention_system.middleware.security import Сеанс
from attention_system.middleware.storage import ХранилищеSQLite

ХэшПароля.ИТЕРАЦИИ = 1000  # в тестах хэширование ускорено; алгоритм тот же


class Среда:
    """Готовая система: администратор, психолог, пилот, действующая норма допуска."""

    def __init__(self, спилотом: bool = True, снормой: bool = True) -> None:
        self.хранилище = ХранилищеSQLite()
        self.уведомления = УведомленияВПамяти()
        self.служба = СлужбаБезопасностиВПамяти()
        self.экран = Экран()
        self.админ = Администратор(логин="admin", хэшПароля=ХэшПароля.создать("admin123"), фио="Админов А.А.")
        self.хранилище.создатьАдминистратора(self.админ)
        self.психолог = АвиационныйПсихолог(логин="psy", хэшПароля=ХэшПароля.создать("psy12345"), фио="Петрова А.С.")
        self.хранилище.создатьПсихолога(self.психолог)
        self.пилот: Optional[Пилот] = None
        if спилотом:
            self.пилот = self.новыйПилот("pilot1", "T-001", "Шкодин Н.Р.")
        self.норма: Optional[НормаДопуска] = None
        if снормой:
            self.норма = НормаДопуска(эрМин=3, эрМакс=25, врМин=0.8, врМакс=1.1, пуМин=0.8, пуМакс=1.1)
            self.хранилище.создатьНорму(self.норма)

    def новыйПилот(self, логин: str, табельный: str, фио: str) -> Пилот:
        пилот = Пилот(логин=логин, хэшПароля=ХэшПароля.создать("pilot123"), фио=фио,
                      табельныйНомер=табельный, должность="КВС")
        self.хранилище.создатьПилота(пилот)
        return пилот

    @staticmethod
    def сеанс(пользователь) -> Сеанс:
        return Сеанс(пользователь, datetime.now())

    def назначить(self, пилот: Optional[Пилот] = None, момент: Optional[datetime] = None) -> СессияТестирования:
        пилот = пилот or self.пилот
        сессия = СессияТестирования(кодПилота=пилот.код, кодПсихолога=self.психолог.код,
                                    датаВремя=момент or datetime.now(), типПроверки=ТипПроверки.ПЛАНОВАЯ)
        self.хранилище.создатьСессию(сессия)
        return сессия

    def пройти(self, времена: list[float], пилот: Optional[Пилот] = None, размер: int = 3,
               расположение: РасположениеЧисел = РасположениеЧисел.ПО_ПОРЯДКУ,
               момент: Optional[datetime] = None) -> СессияТестирования:
        """Назначает сессию и проходит все пять таблиц через форму тестирования."""
        пилот = пилот or self.пилот
        сессия = self.назначить(пилот, момент)
        форма = Ф.ФормаТестирования(К.КонтроллерТестирования(self.хранилище, self.сеанс(пилот), random.Random(7)),
                                    Экран(), СекундомерПоСценарию(времена))
        форма.выбратьТестирование()
        форма.подтвердитьГотовность(размер, расположение)
        for _ in range(5):
            форма.указатьЧисла()
        return self.хранилище.найтиСессию(сессия.код)

    def заново(self, момент: datetime) -> datetime:
        return момент

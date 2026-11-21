"""Сеанс работы пользователя и контроль доступа."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from attention_system.business.enums import Роль
from attention_system.business.errors import ОшибкаДоступа
from attention_system.markup import стереотип

if TYPE_CHECKING:
    from attention_system.business.entities import Пользователь


@стереотип("структура данных")
class Сеанс:
    """Результат успешного входа: кто работает и с какого момента."""

    def __init__(self, пользователь: Пользователь, начало: datetime) -> None:
        self.пользователь: Пользователь = пользователь
        self.начало: datetime = начало

    def роль(self) -> Роль:
        return self.пользователь.определитьРоль()


@стереотип("служба")
class КонтрольДоступа:
    @staticmethod
    def требоватьРоль(сеанс: Сеанс, *допустимые: Роль) -> None:
        if сеанс.роль() not in допустимые:
            raise ОшибкаДоступа(
                f"Операция недоступна для роли «{сеанс.роль().названиеРоли()}»")

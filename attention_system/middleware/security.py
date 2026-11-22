"""Сеанс работы пользователя и контроль доступа."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from attention_system.business.enums import Role
from attention_system.business.errors import AccessError
from attention_system.markup import stereotype

if TYPE_CHECKING:
    from attention_system.business.entities import User


@stereotype("структура данных")
class WorkSession:
    """Результат успешного входа: кто работает и с какого момента."""

    def __init__(self, user: User, start: datetime) -> None:
        self.user: User = user
        self.start: datetime = start

    def role(self) -> Role:
        return self.user.resolve_role()


@stereotype("служба")
class Access:
    @staticmethod
    def require(work: WorkSession, *allowed: Role) -> None:
        if work.role() not in allowed:
            raise AccessError(
                f"Операция недоступна для роли «{work.role().label()}»")

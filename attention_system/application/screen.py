"""Экран: простейший вывод сообщений пользователю (консоль и журнал для проверки)."""
from __future__ import annotations

from attention_system.markup import стереотип


@стереотип("граничный")
class Экран:
    def __init__(self, печатать: bool = False) -> None:
        self.журнал: list[str] = []
        self._печатать: bool = печатать

    def вывести(self, сообщение: str) -> None:
        self.журнал.append(сообщение)
        if self._печатать:
            print(сообщение)

    def последнее(self) -> str:
        return self.журнал[-1] if self.журнал else ""

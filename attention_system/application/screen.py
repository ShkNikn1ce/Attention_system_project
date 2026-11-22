"""Экран: простейший вывод сообщений пользователю (консоль и журнал для проверки)."""
from __future__ import annotations

from attention_system.markup import stereotype


@stereotype("граничный")
class Screen:
    def __init__(self, echo: bool = False) -> None:
        self.log: list[str] = []
        self._echo: bool = echo

    def show(self, message: str) -> None:
        self.log.append(message)
        if self._echo:
            print(message)

    def last(self) -> str:
        return self.log[-1] if self.log else ""

"""Структура потоков управления: сервер обрабатывает сеансы пользователей параллельно."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from attention_system.markup import стереотип


@стереотип("процесс")
class СерверПриложения:
    """Активный класс: владеет пулом потоков, каждый сеанс пользователя выполняется в своём потоке."""

    def __init__(self, максПотоков: int = 50) -> None:
        self._пул: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=максПотоков)

    def выполнить(self, задача: Callable[[], object]) -> Future:
        return self._пул.submit(задача)

    def остановить(self) -> None:
        self._пул.shutdown(wait=True)

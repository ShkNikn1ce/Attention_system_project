"""Структура потоков управления: сервер обрабатывает сеансы пользователей параллельно."""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from attention_system.markup import stereotype


@stereotype("процесс")
class AppServer:
    """Активный класс: владеет пулом потоков, каждый сеанс пользователя выполняется в своём потоке."""

    def __init__(self, max_workers: int = 50) -> None:
        self._pool: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, task: Callable[[], object]) -> Future:
        return self._pool.submit(task)

    def stop(self) -> None:
        self._pool.shutdown(wait=True)

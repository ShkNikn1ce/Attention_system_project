"""Исключения предметной области."""


class DomainError(Exception):
    """Базовое исключение системы."""


class DataError(DomainError):
    """Некорректные или конфликтующие данные."""


class StateError(DomainError):
    """Операция недопустима в текущем состоянии объекта."""


class AccessError(DomainError):
    """У пользователя нет прав на операцию."""


class NotFoundError(DomainError):
    """Запрошенные данные отсутствуют."""


class LoginError(DomainError):
    """Неверный логин или пароль."""


class LockoutError(LoginError):
    """Превышено число попыток входа."""

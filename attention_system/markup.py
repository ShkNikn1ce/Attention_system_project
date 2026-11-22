"""Пометка классов стереотипами UML (используется при построении диаграмм классов проекта)."""


def stereotype(name: str):
    """Декоратор: сохраняет в классе стереотип UML (граничный, управляющий, сущность и т.д.)."""

    def wrap(cls_node):
        cls_node.__stereotype__ = name
        return cls_node

    return wrap

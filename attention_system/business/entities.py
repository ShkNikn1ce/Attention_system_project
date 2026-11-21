"""Классы-сущности предметной области (бизнес-уровень)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from attention_system.business.calculations import РасчётПоказателей
from attention_system.business.enums import (
    РасположениеЧисел, РешениеОДопуске, Роль, СтатусСессии, ТипПроверки)
from attention_system.business.errors import ОшибкаДанных, ОшибкаСостояния
from attention_system.markup import стереотип
from attention_system.middleware.password import ХэшПароля


@стереотип("сущность")
@dataclass(kw_only=True)
class Пользователь:
    """Учётная запись пользователя системы."""
    логин: str
    хэшПароля: str
    роль: Роль
    последнийВход: Optional[datetime] = None
    код: Optional[int] = None

    def проверитьПароль(self, пароль: str) -> bool:
        return ХэшПароля.проверить(пароль, self.хэшПароля)

    def определитьРоль(self) -> Роль:
        return self.роль

    def отметитьВход(self, момент: datetime) -> None:
        self.последнийВход = момент


@стереотип("сущность")
@dataclass(kw_only=True)
class Пилот(Пользователь):
    """Пилот авиакомпании (подкласс пользователя)."""
    роль: Роль = Роль.ПИЛОТ
    фио: str
    табельныйНомер: str
    должность: str = ""


@стереотип("сущность")
@dataclass(kw_only=True)
class АвиационныйПсихолог(Пользователь):
    роль: Роль = Роль.ПСИХОЛОГ
    фио: str


@стереотип("сущность")
@dataclass(kw_only=True)
class Администратор(Пользователь):
    роль: Роль = Роль.АДМИНИСТРАТОР
    фио: str


@стереотип("сущность")
@dataclass(kw_only=True)
class СессияТестирования:
    """Одно прохождение пилотом комплекта из пяти таблиц Шульте.
    Объект зависит от состояния: назначена -> завершена | отменена."""
    кодПилота: int
    кодПсихолога: int
    датаВремя: datetime
    типПроверки: ТипПроверки
    методика: str = "Шульте"
    статус: СтатусСессии = СтатусСессии.НАЗНАЧЕНА
    код: Optional[int] = None

    def назначена(self) -> bool:
        return self.статус == СтатусСессии.НАЗНАЧЕНА

    def завершить(self) -> None:
        self.__перейти(СтатусСессии.ЗАВЕРШЕНА)

    def отменить(self) -> None:
        self.__перейти(СтатусСессии.ОТМЕНЕНА)

    def __перейти(self, новый: СтатусСессии) -> None:
        if self.статус != СтатусСессии.НАЗНАЧЕНА:
            raise ОшибкаСостояния(
                f"Сессия в состоянии «{self.статус.value}» не может стать «{новый.value}»")
        self.статус = новый


@стереотип("сущность")
@dataclass(kw_only=True)
class ТаблицаШульте:
    """Таблица n×n с числами от 1 до n²."""
    кодСессии: int
    номерПоПорядку: int
    размер: int
    расположениеЧисел: РасположениеЧисел
    времяСек: Optional[float] = None
    числа: list[int] = field(default_factory=list)
    код: Optional[int] = None

    def сгенерироватьЧисла(self, генератор: Optional[random.Random] = None) -> list[int]:
        if self.размер < 2:
            raise ОшибкаДанных("Размер таблицы должен быть не меньше 2")
        числа = list(range(1, self.размер ** 2 + 1))
        if self.расположениеЧисел == РасположениеЧисел.ВПЕРЕМЕШКУ:
            (генератор or random.Random()).shuffle(числа)
        self.числа = числа
        return числа

    def зафиксироватьВремя(self, секунды: float) -> None:
        if секунды <= 0:
            raise ОшибкаДанных("Время прохождения должно быть положительным")
        self.времяСек = секунды


@стереотип("сущность")
@dataclass(kw_only=True)
class РезультатТестирования:
    """Расчётные показатели сессии: ЭР, ВР, ПУ."""
    кодСессии: int
    эр: float = 0.0
    вр: float = 0.0
    пу: float = 0.0
    код: Optional[int] = None

    def рассчитатьПоказатели(self, времена: list[float]) -> None:
        self.эр, self.вр, self.пу = РасчётПоказателей.рассчитать(времена)


@стереотип("сущность")
@dataclass(kw_only=True)
class НормаДопуска:
    """Допустимые диапазоны показателей, при которых пилот годен к полётам."""
    эрМин: float
    эрМакс: float
    врМин: float
    врМакс: float
    пуМин: float
    пуМакс: float
    код: Optional[int] = None

    def проверитьДиапазоны(self) -> None:
        for название, нижняя, верхняя in (("ЭР", self.эрМин, self.эрМакс),
                                           ("ВР", self.врМин, self.врМакс),
                                           ("ПУ", self.пуМин, self.пуМакс)):
            if нижняя > верхняя:
                raise ОшибкаДанных(f"Диапазон {название}: нижняя граница больше верхней")

    def проверитьПоказатели(self, результат: РезультатТестирования) -> bool:
        return (self.эрМин <= результат.эр <= self.эрМакс
                and self.врМин <= результат.вр <= self.врМакс
                and self.пуМин <= результат.пу <= self.пуМакс)


@стереотип("сущность")
@dataclass(kw_only=True)
class ЗаключениеОДопуске:
    кодРезультата: int
    кодПсихолога: int
    кодНормы: int
    решение: РешениеОДопуске
    дата: date
    комментарий: str = ""
    код: Optional[int] = None


@стереотип("структура данных")
@dataclass(kw_only=True)
class СтрокаОтчёта:
    кодПилота: int
    фио: str
    числоСессий: int
    срЭР: float
    срВР: float
    срПУ: float


@стереотип("сущность")
@dataclass(kw_only=True)
class СводныйОтчёт:
    кодАдминистратора: int
    началоПериода: date
    конецПериода: date
    датаСоздания: datetime
    строки: list[СтрокаОтчёта] = field(default_factory=list)
    код: Optional[int] = None

    def добавитьСтроку(self, строка: СтрокаОтчёта) -> None:
        self.строки.append(строка)

    def кодыПилотов(self) -> list[int]:
        return [с.кодПилота for с in self.строки]

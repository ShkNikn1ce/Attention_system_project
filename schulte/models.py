from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models


class UserManager(DjangoUserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields["role"] = self.model.Role.ADMIN
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Учётная запись: пилот, авиационный психолог или администратор."""

    class Role(models.TextChoices):
        PILOT = "pilot", "Пилот"
        PSYCHOLOGIST = "psychologist", "Авиационный психолог"
        ADMIN = "admin", "Администратор системы"

    role = models.CharField("роль", max_length=20, choices=Role.choices)
    full_name = models.CharField("ФИО", max_length=200, blank=True)
    employee_number = models.CharField(
        "табельный номер", max_length=32, unique=True, null=True, blank=True)
    position = models.CharField("должность", max_length=120, blank=True)

    objects = UserManager()

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"

    REQUIRED_FIELDS = []

    def display_name(self) -> str:
        return self.full_name or self.get_username()

    def short_name(self) -> str:
        """Фамилия И. О. Первое слово — фамилия, остальные — инициалы."""
        parts = (self.full_name or self.get_username()).split()
        if len(parts) < 2:
            return parts[0] if parts else self.get_username()
        initials = []
        for part in parts[1:]:
            letters = [char for char in part if char.isalpha()]
            if not letters:
                continue
            if "." in part or len(letters) <= 2:
                initials.extend(f"{char.upper()}." for char in letters)
            else:
                initials.append(f"{letters[0].upper()}.")
        return f"{parts[0]} {' '.join(initials)}" if initials else parts[0]

    def __str__(self) -> str:
        return f"{self.display_name()} ({self.get_role_display()})"


class LoginThrottle(models.Model):
    """Счётчик неудачных попыток входа по логину."""

    username = models.CharField(max_length=150, unique=True)
    failures = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.username}: {self.failures}"


class AdmissionNorm(models.Model):
    """Допустимые диапазоны ЭР, ВР и ПУ. Новая запись — новая версия нормы."""

    er_min = models.FloatField("ЭР, нижняя граница")
    er_max = models.FloatField("ЭР, верхняя граница")
    vr_min = models.FloatField("ВР, нижняя граница")
    vr_max = models.FloatField("ВР, верхняя граница")
    pu_min = models.FloatField("ПУ, нижняя граница")
    pu_max = models.FloatField("ПУ, верхняя граница")
    created_at = models.DateTimeField("создана", auto_now_add=True)

    class Meta:
        verbose_name = "норма допуска"
        verbose_name_plural = "нормы допуска"
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(er_min__lte=models.F("er_max")), name="norm_er_range"),
            models.CheckConstraint(
                condition=models.Q(vr_min__lte=models.F("vr_max")), name="norm_vr_range"),
            models.CheckConstraint(
                condition=models.Q(pu_min__lte=models.F("pu_max")), name="norm_pu_range"),
        ]

    def __str__(self) -> str:
        return (
            f"ЭР {self.er_min:g}–{self.er_max:g}; "
            f"ВР {self.vr_min:g}–{self.vr_max:g}; "
            f"ПУ {self.pu_min:g}–{self.pu_max:g}"
        )

    def contains(self, result: "TestResult") -> bool:
        return (
            self.er_min <= result.er <= self.er_max
            and self.vr_min <= result.vr <= self.vr_max
            and self.pu_min <= result.pu <= self.pu_max
        )


class TestSession(models.Model):
    """Назначенное прохождение пяти таблиц Шульте."""

    class CheckType(models.TextChoices):
        PLANNED = "плановая", "Плановая"
        PERIODIC = "периодическая", "Периодическая"
        PREFLIGHT = "предполётная", "Предполётная"

    class Status(models.TextChoices):
        ASSIGNED = "назначена", "Назначена"
        COMPLETED = "завершена", "Завершена"
        CANCELLED = "отменена", "Отменена"

    pilot = models.ForeignKey(
        User, verbose_name="пилот", related_name="pilot_sessions", on_delete=models.PROTECT)
    psychologist = models.ForeignKey(
        User, verbose_name="психолог", related_name="assigned_sessions", on_delete=models.PROTECT)
    scheduled_at = models.DateTimeField("дата и время")
    check_type = models.CharField("тип проверки", max_length=20, choices=CheckType.choices)
    table_size = models.PositiveSmallIntegerField(
        "размер таблиц",
        choices=((3, "3×3"), (4, "4×4"), (5, "5×5")),
        default=3,
    )
    number_order = models.CharField(
        "порядок следования чисел",
        max_length=20,
        choices=(("по порядку", "По порядку"), ("вперемешку", "Вперемешку")),
        default="по порядку",
    )
    method = models.CharField("методика", max_length=40, default="Шульте")
    status = models.CharField(
        "статус", max_length=20, choices=Status.choices, default=Status.ASSIGNED)
    practice_done = models.BooleanField("пробная таблица пройдена", default=False)

    class Meta:
        verbose_name = "попытка тестирования"
        verbose_name_plural = "попытки тестирования"
        ordering = ["-scheduled_at", "-id"]

    def __str__(self) -> str:
        return f"{self.pilot.display_name()}, {self.get_check_type_display()}, {self.get_status_display()}"

    @property
    def status_kind(self) -> str:
        return {
            self.Status.ASSIGNED: "warn",
            self.Status.COMPLETED: "ok",
            self.Status.CANCELLED: "bad",
        }[self.status]


class SchulteTable(models.Model):
    """Одна таблица n×n внутри сессии."""

    class Layout(models.TextChoices):
        ORDERED = "по порядку", "По порядку"
        SHUFFLED = "вперемешку", "Вперемешку"

    session = models.ForeignKey(
        TestSession, verbose_name="попытка", related_name="tables", on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField("номер по порядку")
    size = models.PositiveSmallIntegerField("размер")
    layout = models.CharField("расположение чисел", max_length=20, choices=Layout.choices)
    numbers = models.JSONField("числа")
    time_sec = models.FloatField("время, с")

    class Meta:
        verbose_name = "таблица Шульте"
        verbose_name_plural = "таблицы Шульте"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["session", "order"], name="unique_table_order"),
            models.CheckConstraint(condition=models.Q(time_sec__gt=0), name="table_time_positive"),
            models.CheckConstraint(condition=models.Q(size__gte=2), name="table_size_min"),
        ]

    def __str__(self) -> str:
        return f"Таблица {self.order}"


class TestResult(models.Model):
    """ЭР, ВР и ПУ завершённой сессии."""

    session = models.OneToOneField(
        TestSession, verbose_name="попытка", related_name="result", on_delete=models.CASCADE)
    er = models.FloatField("ЭР")
    vr = models.FloatField("ВР")
    pu = models.FloatField("ПУ")

    class Meta:
        verbose_name = "результат тестирования"
        verbose_name_plural = "результаты тестирования"

    def __str__(self) -> str:
        return f"ЭР={self.er:.2f}, ВР={self.vr:.3f}, ПУ={self.pu:.3f}"


class Conclusion(models.Model):
    """Заключение психолога о допуске пилота к полётам."""

    class Decision(models.TextChoices):
        FIT = "годен", "Допустить"
        FIT_LIMITED = "годен с ограничением", "Допустить с ограничением"
        EXTRA = "направлен на дополнительное обследование", "Направить на дополнительное обследование"

    result = models.ForeignKey(
        TestResult, verbose_name="результат", related_name="conclusions", on_delete=models.PROTECT)
    psychologist = models.ForeignKey(
        User, verbose_name="психолог", related_name="conclusions", on_delete=models.PROTECT)
    norm = models.ForeignKey(
        AdmissionNorm, verbose_name="норма", related_name="conclusions", on_delete=models.PROTECT)
    decision = models.CharField("решение", max_length=80, choices=Decision.choices)
    date = models.DateField("дата")
    comment = models.TextField("комментарий", blank=True)

    class Meta:
        verbose_name = "заключение о допуске"
        verbose_name_plural = "заключения о допуске"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.result.session.pilot.display_name()}: {self.get_decision_display()}"

    @property
    def pilot_decision(self) -> str:
        """Итог для пилота: не рекомендация психолога, а состояние допуска."""
        return {
            self.Decision.FIT: "Допущен",
            self.Decision.FIT_LIMITED: "Допущен с ограничением",
            self.Decision.EXTRA: "Требуется дополнительное обследование",
        }[self.decision]

    @property
    def decision_kind(self) -> str:
        return {
            self.Decision.FIT: "ok",
            self.Decision.FIT_LIMITED: "warn",
            self.Decision.EXTRA: "bad",
        }[self.decision]


class SummaryReport(models.Model):
    """Сводный отчёт администратора за период по группе пилотов."""

    administrator = models.ForeignKey(
        User, verbose_name="администратор", related_name="reports", on_delete=models.PROTECT)
    period_start = models.DateField("начало периода")
    period_end = models.DateField("конец периода")
    created_at = models.DateTimeField("создан", auto_now_add=True)

    class Meta:
        verbose_name = "сводный отчёт"
        verbose_name_plural = "сводные отчёты"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Отчёт {self.period_start}–{self.period_end}"


class ReportLine(models.Model):
    report = models.ForeignKey(
        SummaryReport, verbose_name="отчёт", related_name="lines", on_delete=models.CASCADE)
    pilot = models.ForeignKey(
        User, verbose_name="пилот", related_name="report_lines", on_delete=models.PROTECT)
    full_name = models.CharField("ФИО", max_length=200)
    session_count = models.PositiveIntegerField("число попыток")
    avg_er = models.FloatField("средний ЭР")
    avg_vr = models.FloatField("средний ВР")
    avg_pu = models.FloatField("средний ПУ")

    class Meta:
        verbose_name = "строка отчёта"
        verbose_name_plural = "строки отчёта"
        ordering = ["full_name"]

    def __str__(self) -> str:
        return self.full_name


class Notification(models.Model):
    """Сообщение пилоту, например о назначенной проверке."""

    recipient = models.ForeignKey(
        User, verbose_name="получатель", related_name="notifications", on_delete=models.CASCADE)
    text = models.TextField("текст")
    created_at = models.DateTimeField("создано", auto_now_add=True)
    is_read = models.BooleanField("прочитано", default=False)

    class Meta:
        verbose_name = "уведомление"
        verbose_name_plural = "уведомления"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.text


class SecurityHandoff(models.Model):
    """Факт передачи заключения или отчёта в службу безопасности полётов."""

    class Kind(models.TextChoices):
        CONCLUSION = "заключение", "Заключение"
        REPORT = "отчёт", "Отчёт"

    kind = models.CharField("вид", max_length=20, choices=Kind.choices)
    summary = models.TextField("содержание")
    created_at = models.DateTimeField("передано", auto_now_add=True)
    conclusion = models.ForeignKey(
        Conclusion, verbose_name="заключение", null=True, blank=True,
        related_name="handoffs", on_delete=models.SET_NULL)
    report = models.ForeignKey(
        SummaryReport, verbose_name="отчёт", null=True, blank=True,
        related_name="handoffs", on_delete=models.SET_NULL)

    class Meta:
        verbose_name = "передача в службу безопасности"
        verbose_name_plural = "передачи в службу безопасности"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.summary

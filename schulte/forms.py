from django import forms

from schulte.models import Conclusion, TestSession, User


class StyledForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
                continue
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} input".strip()


class PilotForm(StyledForm):
    username = forms.CharField(label="Логин", max_length=150)
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput, required=False)
    full_name = forms.CharField(label="ФИО", max_length=200)
    employee_number = forms.CharField(label="Табельный номер", max_length=32)
    position = forms.CharField(label="Должность", max_length=120, required=False)

    def __init__(self, *args, instance: User | None = None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance is None:
            self.fields["password"].required = True
        else:
            self.fields["password"].help_text = "Оставьте пустым, чтобы не менять пароль"

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if not username:
            raise forms.ValidationError("Логин обязателен")
        taken = User.objects.filter(username=username)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("Логин уже занят")
        return username

    def clean_full_name(self) -> str:
        full_name = self.cleaned_data["full_name"].strip()
        if not full_name:
            raise forms.ValidationError("ФИО обязательно")
        return full_name

    def clean_employee_number(self) -> str:
        number = self.cleaned_data["employee_number"].strip()
        if not number:
            raise forms.ValidationError("Табельный номер обязателен")
        taken = User.objects.filter(employee_number=number)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("Табельный номер уже используется")
        return number

    def clean_password(self) -> str:
        password = self.cleaned_data.get("password") or ""
        creating = self.instance is None
        if (creating or password) and len(password) < 6:
            raise forms.ValidationError("Пароль должен содержать не менее 6 символов")
        return password

    def save(self) -> User:
        data = self.cleaned_data
        pilot = self.instance or User(role=User.Role.PILOT)
        pilot.username = data["username"]
        pilot.full_name = data["full_name"]
        pilot.employee_number = data["employee_number"]
        pilot.position = data["position"].strip()
        pilot.role = User.Role.PILOT
        if data["password"]:
            pilot.set_password(data["password"])
        pilot.save()
        return pilot


class PsychologistForm(StyledForm):
    username = forms.CharField(label="Логин", max_length=150)
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput, required=False)
    full_name = forms.CharField(label="ФИО", max_length=200)
    position = forms.CharField(label="Должность", max_length=120, required=False)

    def __init__(self, *args, instance: User | None = None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance is None:
            self.fields["password"].required = True
        else:
            self.fields["password"].help_text = "Оставьте пустым, чтобы не менять пароль"

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if not username:
            raise forms.ValidationError("Логин обязателен")
        taken = User.objects.filter(username=username)
        if self.instance is not None:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError("Логин уже занят")
        return username

    def clean_full_name(self) -> str:
        full_name = self.cleaned_data["full_name"].strip()
        if not full_name:
            raise forms.ValidationError("ФИО обязательно")
        return full_name

    def clean_password(self) -> str:
        password = self.cleaned_data.get("password") or ""
        creating = self.instance is None
        if (creating or password) and len(password) < 6:
            raise forms.ValidationError("Пароль должен содержать не менее 6 символов")
        return password

    def save(self) -> User:
        data = self.cleaned_data
        psychologist = self.instance or User(role=User.Role.PSYCHOLOGIST)
        psychologist.username = data["username"]
        psychologist.full_name = data["full_name"]
        psychologist.position = data["position"].strip()
        psychologist.role = User.Role.PSYCHOLOGIST
        psychologist.employee_number = None
        if data["password"]:
            psychologist.set_password(data["password"])
        psychologist.save()
        return psychologist


class AdministratorForm(StyledForm):
    username = forms.CharField(label="Логин", max_length=150)
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput)
    full_name = forms.CharField(label="ФИО", max_length=200)

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if not username:
            raise forms.ValidationError("Логин обязателен")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Логин уже занят")
        return username

    def clean_full_name(self) -> str:
        full_name = self.cleaned_data["full_name"].strip()
        if not full_name:
            raise forms.ValidationError("ФИО обязательно")
        return full_name

    def clean_password(self) -> str:
        password = self.cleaned_data.get("password") or ""
        if len(password) < 6:
            raise forms.ValidationError("Пароль должен содержать не менее 6 символов")
        return password

    def save(self) -> User:
        data = self.cleaned_data
        admin = User(
            username=data["username"],
            full_name=data["full_name"],
            role=User.Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        admin.set_password(data["password"])
        admin.save()
        return admin


class NormForm(StyledForm):
    er_min = forms.FloatField(label="ЭР, минимум")
    er_max = forms.FloatField(label="ЭР, максимум")
    vr_min = forms.FloatField(label="ВР, минимум")
    vr_max = forms.FloatField(label="ВР, максимум")
    pu_min = forms.FloatField(label="ПУ, минимум")
    pu_max = forms.FloatField(label="ПУ, максимум")

    def clean(self):
        cleaned = super().clean()
        for title, low_key, high_key in (
            ("ЭР", "er_min", "er_max"),
            ("ВР", "vr_min", "vr_max"),
            ("ПУ", "pu_min", "pu_max"),
        ):
            low, high = cleaned.get(low_key), cleaned.get(high_key)
            if low is not None and high is not None and low > high:
                self.add_error(low_key, f"Диапазон {title}: нижняя граница больше верхней")
        return cleaned


class AssignForm(StyledForm):
    pilot = forms.ModelChoiceField(
        label="Пилот",
        queryset=User.objects.filter(role=User.Role.PILOT).order_by("full_name", "username"),
        empty_label="Выберите пилота",
    )
    check_type = forms.ChoiceField(label="Тип проверки", choices=TestSession.CheckType.choices)
    table_size = forms.TypedChoiceField(
        label="Размер таблиц",
        choices=((3, "3×3"), (4, "4×4"), (5, "5×5")),
        coerce=int,
    )
    number_order = forms.ChoiceField(
        label="Порядок следования чисел",
        choices=(("по порядку", "По порядку"), ("вперемешку", "Вперемешку")),
    )


class ConclusionForm(StyledForm):
    decision = forms.ChoiceField(label="Решение", choices=Conclusion.Decision.choices)
    comment = forms.CharField(
        label="Комментарий", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class ReportForm(StyledForm):
    period_start = forms.DateField(
        label="Начало периода", widget=forms.DateInput(attrs={"type": "date"}))
    period_end = forms.DateField(
        label="Конец периода", widget=forms.DateInput(attrs={"type": "date"}))
    pilots = forms.ModelMultipleChoiceField(
        label="Группа пилотов",
        queryset=User.objects.filter(role=User.Role.PILOT).order_by("full_name", "username"),
        widget=forms.CheckboxSelectMultiple,
    )

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("period_start"), cleaned.get("period_end")
        if start and end and start > end:
            raise forms.ValidationError("Начало периода позже его конца")
        return cleaned

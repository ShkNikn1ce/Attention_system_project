from django.core.management.base import BaseCommand

from schulte.models import AdmissionNorm, User


ACCOUNTS = (
    {
        "username": "admin",
        "password": "admin123",
        "role": User.Role.ADMIN,
        "full_name": "Администратор",
        "staff": True,
    },
    {
        "username": "psy",
        "password": "psy12345",
        "role": User.Role.PSYCHOLOGIST,
        "full_name": "Петрова А.С.",
        "staff": False,
    },
)


class Command(BaseCommand):
    help = "Создаёт персонал (администратор и психолог) и нормы допуска. Пилотов не добавляет."

    def handle(self, *args, **options):
        for account in ACCOUNTS:
            user, created = User.objects.get_or_create(
                username=account["username"],
                defaults={
                    "role": account["role"],
                    "full_name": account["full_name"],
                    "employee_number": account.get("employee_number"),
                    "position": account.get("position", ""),
                    "is_staff": account["staff"],
                    "is_superuser": account["staff"],
                },
            )
            if created:
                user.set_password(account["password"])
                user.save(update_fields=["password"])
                self.stdout.write(f"создан {user.username}")
            else:
                self.stdout.write(f"уже есть {user.username}")
        if not AdmissionNorm.objects.exists():
            AdmissionNorm.objects.create(
                er_min=3, er_max=25, vr_min=0.8, vr_max=1.1, pu_min=0.8, pu_max=1.1)
            self.stdout.write("созданы нормы допуска")
        self.stdout.write("Готово. Персонал: admin/admin123, psy/psy12345. Пилоты регистрируются сами.")

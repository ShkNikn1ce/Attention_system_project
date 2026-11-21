from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from schulte.models import (
    AdmissionNorm, Conclusion, Notification, ReportLine, SecurityHandoff, SchulteTable,
    SummaryReport, TestResult, TestSession, User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Профиль", {"fields": ("role", "full_name", "employee_number", "position")}),
    )
    list_display = ("username", "full_name", "role", "employee_number", "position")
    list_filter = ("role",)


admin.site.register(AdmissionNorm)
admin.site.register(TestSession)
admin.site.register(SchulteTable)
admin.site.register(TestResult)
admin.site.register(Conclusion)
admin.site.register(SummaryReport)
admin.site.register(ReportLine)
admin.site.register(Notification)
admin.site.register(SecurityHandoff)

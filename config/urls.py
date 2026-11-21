from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Система тестирования внимания"
admin.site.site_title = "Шульте"
admin.site.index_title = "Данные системы"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("schulte.urls")),
]

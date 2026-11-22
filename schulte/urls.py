from django.urls import path

from schulte import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("testing/", views.test_start, name="test_start"),
    path("testing/table/", views.test_table, name="test_table"),
    path("results/", views.my_results, name="my_results"),
    path("results/<int:pk>/", views.my_result, name="my_result"),
    path("notifications/", views.notifications, name="notifications"),
    path("assign/", views.assign_test, name="assign_test"),
    path("reviews/", views.review_pilots, name="review_pilots"),
    path("reviews/pilot/<int:pk>/", views.review_pilot, name="review_pilot"),
    path("reviews/session/<int:pk>/", views.review_session, name="review_session"),
    path("reviews/session/<int:pk>/conclusion/", views.conclusion, name="conclusion"),
    path("dynamics/", views.dynamics, name="dynamics"),
    path("dynamics/<int:pk>/", views.dynamics_pilot, name="dynamics_pilot"),
    path("psychologists/", views.psychologist_list, name="psychologist_list"),
    path("psychologists/new/", views.psychologist_create, name="psychologist_create"),
    path("psychologists/<int:pk>/edit/", views.psychologist_edit, name="psychologist_edit"),
    path("pilots/", views.pilot_list, name="pilot_list"),
    path("pilots/new/", views.pilot_create, name="pilot_create"),
    path("pilots/<int:pk>/edit/", views.pilot_edit, name="pilot_edit"),
    path("pilots/<int:pk>/delete/", views.pilot_delete, name="pilot_delete"),
    path("norms/", views.norms, name="norms"),
    path("reports/", views.reports, name="reports"),
    path("reports/<int:pk>/", views.report_detail, name="report_detail"),
    path("security/", views.security_log, name="security_log"),
]

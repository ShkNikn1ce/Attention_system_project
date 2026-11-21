from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods, require_POST

from schulte.authz import role_required
from schulte.forms import AssignForm, ConclusionForm, NormForm, PilotForm, ReportForm
from schulte.models import (
    AdmissionNorm, Conclusion, LoginThrottle, SchulteTable, SecurityHandoff, SummaryReport,
    TestSession, User,
)
from schulte.services import (
    DomainError, TABLE_COUNT, assign_session, build_report, cancel_session, chart_polyline,
    dynamics_points, generate_numbers, record_table, save_conclusion, save_norm, suggest_decision,
)

RUN_KEY = "schulte_run"
GRID_SIZES = (3, 4, 5)


def _assigned_session(user: User) -> TestSession | None:
    return (
        TestSession.objects.filter(pilot=user, status=TestSession.Status.ASSIGNED)
        .select_related("psychologist")
        .order_by("scheduled_at", "id")
        .first()
    )


def _clear_run(request) -> None:
    request.session.pop(RUN_KEY, None)


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    error = None
    hint = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        throttle, _ = LoginThrottle.objects.get_or_create(username=username)
        if throttle.failures >= settings.LOGIN_MAX_ATTEMPTS:
            error = "Превышено число попыток входа"
        else:
            user = authenticate(request, username=username, password=password)
            if user is None:
                throttle.failures += 1
                throttle.save(update_fields=["failures"])
                error = "Неверный логин или пароль"
                hint = "Повторите ввод логина и пароля"
            else:
                if throttle.failures:
                    throttle.failures = 0
                    throttle.save(update_fields=["failures"])
                login(request, user)
                messages.success(request, f"Открыт интерфейс: {user.get_role_display().lower()}")
                return redirect("dashboard")
    return render(request, "schulte/login.html", {"error": error, "hint": hint})


@require_http_methods(["GET", "POST"])
def register_view(request):
    """Регистрация пилота. Персонал в базе уже есть, пилотов заранее нет."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = PilotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        pilot = form.save()
        messages.success(request, f"Пилот {pilot.display_name()} зарегистрирован. Войдите в систему.")
        return redirect("login")
    return render(request, "schulte/register.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    user = request.user
    context = {}
    if user.role == User.Role.PILOT:
        context["assigned"] = _assigned_session(user)
        context["sessions"] = (
            TestSession.objects.filter(pilot=user, status=TestSession.Status.COMPLETED)
            .select_related("result")[:5]
        )
        context["notes"] = user.notifications.all()[:5]
    elif user.role == User.Role.PSYCHOLOGIST:
        context["recent_sessions"] = (
            user.assigned_sessions.select_related("pilot")[:6]
        )
    else:
        context["norm"] = AdmissionNorm.objects.order_by("-id").first()
        context["pilot_count"] = User.objects.filter(role=User.Role.PILOT).count()
        context["reports"] = SummaryReport.objects.select_related("administrator")[:5]
    return render(request, "schulte/dashboard.html", context)


@role_required(User.Role.PILOT)
@require_http_methods(["GET", "POST"])
def test_start(request):
    session = _assigned_session(request.user)
    run = request.session.get(RUN_KEY)
    if run and session and run.get("session_id") == session.id:
        return redirect("test_table")
    if run:
        _clear_run(request)
    if request.method == "POST" and session is not None:
        try:
            size = int(request.POST.get("size", ""))
        except ValueError:
            size = 0
        layout = request.POST.get("layout", "")
        allowed = {value for value, _label in SchulteTable.Layout.choices}
        if size not in GRID_SIZES or layout not in allowed:
            messages.error(request, "Выберите размер таблицы и расположение чисел")
        else:
            request.session[RUN_KEY] = {
                "session_id": session.id,
                "size": size,
                "layout": layout,
            }
            request.session.modified = True
            return redirect("test_table")
    return render(request, "schulte/test_start.html", {
        "session": session,
        "sizes": GRID_SIZES,
        "layouts": SchulteTable.Layout.choices,
    })


@role_required(User.Role.PILOT)
@require_http_methods(["GET", "POST"])
def test_table(request):
    run = request.session.get(RUN_KEY)
    session = _assigned_session(request.user)
    if not run or session is None or run.get("session_id") != session.id:
        _clear_run(request)
        return redirect("test_start")

    if request.method == "POST" and request.POST.get("action") == "cancel":
        try:
            cancel_session(session)
        except DomainError as exc:
            messages.error(request, str(exc))
        else:
            messages.info(request, "Тестирование прервано, результат не сохранён")
        _clear_run(request)
        return redirect("dashboard")

    size = int(run["size"])
    layout = run["layout"]
    done = session.tables.count()
    if done >= TABLE_COUNT:
        _clear_run(request)
        return redirect("my_result", pk=session.pk)

    current = run.get("current")
    if current is None or current.get("order") != done + 1:
        current = {
            "order": done + 1,
            "numbers": generate_numbers(size, layout),
            "started_at": timezone.now().isoformat(),
        }
        run["current"] = current
        request.session[RUN_KEY] = run
        request.session.modified = True

    if request.method == "POST":
        expected = list(range(1, size * size + 1))
        raw = request.POST.get("sequence", "")
        try:
            sequence = [int(part) for part in raw.split(",") if part]
        except ValueError:
            sequence = []
        if sequence != expected:
            messages.error(request, "Числа нужно указывать строго по возрастанию, от 1 до последней клетки")
            return redirect("test_table")
        started = parse_datetime(current["started_at"])
        if started is None:
            started = datetime.fromisoformat(current["started_at"])
        if timezone.is_naive(started):
            started = timezone.make_aware(started, timezone.get_current_timezone())
        elapsed = (timezone.now() - started).total_seconds()
        if elapsed <= 0:
            elapsed = 0.001
        try:
            finished = record_table(
                session, current["order"], size, layout, current["numbers"], elapsed)
        except DomainError as exc:
            messages.error(request, str(exc))
            return redirect("test_table")
        run["current"] = None
        request.session[RUN_KEY] = run
        request.session.modified = True
        if not finished:
            return redirect("test_table")
        session.refresh_from_db()
        result = session.result
        _clear_run(request)
        messages.success(
            request,
            f"Тестирование завершено: ЭР={result.er:.2f}, ВР={result.vr:.3f}, ПУ={result.pu:.3f}",
        )
        return redirect("my_result", pk=session.pk)

    return render(request, "schulte/test_table.html", {
        "session": session,
        "order": current["order"],
        "size": size,
        "numbers": current["numbers"],
        "started_at": current["started_at"],
        "layout_label": dict(SchulteTable.Layout.choices)[layout],
        "total": TABLE_COUNT,
    })


@role_required(User.Role.PILOT)
def my_results(request):
    sessions = (
        TestSession.objects.filter(pilot=request.user, status=TestSession.Status.COMPLETED)
        .select_related("result")
    )
    return render(request, "schulte/my_results.html", {"sessions": sessions})


def _result_page(request, session: TestSession, *, conclude: bool):
    tables = list(session.tables.all())
    result = getattr(session, "result", None)
    conclusion = None
    if result is not None:
        conclusion = result.conclusions.select_related("norm", "psychologist").first()
    return render(request, "schulte/result_detail.html", {
        "session": session,
        "tables": tables,
        "result": result,
        "conclusion": conclusion,
        "conclude": conclude,
    })


@role_required(User.Role.PILOT)
def my_result(request, pk: int):
    session = get_object_or_404(
        TestSession.objects.select_related("result", "psychologist"),
        pk=pk, pilot=request.user, status=TestSession.Status.COMPLETED,
    )
    return _result_page(request, session, conclude=False)


@role_required(User.Role.PILOT)
def notifications(request):
    notes = list(request.user.notifications.all())
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "schulte/notifications.html", {"notes": notes})


@role_required(User.Role.PSYCHOLOGIST)
@require_http_methods(["GET", "POST"])
def assign_test(request):
    pilots = User.objects.filter(role=User.Role.PILOT).order_by("full_name", "username")
    form = AssignForm(request.POST or None)
    if request.method == "POST" and pilots.exists() and form.is_valid():
        session = assign_session(request.user, form.cleaned_data["pilot"], form.cleaned_data["check_type"])
        messages.success(
            request, f"Тестирование назначено (сессия {session.pk}), пилот уведомлён")
        return redirect("assign_test")
    return render(request, "schulte/assign.html", {"form": form, "has_pilots": pilots.exists()})


@role_required(User.Role.PSYCHOLOGIST)
def review_pilots(request):
    pilots = User.objects.filter(role=User.Role.PILOT).order_by("full_name", "username")
    return render(request, "schulte/review_pilots.html", {"pilots": pilots})


@role_required(User.Role.PSYCHOLOGIST)
def review_pilot(request, pk: int):
    pilot = get_object_or_404(User, pk=pk, role=User.Role.PILOT)
    sessions = (
        TestSession.objects.filter(pilot=pilot, status=TestSession.Status.COMPLETED)
        .select_related("result")
    )
    return render(request, "schulte/review_pilot.html", {"pilot": pilot, "sessions": sessions})


@role_required(User.Role.PSYCHOLOGIST)
def review_session(request, pk: int):
    session = get_object_or_404(
        TestSession.objects.select_related("pilot", "result", "psychologist"), pk=pk)
    if session.status != TestSession.Status.COMPLETED or not hasattr(session, "result"):
        messages.error(request, "Результат сессии отсутствует")
        return redirect("review_pilot", pk=session.pilot_id)
    return _result_page(request, session, conclude=True)


@role_required(User.Role.PSYCHOLOGIST)
@require_http_methods(["GET", "POST"])
def conclusion(request, pk: int):
    session = get_object_or_404(
        TestSession.objects.select_related("pilot", "result"), pk=pk)
    result = getattr(session, "result", None)
    if result is None:
        messages.error(request, "Для сессии нет результата тестирования")
        return redirect("review_pilot", pk=session.pilot_id)
    existing = result.conclusions.select_related("norm").first()
    norm = AdmissionNorm.objects.order_by("-id").first()
    if existing is None and norm is None:
        messages.error(request, "Нормы допуска не заданы")
        return redirect("review_session", pk=session.pk)
    suggestion = suggest_decision(result, existing.norm if existing else norm)
    form = ConclusionForm(
        request.POST or None,
        initial={"decision": existing.decision if existing else suggestion},
    )
    if request.method == "POST" and existing is None and form.is_valid():
        saved = save_conclusion(
            result, request.user, norm, form.cleaned_data["decision"], form.cleaned_data["comment"])
        messages.success(
            request,
            f"Заключение сохранено и передано в службу безопасности: {saved.get_decision_display().lower()}",
        )
        return redirect("conclusion", pk=session.pk)
    return render(request, "schulte/conclusion.html", {
        "session": session,
        "result": result,
        "norm": existing.norm if existing else norm,
        "suggestion": suggestion,
        "suggestion_label": dict(Conclusion.Decision.choices)[suggestion],
        "in_norm": suggestion == Conclusion.Decision.FIT,
        "form": form,
        "existing": existing,
    })


@role_required(User.Role.PSYCHOLOGIST)
def dynamics(request):
    pilots = User.objects.filter(role=User.Role.PILOT).order_by("full_name", "username")
    return render(request, "schulte/dynamics_pick.html", {"pilots": pilots})


@role_required(User.Role.PSYCHOLOGIST)
def dynamics_pilot(request, pk: int):
    pilot = get_object_or_404(User, pk=pk, role=User.Role.PILOT)
    points = dynamics_points(pilot)
    charts = []
    if len(points) >= 2:
        for key, title in (("er", "ЭР"), ("vr", "ВР"), ("pu", "ПУ")):
            values = [point[key] for point in points]
            charts.append({
                "title": title,
                "points": chart_polyline(values),
                "low": min(values),
                "high": max(values),
            })
    return render(request, "schulte/dynamics.html", {
        "pilot": pilot,
        "points": points,
        "charts": charts,
        "enough": len(points) >= 2,
    })


@role_required(User.Role.ADMIN)
def pilot_list(request):
    pilots = User.objects.filter(role=User.Role.PILOT).order_by("full_name", "username")
    return render(request, "schulte/pilots.html", {"pilots": pilots})


@role_required(User.Role.ADMIN)
@require_http_methods(["GET", "POST"])
def pilot_create(request):
    form = PilotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Пилот добавлен")
        return redirect("pilot_list")
    return render(request, "schulte/pilot_form.html", {"form": form, "title": "Новый пилот"})


@role_required(User.Role.ADMIN)
@require_http_methods(["GET", "POST"])
def pilot_edit(request, pk: int):
    pilot = get_object_or_404(User, pk=pk, role=User.Role.PILOT)
    form = PilotForm(
        request.POST or None,
        instance=pilot,
        initial={
            "username": pilot.username,
            "full_name": pilot.full_name,
            "employee_number": pilot.employee_number,
            "position": pilot.position,
        },
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Данные пилота изменены")
        return redirect("pilot_list")
    return render(request, "schulte/pilot_form.html", {"form": form, "title": "Данные пилота"})


@role_required(User.Role.ADMIN)
@require_http_methods(["GET", "POST"])
def pilot_delete(request, pk: int):
    pilot = get_object_or_404(User, pk=pk, role=User.Role.PILOT)
    blocked = pilot.pilot_sessions.exists()
    if request.method == "POST":
        if blocked:
            messages.error(request, "Нельзя удалить пилота: у него есть сессии тестирования")
            return redirect("pilot_list")
        try:
            pilot.delete()
        except ProtectedError:
            messages.error(request, "Нельзя удалить пилота: на него ссылаются сохранённые отчёты")
            return redirect("pilot_list")
        messages.success(request, "Пилот удалён")
        return redirect("pilot_list")
    return render(request, "schulte/pilot_delete.html", {"pilot": pilot, "blocked": blocked})


@role_required(User.Role.ADMIN)
@require_http_methods(["GET", "POST"])
def norms(request):
    current = AdmissionNorm.objects.order_by("-id").first()
    initial = None
    if current is not None:
        initial = {
            "er_min": current.er_min, "er_max": current.er_max,
            "vr_min": current.vr_min, "vr_max": current.vr_max,
            "pu_min": current.pu_min, "pu_max": current.pu_max,
        }
    form = NormForm(request.POST or None, initial=None if request.method == "POST" else initial)
    if request.method == "POST" and form.is_valid():
        save_norm(form.cleaned_data)
        messages.success(request, "Нормы допуска сохранены")
        return redirect("norms")
    history = AdmissionNorm.objects.all()
    return render(request, "schulte/norms.html", {
        "form": form,
        "current": current,
        "history": history,
        "saved": None,
    })


@role_required(User.Role.ADMIN)
@require_http_methods(["GET", "POST"])
def reports(request):
    form = ReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            report = build_report(
                request.user,
                form.cleaned_data["period_start"],
                form.cleaned_data["period_end"],
                form.cleaned_data["pilots"],
            )
        except DomainError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Сводный отчёт передан в службу безопасности")
            return redirect("report_detail", pk=report.pk)
    ready = SummaryReport.objects.all()[:20]
    return render(request, "schulte/reports.html", {"form": form, "reports": ready})


@role_required(User.Role.ADMIN)
def report_detail(request, pk: int):
    report = get_object_or_404(
        SummaryReport.objects.prefetch_related("lines"), pk=pk)
    return render(request, "schulte/report_detail.html", {"report": report})


@role_required(User.Role.ADMIN)
def security_log(request):
    handoffs = SecurityHandoff.objects.all()[:50]
    return render(request, "schulte/security.html", {"handoffs": handoffs})

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
    DomainError, TABLE_COUNT, assign_session, attempt_number, build_report, cancel_session, chart_series,
    dynamics_points, generate_numbers, record_table, save_conclusion, save_norm, suggest_decision,
)

RUN_KEY = "schulte_run"


def _assigned_session(user: User) -> TestSession | None:
    return (
        TestSession.objects.filter(pilot=user, status=TestSession.Status.ASSIGNED)
        .select_related("psychologist")
        .order_by("scheduled_at", "id")
        .first()
    )


def _clear_run(request) -> None:
    request.session.pop(RUN_KEY, None)


def _run_session(request):
    """Текущая попытка пилота. После пятой таблицы по порядку сессия уже завершена, но экран итога ещё открыт."""
    run = request.session.get(RUN_KEY)
    assigned = _assigned_session(request.user)
    if not run:
        return None, assigned
    if assigned is not None and run.get("session_id") == assigned.id:
        return run, assigned
    if run.get("pause"):
        paused = (
            TestSession.objects.filter(
                pk=run.get("session_id"),
                pilot=request.user,
                status=TestSession.Status.COMPLETED,
            )
            .select_related("result")
            .first()
        )
        if paused is not None:
            return run, paused
    return run, assigned


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
        context["sessions"] = [
            session for session in (
                TestSession.objects.filter(pilot=user, status=TestSession.Status.COMPLETED)
                .select_related("result")[:5]
            )
        ]
        for session in context["sessions"]:
            session.attempt = attempt_number(session)
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
    needs_practice = (
        session is not None
        and not session.practice_done
        and not session.tables.exists()
    )
    if request.method == "POST" and session is not None:
        practice = request.POST.get("mode") == "practice"
        if practice and needs_practice:
            request.session[RUN_KEY] = {
                "session_id": session.id,
                "size": session.table_size,
                "layout": session.number_order,
                "practice": True,
            }
            request.session.modified = True
            return redirect("test_table")
        if not practice and not needs_practice:
            request.session[RUN_KEY] = {
                "session_id": session.id,
                "size": session.table_size,
                "layout": session.number_order,
                "practice": False,
            }
            request.session.modified = True
            return redirect("test_table")
    return render(request, "schulte/test_start.html", {
        "session": session,
        "needs_practice": needs_practice,
    })


@role_required(User.Role.PILOT)
@require_http_methods(["GET", "POST"])
def test_table(request):
    run, session = _run_session(request)
    if not run or session is None or run.get("session_id") != session.id:
        _clear_run(request)
        return redirect("test_start")

    if request.method == "POST" and request.POST.get("action") == "cancel" and not run.get("practice"):
        try:
            cancel_session(session)
        except DomainError as exc:
            messages.error(request, str(exc))
        else:
            messages.info(request, "Тестирование прервано, результат не сохранён")
        _clear_run(request)
        return redirect("dashboard")

    size = session.table_size
    layout = session.number_order
    practice = bool(run.get("practice"))
    if practice:
        if session.practice_done:
            _clear_run(request)
            return redirect("test_start")
        current = run.get("current")
        if current is None:
            current = {
                "order": 1,
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
            session.practice_done = True
            session.save(update_fields=["practice_done"])
            _clear_run(request)
            return redirect("test_start")
        return render(request, "schulte/test_table.html", {
            "session": session,
            "order": 1,
            "size": size,
            "numbers": current["numbers"],
            "started_at": current["started_at"],
            "layout_label": dict(SchulteTable.Layout.choices)[layout],
            "total": 1,
        })

    total = TABLE_COUNT
    if run.get("pause") and layout == SchulteTable.Layout.ORDERED:
        tables = list(session.tables.order_by("order"))
        if request.method == "POST" and request.POST.get("action") in {"next", "finish"}:
            run["pause"] = False
            request.session[RUN_KEY] = run
            request.session.modified = True
            if request.POST.get("action") == "finish" or len(tables) >= total:
                _clear_run(request)
                return redirect("my_result", pk=session.pk)
            return redirect("test_table")
        finished = len(tables) >= total
        last = tables[-1] if tables else None
        return render(request, "schulte/test_pause.html", {
            "session": session,
            "tables": tables,
            "order": last.order if last else 0,
            "time_sec": last.time_sec if last else 0,
            "next_order": (last.order + 1) if last else 2,
            "finished": finished,
            "result": getattr(session, "result", None) if finished else None,
        })

    done = session.tables.count()
    if done >= total:
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
        if layout == SchulteTable.Layout.ORDERED:
            run["pause"] = True
        request.session[RUN_KEY] = run
        request.session.modified = True
        if run.get("pause"):
            return redirect("test_table")
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
        "total": total,
    })


@role_required(User.Role.PILOT)
def my_results(request):
    sessions = (
        TestSession.objects.filter(pilot=request.user, status=TestSession.Status.COMPLETED)
        .select_related("result")
        .order_by("scheduled_at", "id")
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
        "attempt": attempt_number(session),
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
        session = assign_session(
            request.user,
            form.cleaned_data["pilot"],
            form.cleaned_data["check_type"],
            form.cleaned_data["table_size"],
            form.cleaned_data["number_order"],
        )
        messages.success(
            request, "Тестирование назначено, пилот уведомлён.", extra_tags="keep")
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
        .order_by("scheduled_at", "id")
    )
    return render(request, "schulte/review_pilot.html", {"pilot": pilot, "sessions": sessions})


@role_required(User.Role.PSYCHOLOGIST)
def review_session(request, pk: int):
    session = get_object_or_404(
        TestSession.objects.select_related("pilot", "result", "psychologist"), pk=pk)
    if session.status != TestSession.Status.COMPLETED or not hasattr(session, "result"):
        messages.error(request, "Результат попытки отсутствует")
        return redirect("review_pilot", pk=session.pilot_id)
    return _result_page(request, session, conclude=True)


@role_required(User.Role.PSYCHOLOGIST)
@require_http_methods(["GET", "POST"])
def conclusion(request, pk: int):
    session = get_object_or_404(
        TestSession.objects.select_related("pilot", "result"), pk=pk)
    result = getattr(session, "result", None)
    if result is None:
        messages.error(request, "Для попытки нет результата тестирования")
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
        "attempt": attempt_number(session),
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
        for key, title, y_title, digits in (
            ("er", "ЭР", "Время, с", 2),
            ("vr", "ВР", "ВР", 3),
            ("pu", "ПУ", "ПУ", 3),
        ):
            values = [point[key] for point in points]
            chart = chart_series(values, digits=digits)
            chart.update(title=title, y_title=y_title, x_title="Попытки")
            charts.append(chart)
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
            messages.error(request, "Нельзя удалить пилота: у него есть тестирования")
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

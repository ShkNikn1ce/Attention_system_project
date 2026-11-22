"""Граничные классы: экранные формы вариантов использования.
Форма принимает действия пользователя, обращается к управляющему классу и выводит результат."""
from __future__ import annotations

from datetime import date
from typing import Optional

from attention_system.application.controllers import (
    PilotData, AuthController, PilotAdminController, DynamicsController,
    ConclusionController, AssignmentController, NormController, ReportController,
    ReviewController, OwnResultsController, TestingController)
from attention_system.application.screen import Screen
from attention_system.business.entities import (
    Conclusion, AdmissionNorm, Pilot, TestResult, SummaryReport, TestSession,
    SchulteTable)
from attention_system.business.enums import NumberOrder, Decision, Role, CheckType
from attention_system.business.errors import (
    LockoutError, LoginError, DataError, DomainError, NotFoundError)
from attention_system.business.services import DynamicsChart, SessionDetails, SuggestedConclusion
from attention_system.markup import stereotype
from attention_system.middleware.clock import Clock
from attention_system.middleware.security import WorkSession


@stereotype("граничный")
class LoginForm:
    """Прецедент 1."""

    def __init__(self, controller: AuthController, screen: Screen) -> None:
        self._controller: AuthController = controller
        self._screen: Screen = screen
        self.work: Optional[WorkSession] = None

    def open_system(self) -> None:
        self.show_login()

    def show_login(self) -> None:
        self._screen.show("Вход в систему: введите логин и пароль")

    def enter_credentials(self, login: str, password: str) -> bool:
        try:
            self.work = self._controller.authenticate(login, password)
        except LockoutError as error:
            self.show_login_error(str(error))
            return False
        except LoginError as error:
            self.show_login_error(str(error))
            self.offer_retry()
            return False
        self.open_home(self.work.role())
        return True

    def show_login_error(self, text: str) -> None:
        self._screen.show(f"Ошибка входа: {text}")

    def offer_retry(self) -> None:
        self._screen.show("Повторите ввод логина и пароля")

    def open_home(self, role: Role) -> None:
        self._screen.show(f"Открыт интерфейс: {role.label()}")


@stereotype("граничный")
class TestingForm:
    """Прецедент 2. Размер и расположение чисел выбирает пилот при подтверждении готовности."""

    def __init__(self, controller: TestingController, screen: Screen, clock: Clock) -> None:
        self._controller: TestingController = controller
        self._screen: Screen = screen
        self._clock: Clock = clock
        self._session: Optional[TestSession] = None
        self._tables: list[SchulteTable] = []
        self._current: Optional[SchulteTable] = None
        self._size: int = 3
        self._layout: NumberOrder = NumberOrder.ORDERED
        self.result: Optional[TestResult] = None

    def open_testing(self) -> bool:
        try:
            self._session = self._controller.start_testing()
        except NotFoundError as error:
            self.show_no_session(str(error))
            return False
        self.show_instructions()
        return True

    def show_instructions(self) -> None:
        self._screen.show("Инструкция: находите числа по возрастанию как можно быстрее; будет пять таблиц")

    def show_no_session(self, text: str) -> None:
        self._screen.show(text)

    def confirm_ready(self, size: int = 3,
                              layout: NumberOrder = NumberOrder.ORDERED) -> None:
        self._size, self._layout = size, layout
        self._tables = []
        self.present_tables()

    def present_tables(self) -> None:
        order = len(self._tables) + 1
        self._current = self._controller.create_table(self._session, order, self._size, self._layout)
        self.show_table(self._current)
        self._clock.start_clock()

    def show_table(self, table: SchulteTable) -> None:
        self._screen.show(f"Таблица {table.order_no} из 5: {table.numbers}")

    def enter_numbers(self) -> None:
        seconds = self._clock.stop()
        self._controller.record_time(self._current, seconds)
        self._tables.append(self._current)
        if len(self._tables) < 5:
            self.present_tables()
            return
        self.result = self._controller.finish_testing(self._session, self._tables)
        self.show_finished(self.result)

    def show_finished(self, result: TestResult) -> None:
        self._screen.show(
            f"Тестирование завершено: ЭР={result.er:.2f}, ВР={result.vr:.3f}, ПУ={result.pu:.3f}")

    def abort_testing(self) -> None:
        self._controller.cancel_testing(self._session)
        self.show_cancelled()

    def show_cancelled(self) -> None:
        self._screen.show("Тестирование прервано, результат не сохранён")


@stereotype("граничный")
class OwnResultsForm:
    """Прецедент 3."""

    def __init__(self, controller: OwnResultsController, screen: Screen) -> None:
        self._controller: OwnResultsController = controller
        self._screen: Screen = screen

    def open_own_results(self) -> bool:
        try:
            sessions = self._controller.completed_sessions()
        except NotFoundError as error:
            self.show_no_results(str(error))
            return False
        self.show_sessions(sessions)
        return True

    def show_sessions(self, sessions: list[TestSession]) -> None:
        for s in sessions:
            self._screen.show(f"Сессия {s.pk}: {s.occurred_at:%Y-%m-%d %H:%M}, {s.check_type.value}")

    def choose_session(self, session_id: int) -> None:
        result = self._controller.metrics_of(session_id)
        self.show_metrics(result)

    def show_metrics(self, result: TestResult) -> None:
        self._screen.show(f"ЭР={result.er:.2f}, ВР={result.vr:.3f}, ПУ={result.pu:.3f}")

    def show_no_results(self, text: str) -> None:
        self._screen.show(text)


@stereotype("граничный")
class AssignmentForm:
    """Прецедент 4."""

    def __init__(self, controller: AssignmentController, screen: Screen) -> None:
        self._controller: AssignmentController = controller
        self._screen: Screen = screen
        self._chosen_pilot: Optional[int] = None
        self._check_type: Optional[CheckType] = None

    def open_assignment(self) -> bool:
        try:
            pilots = self._controller.all_pilots()
        except NotFoundError as error:
            self.show_no_pilot(str(error))
            return False
        self.show_pilots(pilots)
        return True

    def show_pilots(self, pilots: list[Pilot]) -> None:
        for p in pilots:
            self._screen.show(f"Пилот {p.pk}: {p.full_name}")

    def choose_pilot_and_check(self, pilot_id: int, format_type: CheckType) -> None:
        self._chosen_pilot, self._check_type = pilot_id, format_type

    def confirm_assignment(self) -> Optional[TestSession]:
        try:
            session = self._controller.assign_test(self._chosen_pilot, self._check_type)
        except NotFoundError as error:
            self.show_no_pilot(str(error))
            return None
        self.show_saved(session)
        return session

    def show_saved(self, session: TestSession) -> None:
        self._screen.show(f"Тестирование назначено (сессия {session.pk}), пилот уведомлён")

    def show_no_pilot(self, text: str) -> None:
        self._screen.show(text)


@stereotype("граничный")
class ReviewForm:
    """Прецедент 5."""

    def __init__(self, controller: ReviewController, screen: Screen) -> None:
        self._controller: ReviewController = controller
        self._screen: Screen = screen

    def choose_pilot(self, pilot_id: int) -> bool:
        try:
            sessions = self._controller.completed_sessions(pilot_id)
        except NotFoundError as error:
            self.show_no_results(str(error))
            return False
        self.show_sessions(sessions)
        return True

    def show_sessions(self, sessions: list[TestSession]) -> None:
        for s in sessions:
            self._screen.show(f"Сессия {s.pk}: {s.occurred_at:%Y-%m-%d %H:%M}")

    def choose_session(self, session_id: int) -> None:
        self.show_metrics(self._controller.session_details(session_id))

    def show_metrics(self, details: SessionDetails) -> None:
        times = ", ".join(f"{t.time_sec:.1f}" for t in details.tables)
        r = details.result
        self._screen.show(f"Время таблиц: {times}; ЭР={r.er:.2f}, ВР={r.vr:.3f}, ПУ={r.pu:.3f}")

    def show_no_results(self, text: str) -> None:
        self._screen.show(text)


@stereotype("граничный")
class ConclusionForm:
    """Прецедент 6."""

    def __init__(self, controller: ConclusionController, screen: Screen) -> None:
        self._controller: ConclusionController = controller
        self._screen: Screen = screen
        self._draft: Optional[SuggestedConclusion] = None

    def request_conclusion(self, session_id: int) -> bool:
        try:
            self._draft = self._controller.suggest_conclusion(session_id)
        except NotFoundError as error:
            self._screen.show(str(error))
            return False
        if self._draft.within_norm:
            self.show_suggestion(self._draft)
        else:
            self.show_warning(self._draft)
        return True

    def show_suggestion(self, draft: SuggestedConclusion) -> None:
        self._screen.show(f"Предлагается заключение: {draft.decision.value}")

    def show_warning(self, draft: SuggestedConclusion) -> None:
        self._screen.show(f"Внимание: показатели вне нормы. Предлагается: {draft.decision.value}")

    def confirm_conclusion(self, decision: Optional[Decision] = None,
                              comment: str = "") -> Conclusion:
        conclusion = self._controller.save_conclusion(self._draft, decision, comment)
        self.show_saved(conclusion)
        return conclusion

    def show_saved(self, conclusion: Conclusion) -> None:
        self._screen.show(f"Заключение сохранено и передано в службу безопасности: {conclusion.decision.value}")


@stereotype("граничный")
class DynamicsForm:
    """Прецедент 7."""

    def __init__(self, controller: DynamicsController, screen: Screen) -> None:
        self._controller: DynamicsController = controller
        self._screen: Screen = screen

    def open_dynamics(self, pilot_id: int) -> bool:
        try:
            chart = self._controller.load_dynamics(pilot_id)
        except NotFoundError as error:
            self.show_no_data(str(error))
            return False
        self.show_chart(chart)
        return True

    def show_chart(self, chart: DynamicsChart) -> None:
        self._screen.show(chart.as_text())

    def show_no_data(self, text: str) -> None:
        self._screen.show(text)


@stereotype("граничный")
class PilotAdminForm:
    """Прецедент 8."""

    def __init__(self, controller: PilotAdminController, screen: Screen) -> None:
        self._controller: PilotAdminController = controller
        self._screen: Screen = screen

    def open_pilot_list(self) -> None:
        self.show_list(self._controller.all_pilots())

    def show_list(self, pilots: list[Pilot]) -> None:
        self._screen.show("Пилотов в базе: " + str(len(pilots)))
        for p in pilots:
            self._screen.show(f"{p.pk}: {p.full_name} ({p.employee_number})")

    def enter_pilot(self, payload: PilotData) -> bool:
        return self._run(lambda: self._controller.add_pilot(payload), "Пилот добавлен")

    def enter_update(self, pilot_id: int, payload: PilotData) -> bool:
        return self._run(lambda: self._controller.update_pilot(pilot_id, payload), "Данные пилота изменены")

    def delete_pilot(self, pilot_id: int) -> bool:
        return self._run(lambda: self._controller.delete_pilot(pilot_id), "Пилот удалён")

    def _run(self, action, confirmation: str) -> bool:
        try:
            action()
        except DomainError as error:
            self.show_input_error(str(error))
            self.ask_again()
            return False
        self.show_saved(confirmation)
        return True

    def show_input_error(self, text: str) -> None:
        self._screen.show(f"Ошибка: {text}")

    def ask_again(self) -> None:
        self._screen.show("Исправьте данные и повторите ввод")

    def show_saved(self, text: str) -> None:
        self._screen.show(text)


@stereotype("граничный")
class NormForm:
    """Прецедент 9."""

    def __init__(self, controller: NormController, screen: Screen) -> None:
        self._controller: NormController = controller
        self._screen: Screen = screen

    def open_norms(self) -> None:
        try:
            norm = self._controller.current_norms()
        except NotFoundError as error:
            self._screen.show(str(error))
            return
        self.show_norms(norm)

    def show_norms(self, norm: AdmissionNorm) -> None:
        self._screen.show(f"ЭР {norm.er_min}–{norm.er_max}; ВР {norm.vr_min}–{norm.vr_max}; "
                            f"ПУ {norm.pu_min}–{norm.pu_max}")

    def change_values(self, values: AdmissionNorm) -> bool:
        try:
            self._controller.save_norms(values)
        except DataError as error:
            self.show_range_error(str(error))
            return False
        self.show_saved()
        return True

    def show_range_error(self, text: str) -> None:
        self._screen.show(f"Ошибка: {text}")

    def show_saved(self) -> None:
        self._screen.show("Нормы допуска сохранены")


@stereotype("граничный")
class ReportForm:
    """Прецедент 10."""

    def __init__(self, controller: ReportController, screen: Screen) -> None:
        self._controller: ReportController = controller
        self._screen: Screen = screen

    def open_report(self) -> None:
        self._screen.show("Сводный отчёт: укажите период и группу пилотов")

    def set_period_and_group(self, start: date, end: date, pilot_ids: list[int]) -> bool:
        try:
            report = self._controller.build_report(start, end, pilot_ids)
        except (NotFoundError, DataError) as error:
            self.show_no_data(str(error))
            return False
        self.show_report(report)
        return True

    def show_report(self, report: SummaryReport) -> None:
        self._screen.show(f"Сводный отчёт {report.period_start}–{report.period_end}: пилотов {len(report.lines)}")
        for s in report.lines:
            self._screen.show(f"{s.full_name}: сессий {s.session_count}, ЭР={s.avg_er:.2f}, ВР={s.avg_vr:.3f}, ПУ={s.avg_pu:.3f}")

    def show_no_data(self, text: str) -> None:
        self._screen.show(text)

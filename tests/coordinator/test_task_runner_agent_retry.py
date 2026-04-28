from __future__ import annotations

from types import SimpleNamespace

from patchweaver.coordinator.task_runner import TaskRunner


class _TaskRepo:
    def __init__(self, *, max_attempts: int) -> None:
        self.task = SimpleNamespace(max_attempts=max_attempts)

    def get_task(self, task_id: str):
        return self.task


class _AttemptRepo:
    def __init__(self) -> None:
        self.attempts: list[object] = []

    def list_attempts(self, task_id: str) -> list[object]:
        return list(self.attempts)


class _Attempt:
    def __init__(self, *, attempt_no: int, status: str, failure_type: str | None) -> None:
        self.attempt_no = attempt_no
        self.attempt_id = f"TASK-A{attempt_no:03d}"
        self.status = status
        self.failure_type = failure_type
        self.build_exec_status = "failed" if status == "failed" else "built"
        self.target_state = None
        self.build_log_path = None


class _AttemptService:
    def __init__(self, attempt_repo: _AttemptRepo) -> None:
        self.attempt_repo = attempt_repo

    def run(self, task_id: str) -> dict[str, object]:
        attempt_no = len(self.attempt_repo.attempts) + 1
        self.attempt_repo.attempts.append(object())
        if attempt_no == 1:
            return {
                "task_id": task_id,
                "attempt_id": f"{task_id}-A001",
                "attempt_no": 1,
                "status": "failed",
                "failure_type": "kpatch_constraint",
            }
        return {
            "task_id": task_id,
            "attempt_id": f"{task_id}-A{attempt_no:03d}",
            "attempt_no": attempt_no,
            "status": "built",
            "failure_type": None,
        }


class _UnexpectedAttemptService:
    def run(self, task_id: str) -> dict[str, object]:
        raise AssertionError("attempt_service.run should not be called when max_attempts is exhausted")


def test_task_runner_auto_retries_kpatch_constraint_until_terminal_state() -> None:
    attempt_repo = _AttemptRepo()
    runner = TaskRunner.__new__(TaskRunner)
    runner.services = SimpleNamespace(
        task_repo=_TaskRepo(max_attempts=3),
        attempt_repo=attempt_repo,
    )
    runner.attempt_service = _AttemptService(attempt_repo)

    result = runner.run_task("TASK-AGENT-RETRY")

    assert result["status"] == "built"
    assert result["attempts_executed"] == 2
    assert result["attempt_results"][0]["failure_type"] == "kpatch_constraint"
    assert result["agent_retry_decisions"][0]["retry"] is True
    assert result["agent_retry_decisions"][1]["retry"] is False


def test_task_runner_stops_retry_when_attempt_budget_is_exhausted() -> None:
    attempt_repo = _AttemptRepo()
    runner = TaskRunner.__new__(TaskRunner)
    runner.services = SimpleNamespace(
        task_repo=_TaskRepo(max_attempts=1),
        attempt_repo=attempt_repo,
    )
    runner.attempt_service = _AttemptService(attempt_repo)

    result = runner.run_task("TASK-AGENT-BUDGET")

    assert result["status"] == "failed"
    assert result["attempts_executed"] == 1
    assert result["agent_retry_decisions"][0]["retry"] is False
    assert result["agent_retry_decisions"][0]["reason"] == "已达到任务最大尝试次数"


def test_task_runner_repeated_run_does_not_create_attempt_after_budget_is_exhausted() -> None:
    attempt_repo = _AttemptRepo()
    attempt_repo.attempts.append(_Attempt(attempt_no=1, status="failed", failure_type="kpatch_constraint"))
    runner = TaskRunner.__new__(TaskRunner)
    runner.services = SimpleNamespace(
        task_repo=_TaskRepo(max_attempts=1),
        attempt_repo=attempt_repo,
    )
    runner.attempt_service = _UnexpectedAttemptService()

    result = runner.run_task("TASK-AGENT-BUDGET")

    assert result["status"] == "failed"
    assert result["attempt_no"] == 1
    assert result["failure_type"] == "kpatch_constraint"
    assert result["max_attempts_exhausted"] is True
    assert result["attempts_executed"] == 0
    assert len(attempt_repo.attempts) == 1

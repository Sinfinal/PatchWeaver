"""FastAPI 依赖装配。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from patchweaver.config.loader import (
    discover_project_root,
    load_build_config,
    load_logging_config,
    load_prompts_config,
    load_rules_config,
    load_skills_config,
    load_system_config,
    load_verify_config,
)
from patchweaver.config.resolver import resolve_runtime
from patchweaver.coordinator.task_runner import TaskRunner
from patchweaver.doctor.service import DoctorService
from patchweaver.reporter.doctor_writer import DoctorWriter
from patchweaver.storage.artifact_repo import ArtifactRepository
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.task_repo import TaskRepository


@dataclass(slots=True)
class ApiContext:
    """收拢 API 运行时会频繁用到的依赖。"""

    project_root: Path
    runtime: object
    system_config: object
    build_config: object
    verify_config: object
    prompts_config: object
    skills_config: object
    rules_config: object
    logging_config: object
    task_repo: TaskRepository
    attempt_repo: AttemptRepository
    artifact_repo: ArtifactRepository
    doctor_service: DoctorService
    doctor_writer: DoctorWriter

    def build_task_runner(self) -> TaskRunner:
        """按当前配置创建一个任务编排器。"""

        return TaskRunner(
            runtime=self.runtime,
            build_config=self.build_config,
            verify_config=self.verify_config,
            prompts_config=self.prompts_config,
        )


@lru_cache(maxsize=1)
def get_api_context() -> ApiContext:
    """创建并缓存 API 共享上下文。"""

    project_root = discover_project_root()
    runtime = resolve_runtime(project_root=project_root)
    system_config = load_system_config(project_root)
    build_config = load_build_config(project_root)
    verify_config = load_verify_config(project_root)
    prompts_config = load_prompts_config(project_root)
    skills_config = load_skills_config(project_root)
    rules_config = load_rules_config(project_root)
    logging_config = load_logging_config(project_root)

    return ApiContext(
        project_root=project_root,
        runtime=runtime,
        system_config=system_config,
        build_config=build_config,
        verify_config=verify_config,
        prompts_config=prompts_config,
        skills_config=skills_config,
        rules_config=rules_config,
        logging_config=logging_config,
        task_repo=TaskRepository(runtime.database_path),
        attempt_repo=AttemptRepository(runtime.database_path),
        artifact_repo=ArtifactRepository(runtime.database_path),
        doctor_service=DoctorService(),
        doctor_writer=DoctorWriter(),
    )

"""FastAPI 依赖装配"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from patchweaver.config.loader import (
    discover_project_root,
    load_logging_config,
    load_models_config,
    load_rag_config,
    load_rules_config,
    load_system_config,
)
from patchweaver.config.resolver import load_effective_configs, resolve_runtime
from patchweaver.coordinator.task_runner import TaskRunner
from patchweaver.doctor.service import DoctorService
from patchweaver.reporter.doctor_writer import DoctorWriter
from patchweaver.storage.artifact_repo import ArtifactRepository
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.task_repo import TaskRepository


@dataclass(slots=True)
class ApiContext:
    """收拢 API 运行时会频繁用到的依赖"""

    project_root: Path
    runtime: object
    system_config: object
    build_config: object
    verify_config: object
    prompts_config: object
    skills_config: object
    rules_config: object
    logging_config: object
    models_config: object
    rag_config: object
    task_repo: TaskRepository
    attempt_repo: AttemptRepository
    artifact_repo: ArtifactRepository
    doctor_service: DoctorService
    doctor_writer: DoctorWriter

    def build_task_runner(self, *, profile_name: str | None = None, max_attempts: int | None = None) -> TaskRunner:
        """按当前配置创建一个任务编排器"""

        runtime = resolve_runtime(
            project_root=self.project_root,
            profile_name=profile_name,
            cli_database_path=str(self.runtime.database_path),
            cli_max_attempts=max_attempts,
        )
        configs = load_effective_configs(project_root=self.project_root, profile_name=runtime.profile_name)
        return TaskRunner(
            runtime=runtime,
            build_config=configs["build"],
            verify_config=configs["verify"],
            prompts_config=configs["prompts"],
            skills_config=configs["skills"],
            models_config=self.models_config,
        )


@lru_cache(maxsize=1)
def get_api_context() -> ApiContext:
    """创建并缓存 API 共享上下文"""

    project_root = discover_project_root()
    runtime = resolve_runtime(project_root=project_root)
    system_config = load_system_config(project_root)
    effective_configs = load_effective_configs(project_root=project_root, profile_name=runtime.profile_name)
    rules_config = load_rules_config(project_root)
    logging_config = load_logging_config(project_root)
    models_config = load_models_config(project_root)
    rag_config = load_rag_config(project_root)

    return ApiContext(
        project_root=project_root,
        runtime=runtime,
        system_config=system_config,
        build_config=effective_configs["build"],
        verify_config=effective_configs["verify"],
        prompts_config=effective_configs["prompts"],
        skills_config=effective_configs["skills"],
        rules_config=rules_config,
        logging_config=logging_config,
        models_config=models_config,
        rag_config=rag_config,
        task_repo=TaskRepository(runtime.database_path, project_root),
        attempt_repo=AttemptRepository(runtime.database_path, project_root),
        artifact_repo=ArtifactRepository(runtime.database_path, project_root),
        doctor_service=DoctorService(),
        doctor_writer=DoctorWriter(project_root),
    )

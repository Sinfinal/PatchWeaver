"""核心数据对象定义"""

from patchweaver.models.attempt import AttemptRecord, AttemptState, FailureRecord
from patchweaver.models.constraint import ConstraintReport, RiskItem
from patchweaver.models.context import BootstrapManifest, ContextBundle
from patchweaver.models.doctor import DoctorCheck, DoctorReport
from patchweaver.models.evidence import EvidenceBundle, EvidenceSpan
from patchweaver.models.failover import FailoverRecord
from patchweaver.models.harness import ArtifactRef, HarnessTrace, StateTransition, SubagentRecord, ToolCallRecord
from patchweaver.models.memory import FailureMemoryEntry, RecipeMemoryEntry
from patchweaver.models.patch import PatchBundle, SourceEvidence
from patchweaver.models.prompt import PromptPacket
from patchweaver.models.report import AttemptDigest, FinalReport
from patchweaver.models.rewrite import (
    ApplyPrecheckReport,
    RewriteCandidate,
    RewritePlan,
    TransformationStep,
    TransformationTrace,
)
from patchweaver.models.semantic import SemanticCard
from patchweaver.models.skill import SkillManifest, SkillRouteDecision
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem, ValidationReport

__all__ = [
    "ArtifactRef",
    "ApplyPrecheckReport",
    "AttemptDigest",
    "AttemptRecord",
    "AttemptState",
    "BootstrapManifest",
    "ConstraintReport",
    "ContextBundle",
    "DoctorCheck",
    "DoctorReport",
    "EvidenceBundle",
    "EvidenceSpan",
    "FailoverRecord",
    "FailureRecord",
    "FailureMemoryEntry",
    "FinalReport",
    "HarnessTrace",
    "PatchBundle",
    "PromptPacket",
    "RewriteCandidate",
    "RewritePlan",
    "RecipeMemoryEntry",
    "RiskItem",
    "SemanticCard",
    "SkillManifest",
    "SkillRouteDecision",
    "SourceEvidence",
    "StateTransition",
    "SubagentRecord",
    "TaskContext",
    "ToolCallRecord",
    "TransformationStep",
    "TransformationTrace",
    "ValidationItem",
    "ValidationReport",
]

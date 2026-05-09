"""原语模板库"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class PrimitiveTemplateSpec:
    """描述一个 recipe 对应的模板、SmPL 规则和原语集合"""

    name: str
    template_path: Path | None
    smpl_path: Path | None
    primitives: tuple[str, ...]
    route_family: str
    requires_kernel_scaffold: bool


class PrimitiveTemplates:
    """负责提供可执行 recipe 的模板索引"""

    def __init__(self, project_root: Path | None = None, manifest_path: Path | None = None) -> None:
        """初始化模板清单"""

        self.project_root = (project_root or Path.cwd()).resolve()
        self.manifest_path = manifest_path or self.project_root / "recipes" / "manifests" / "default.yaml"
        self._specs: dict[str, PrimitiveTemplateSpec] | None = None

    def catalog(self) -> list[PrimitiveTemplateSpec]:
        """返回当前 recipe 模板清单"""

        if self._specs is None:
            self._specs = self._load_specs()
        return list(self._specs.values())

    def get(self, recipe_name: str) -> PrimitiveTemplateSpec | None:
        """按 recipe 名称查找模板定义"""

        if self._specs is None:
            self._specs = self._load_specs()
        return self._specs.get(recipe_name)

    def render(self, recipe_name: str) -> str:
        """返回指定 recipe 的工程说明"""

        spec = self.get(recipe_name)
        if spec is None:
            return f"{recipe_name} 未登记到 recipe 模板清单"
        template_state = "present" if spec.template_path and spec.template_path.exists() else "missing"
        smpl_state = "present" if spec.smpl_path and spec.smpl_path.exists() else "missing"
        return (
            f"{spec.name}: route={spec.route_family}; "
            f"primitives={','.join(spec.primitives)}; "
            f"template={template_state}; smpl={smpl_state}; "
            f"kernel_scaffold={spec.requires_kernel_scaffold}"
        )

    def by_primitive(self, primitive_name: str) -> list[PrimitiveTemplateSpec]:
        """按原语反查可用 recipe"""

        return [spec for spec in self.catalog() if primitive_name in spec.primitives]

    def _load_specs(self) -> dict[str, PrimitiveTemplateSpec]:
        """读取 recipe manifest 并折叠为稳定索引"""

        if not self.manifest_path.exists():
            return {}
        payload = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8")) or {}
        items = payload.get("recipes") if isinstance(payload, dict) else []
        specs: dict[str, PrimitiveTemplateSpec] = {}
        for item in items or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            primitives = tuple(str(value) for value in item.get("primitives") or [])
            specs[name] = PrimitiveTemplateSpec(
                name=name,
                template_path=self._resolve_optional_path(item.get("template")),
                smpl_path=self._resolve_optional_path(item.get("smpl")),
                primitives=primitives,
                route_family=self._route_family(name=name, primitives=primitives),
                requires_kernel_scaffold=bool(
                    {"callback", "shadow_variable", "state_preserving"}.intersection(primitives)
                ),
            )
        return specs

    def _resolve_optional_path(self, raw_path: object) -> Path | None:
        """把 manifest 中的相对路径解析到项目根目录"""

        if raw_path is None:
            return None
        value = str(raw_path).strip()
        if not value:
            return None
        path = Path(value)
        return path if path.is_absolute() else self.project_root / path

    def _route_family(self, *, name: str, primitives: tuple[str, ...]) -> str:
        """根据 recipe 名称和原语推导路线族"""

        if "callback" in primitives and "shadow_variable" in primitives:
            return "callback_shadow"
        if "callback" in primitives:
            return "callback"
        if "shadow_variable" in primitives and "state_preserving" in primitives:
            return "state_preserving"
        if "shadow_variable" in primitives:
            return "shadow_variable"
        if "direct_apply" in primitives:
            return "direct_apply"
        if "section_change_avoidance" in primitives or "section_change" in name:
            return "section_change_avoidance"
        if "smpl" in primitives:
            return "smpl_primary"
        return "wrapper"

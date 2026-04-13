"""Patch 规范化骨架。"""

from __future__ import annotations

from pathlib import Path
import re


class PatchNormalizer:
    """负责管理原始补丁到规范化补丁的转换入口。"""

    def normalize(self, raw_patch_path: Path, normalized_patch_path: Path) -> Path:
        """返回规范化补丁路径。"""

        raw_text = raw_patch_path.read_text(encoding="utf-8")
        normalized_text = self.normalize_text(raw_text)
        normalized_patch_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_patch_path.write_text(normalized_text, encoding="utf-8")
        return normalized_patch_path

    def normalize_text(self, patch_text: str) -> str:
        """统一换行和 diff 路径头。"""

        text = patch_text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(
            r"(?m)^--- (?!a/|/dev/null)(.+)$",
            lambda match: f"--- a/{match.group(1).strip()}",
            text,
        )
        text = re.sub(
            r"(?m)^\+\+\+ (?!b/|/dev/null)(.+)$",
            lambda match: f"+++ b/{match.group(1).strip()}",
            text,
        )
        if not text.endswith("\n"):
            text += "\n"
        return text

    def extract_affected_files(self, patch_text: str) -> list[str]:
        """提取 patch 中涉及的文件路径。"""

        files: list[str] = []
        seen: set[str] = set()
        for line in patch_text.splitlines():
            if line.startswith("diff --git "):
                parts = line.split()
                if len(parts) >= 4:
                    path = parts[3]
                    if path.startswith("b/"):
                        path = path[2:]
                    if path and path != "/dev/null" and path not in seen:
                        seen.add(path)
                        files.append(path)
            elif line.startswith("+++ "):
                path = line[4:].strip()
                if path.startswith("b/"):
                    path = path[2:]
                if path and path != "/dev/null" and path not in seen:
                    seen.add(path)
                    files.append(path)
        return files


# -*- coding: utf-8 -*-
"""Generate the daily PatchWeaver work plan"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""

    parser = argparse.ArgumentParser(description="Generate PatchWeaver daily work plan")
    parser.add_argument("--docs-root", default=r"D:\spaces\python\b312_docs")
    parser.add_argument("--project-root", default=r"D:\spaces\ai\PatchWeaver")
    return parser.parse_args()


def json_array_count(path: Path) -> int:
    """Count top-level JSON array items"""

    if not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(payload, list):
        return len(payload)
    return 1 if payload else 0


def git_short_status(path: Path) -> str:
    """Return a compact git status summary"""

    if not (path / ".git").exists():
        return "not_git_repo"
    proc = subprocess.run(
        ["git", "-C", str(path), "status", "--short"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        return "clean"
    return f"{len(lines)} changed item(s)"


def build_plan(*, docs_root: Path, project_root: Path) -> tuple[Path, Path]:
    """Build and write today's plan"""

    today = datetime.now()
    date_id = today.strftime("%Y%m%d")
    date_text = today.strftime("%Y-%m-%d")
    output_dir = docs_root / "阶段性成果" / "每日工作规划"
    output_dir.mkdir(parents=True, exist_ok=True)

    positive_fixture = project_root / "evaluations" / "fixtures" / "challenge_positive_pool_confirmed_v0426.json"
    kpatch_fixture = project_root / "evaluations" / "fixtures" / "challenge_kpatch_constraint_pool_v0427.json"
    positive_count = json_array_count(positive_fixture)
    kpatch_count = json_array_count(kpatch_fixture)
    positive_target = 10
    positive_gap = max(0, positive_target - positive_count)
    project_status = git_short_status(project_root)
    docs_status = git_short_status(docs_root)

    if positive_gap > 0:
        main_mode = "继续围绕构建成功率收口：源码基线对齐、正向池扩展、kpatch_constraint 专项突破"
        must_focus = "正向池仍不足 10 条，今日不能把主要时间投入 UI、文档润色或新技术扩展"
    else:
        main_mode = "进入代表集复测与交付收口：稳定性、复现脚本、Demo 和答辩材料"
        must_focus = "正向池已达到阶段数量目标，今日重点应转向代表集成功率和可复现交付"

    content = f"""# PatchWeaver 今日工作规划 {date_text}

## 1. 今日定位

今日主线：{main_mode}

当前自动读取到的状态：

1. confirmed 正向样例池：{positive_count} / {positive_target}
2. 正向池缺口：{positive_gap}
3. kpatch_constraint 专项池样例数：{kpatch_count}
4. 本地项目 Git 状态：{project_status}
5. 文档仓库 Git 状态：{docs_status}

判断：

{must_focus}

## 2. 必须完成的任务

### 2.1 开工前状态确认

目标：避免在错误状态上继续开发

任务：

1. 查看 `D:/spaces/ai/PatchWeaver` 和 `D:/spaces/python/b312_docs` 的 Git 状态
2. 确认昨天验证机产物、报告和本地代码是否已经同步
3. 如果有未提交改动，先按“代码 / 文档 / 验证证据”分类，不要混在一起处理

完成标准：

1. 能说清楚今天是在什么代码版本上继续
2. 能说清楚今天验证机上要复测哪些任务

### 2.2 未修复 stable source 基线推进

目标：减少 `already_patched`、`context_mismatch`、`source_too_new_or_already_patched` 对正向池扩展的污染

任务：

1. 从最近失败样例中选 1 到 2 个源码状态问题样例
2. 查看其 `stable_source_baseline_ref`
3. 判断验证机是否已有可用 git stable source tree
4. 如果没有，今天至少完成准备方案、目录规范和脚本入口设计
5. 如果有，尝试把样例切到 `<stable_commit>^` 基线后复测

完成标准：

1. 对每个样例明确写出“能否准备未修复源码基线”
2. 不能准备时，必须写出阻塞原因，不继续盲目换 recipe

### 2.3 正向样例池扩展

目标：把 confirmed 正向样例池从当前数量推进到 `10+`

任务：

1. 只筛选能映射到具体 `.ko` 模块目标的样例
2. 每批控制在 6 到 12 个 CVE
3. 每条 `run` 必须带 timeout
4. `already_patched`、`feature_not_enabled`、`kpatch_constraint` 不计入正向成功率
5. 只有 `.ko + load/unload/smoke/selftest` 通过，才加入 confirmed 正向池

完成标准：

1. 输出本轮筛选报告
2. 如果新增 confirmed 样例，更新正向池 fixture
3. 如果没有新增，按失败桶统计原因

### 2.4 kpatch_constraint 专项突破

目标：不要只识别 kpatch 后端约束，要尝试让一部分样例从不可构建变成可构建

任务：

1. 固定使用专项池样例，不随机更换
2. 优先处理 `.rela.call_sites` 和 `unsupported section change(s)`
3. 检查 `failure_record.json` 中是否有对象文件、源码文件、函数名和触发原因
4. 检查 `section_change_avoidance` 是否真正改变 patch 形态
5. 如果多轮仍命中同一 section 签名，标记为 `kpatch_constraint_unresolved` 或 `unfixable_by_livepatch`

完成标准：

1. 至少完成 1 个专项样例的根因复核或代码修复
2. 验证机上完成复测
3. 报告中写清楚“突破了什么”或“为什么不能突破”

### 2.5 Agent 闭环检查

目标：让系统不只是解释失败，而是根据失败自动调整下一轮策略

任务：

1. 检查失败后是否写出 `agent_next_action`
2. 检查下一轮 attempt 是否真的依据失败类型调整策略
3. 检查 `route_effectiveness` 是否能识别无效重试
4. 对 `patch_apply_failed`、`kpatch_constraint`、`compile_failed` 分别确认下一步动作是否合理

完成标准：

1. 今天新增或复测的任务必须能在报告中看到失败归因和下一步动作
2. 不允许只有“失败了”这种粗粒度结论

### 2.6 每日收口

目标：当天工作必须留下可追溯证据

任务：

1. 保存验证机任务 ID、命令、输出摘要和关键 JSON 路径
2. 更新测试验收或阶段性报告
3. 同步必要的设计文档口径
4. 记录还没解决的问题，不用把失败包装成成功

完成标准：

1. 有一份当天可读的工作记录
2. 能明确说明距离赛题 `60%+` 成功率又推进了多少

## 3. 额外任务

如果今天工作时间较长，在必须任务完成后再做以下内容：

1. 扩展 RAG seed 覆盖范围，但只用于筛样和解释，不把 RAG 当成构建成功保证
2. 优化 `screen_challenge_pool.py` 的批量报告，让每个失败桶自动给出下一步建议
3. 为 stable source 基线准备做缓存目录规范和清理策略
4. 选 1 个 Web/API 页面展示正向池、kpatch_constraint 专项池和失败归因
5. 整理 Demo 脚本草案，但不要替代真实 `.ko` 成功率工作
6. 更新答辩材料中的术语解释，保持和阶段报告一致

## 4. 今日不要做的事

1. 不要无边界随机跑新 CVE
2. 不要把 `analyze` 成功当成热补丁成功
3. 不要把 `already_patched` 算入正向成功率
4. 不要把 `feature_not_enabled` 当成系统能力失败
5. 不要在没有验证机复测的情况下宣称构建链路已修复
6. 不要新增大模块，除非它直接服务于源码基线、正向池或 kpatch_constraint

## 5. 长期收手线

达到以下条件后，停止新增能力，转向交付：

1. confirmed 正向样例池 `>=10`
2. 代表集完整热补丁成功率 `>=60%`
3. 平均尝试轮次 `<=5`
4. report/replay/workspace 证据完整
5. Web/API 能展示任务、结果、失败归因和产物

未达到前，优先级保持不变：

1. 源码基线对齐
2. 正向样例池扩展
3. kpatch_constraint 专项突破
4. Agent 失败驱动闭环
"""

    output_path = output_dir / f"PatchWeaver-今日工作规划_{date_id}.md"
    latest_path = output_dir / "PatchWeaver-今日工作规划_latest.md"
    output_path.write_text(content, encoding="utf-8")
    latest_path.write_text(content, encoding="utf-8")
    return output_path, latest_path


def main() -> int:
    """CLI entry"""

    args = parse_args()
    output_path, latest_path = build_plan(docs_root=Path(args.docs_root), project_root=Path(args.project_root))
    print(f"已生成: {output_path}")
    print(f"latest: {latest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

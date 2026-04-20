export type StageCard = {
  id: string;
  title: string;
  description: string;
  artifacts: string[];
};

export type ProfileCard = {
  name: string;
  attempts: string;
  description: string;
  highlights: string[];
};

export type HighlightCard = {
  title: string;
  description: string;
  meta?: string;
};

export const projectSummary = {
  alias: "补天",
  title: "面向 Anolis OS 热补丁生成与交付的工程控制台",
  subtitle: "围绕任务主链、固定样例评测、报告沉淀与回放证据，提供一套可排障、可展示、可验收的 Web 控制面。",
} as const;

export const controlPlanes: HighlightCard[] = [
  {
    title: "控制面",
    description: "发起任务、查看状态、定位失败，并触发分析、执行和报告动作。",
  },
  {
    title: "展示面",
    description: "把从 CVE 到最终报告的链路压缩成适合演示和答辩的证据面板。",
  },
  {
    title: "运维面",
    description: "围绕环境诊断、日志尾流和构建可用性做日常联调与排障。",
  },
  {
    title: "评测面",
    description: "集中查看固定样例分组、阶段统计和单样例回放摘要。",
  },
];

export const architectureStages: StageCard[] = [
  {
    id: "prepare",
    title: "01 输入归一化",
    description: "围绕 CVE、补丁与上下文整理统一输入包，为主链后续阶段提供稳定入口。",
    artifacts: ["task_context.json", "patch_bundle.json", "normalized.patch"],
  },
  {
    id: "analyze",
    title: "02 语义分析",
    description: "提取修复意图、风险点与上下文约束，沉淀 semantic card 与分析轨迹。",
    artifacts: ["semantic_card.json", "constraint_report.json", "analysis_trace.json"],
  },
  {
    id: "rewrite",
    title: "03 约束诊断与改写",
    description: "结合规则、原语与 Recipe 生成 rewrite_plan 与 rewritten.patch。",
    artifacts: ["rewrite_plan.json", "rewritten.patch", "transformation_trace.json"],
  },
  {
    id: "build",
    title: "04 构建与装载",
    description: "通过 kpatch-build 推进构建，记录构建日志与失败归因。",
    artifacts: ["build.log", "failure_record.json", "module.ko"],
  },
  {
    id: "validate",
    title: "05 验证与防回归",
    description: "围绕 load、unload、smoke 与语义守卫确认补丁的可交付性。",
    artifacts: ["validation_report.json", "semantic_precheck.json", "validate.log"],
  },
  {
    id: "report",
    title: "06 报告与回放",
    description: "沉淀 report.json、report.md、阶段统计和回放索引，支撑复盘与展示。",
    artifacts: ["report.json", "report.md", "harness_trace.json"],
  },
];

export const buildProfiles: ProfileCard[] = [
  {
    name: "dev",
    attempts: "最多 2 轮",
    description: "适合本地快速联调与问题定位，优先保证最短反馈回路。",
    highlights: ["轻量验证", "便于排错", "适合开发期"],
  },
  {
    name: "demo",
    attempts: "最多 3 轮",
    description: "默认演示档位，兼顾链路完整性、日志沉淀和整体运行成本。",
    highlights: ["主链可展示", "保留回放", "适合日常联调"],
  },
  {
    name: "full",
    attempts: "最多 5 轮",
    description: "适合完整评测与正式跑样例，保留更多验证动作与统计结果。",
    highlights: ["验证更全", "统计更完整", "适合正式验收"],
  },
];

export const logGuides: HighlightCard[] = [
  {
    title: "先看 system log",
    description: "优先确认是不是路径、配置、数据库或 API 层问题。",
  },
  {
    title: "再看 build log",
    description: "快速判断已经推进到 patch apply、编译还是 kpatch 约束阶段。",
  },
  {
    title: "最后回看 report",
    description: "用 report.json、report.md 和 replay 摘要串起整轮证据。",
  },
];

export const ruleHighlights: HighlightCard[] = [
  {
    title: "风险规则",
    description: "对 missing_fentry、init_section、global_data_change 等高频问题做识别。",
  },
  {
    title: "原语规则",
    description: "把 wrapper、direct_apply 等 livepatch 原语固化成可复用选择项。",
  },
  {
    title: "Recipe 配方",
    description: "把规则命中、原语组合与改写模板挂到同一条可解释链路里。",
  },
];

export const skillHighlights: HighlightCard[] = [
  {
    title: "retrieval",
    description: "负责来源链与 patch 证据整理。",
    meta: "优先 stable，再看 upstream",
  },
  {
    title: "rewrite_recipe",
    description: "负责候选配方、原语选择和改写提示组织。",
    meta: "只写主链允许的产物",
  },
  {
    title: "failure_analysis",
    description: "负责构建失败解释、回退建议和下一轮提示。",
    meta: "默认只读旁路",
  },
  {
    title: "validation",
    description: "负责验证矩阵、语义守卫和阶段报告输入。",
    meta: "围绕 validation_report 汇总",
  },
];

export const settingsFacts: HighlightCard[] = [
  {
    title: "目标内核",
    description: "6.6.102-5.2.an23.x86_64",
  },
  {
    title: "目标系统",
    description: "Anolis OS 23.4",
  },
  {
    title: "构建工具",
    description: "kpatch-build",
  },
  {
    title: "模型拓扑",
    description: "单主模型 + 可选辅助模型",
  },
  {
    title: "状态真相源",
    description: "SQLite + workspace artifacts",
  },
];

export const reportHighlights: HighlightCard[] = [
  {
    title: "任务报告",
    description: "按 task_id 回看 report.json、report.md 和任务级关键证据。",
  },
  {
    title: "固定样例",
    description: "按评测分组查看 summary.json、summary.md 和单样例结果。",
  },
  {
    title: "阶段统计",
    description: "聚合成功率、平均尝试轮次和失败分布，服务阶段汇报与封版核对。",
  },
];

export const reportGroupGuides: HighlightCard[] = [
  {
    title: "challenge-dev",
    description: "开发期固定样例，适合日常联调和问题回归。",
  },
  {
    title: "holdout",
    description: "验收期保留样例，适合独立核对整体泛化能力。",
  },
  {
    title: "regression",
    description: "回归样例，适合封版前做稳定性与一致性复查。",
  },
];

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
  name: "PatchWeaver",
  alias: "补天",
  title: "面向 Anolis OS 热补丁生成与交付的工程控制台",
  subtitle: "围绕任务运行、失败定位、构建验证和报告沉淀组织统一的可观测界面。",
};

export const overviewTargets: HighlightCard[] = [
  {
    title: "60%+ 竞赛达标率",
    description: "以真实样例为基线，持续拉升热补丁生成和验证成功率。",
  },
  {
    title: "70%+ 公开集命中率",
    description: "面向公开挑战样例集构建可复现的稳定主链路，而不是偶然成功。",
  },
  {
    title: "90%+ 模块加载成功率",
    description: "不只要求构建完成，更强调模块可加载、可验证、可解释。",
  },
  {
    title: "100% 报告覆盖率",
    description: "所有任务都应沉淀 report.json、report.md 和回放证据链。",
  },
];

export const architectureStages: StageCard[] = [
  {
    id: "retrieve",
    title: "01 输入归一化",
    description: "围绕 CVE、补丁和上下文整理统一输入包，为后续分析提供稳定入口。",
    artifacts: ["patch_bundle.json", "normalized.patch", "task_context.json"],
  },
  {
    id: "analysis",
    title: "02 语义分析",
    description: "抽取修复意图、风险点和上下文约束，形成可消费的语义卡片。",
    artifacts: ["semantic_card.json", "context_bundle.json", "analysis_trace.json"],
  },
  {
    id: "rewrite",
    title: "03 约束诊断与改写",
    description: "识别 livepatch 风险并结合 Recipe、SmPL 生成可解释的改写方案。",
    artifacts: ["constraint_report.json", "rewrite_plan.json", "rewritten.patch"],
  },
  {
    id: "build",
    title: "04 构建与装载",
    description: "通过 kpatch-build 生成可加载模块，并记录构建日志和失败上下文。",
    artifacts: ["build.log", "failure_record.json", "module.ko"],
  },
  {
    id: "validate",
    title: "05 验证与防回归",
    description: "围绕 load、unload、smoke 和语义约束确认补丁可以真正交付。",
    artifacts: ["validation_report.json", "semantic_precheck.json", "load.log"],
  },
  {
    id: "report",
    title: "06 报告与回放",
    description: "沉淀最终报告、时间线和回放索引，支撑答辩、排障和经验复用。",
    artifacts: ["report.json", "report.md", "HarnessTrace / AttemptState"],
  },
];

export const controlPlanes: HighlightCard[] = [
  {
    title: "控制视图",
    description: "发起任务、跟踪状态，并触发分析、执行和报告动作。",
  },
  {
    title: "交付视图",
    description: "把 CVE 到报告的链路压缩成清晰、可演示、可复盘的证据面板。",
  },
  {
    title: "运维视图",
    description: "聚焦环境诊断、日志尾流和构建环境快照，降低排障成本。",
  },
];

export const repositoryAssets: HighlightCard[] = [
  {
    title: "7 个项目技能",
    description: "retrieval、semantic_card、constraint_diagnosis、rewrite_recipe、failure_analysis、validation、reporting。",
  },
  {
    title: "6 条核心规则",
    description: "2 条 livepatch primitive 与 4 条 risk rules，支撑风险识别和改写路径选择。",
  },
  {
    title: "3 档运行 profile",
    description: "dev、demo、full 三档执行强度，用于联调、演示与完整验证。",
  },
  {
    title: "2 份经验记忆",
    description: "failure_memory.json 与 recipe_memory.json 负责沉淀失败经验和可复用策略。",
  },
];

export const buildProfiles: ProfileCard[] = [
  {
    name: "dev",
    attempts: "最多 2 轮",
    description: "适合本地快速调试，优先保证最短反馈回路。",
    highlights: ["快速排障", "最少等待", "适合开发联调"],
  },
  {
    name: "demo",
    attempts: "最多 3 轮",
    description: "兼顾稳定性与速度，是联调与演示阶段的推荐档位。",
    highlights: ["平衡速度", "推荐默认", "适合现场展示"],
  },
  {
    name: "full",
    attempts: "最多 5 轮",
    description: "适合完整评测和较稳定的正式运行，带更多约束检查。",
    highlights: ["完整验证", "约束更全", "适合正式跑样例"],
  },
];

export const ruleHighlights: HighlightCard[] = [
  {
    title: "direct_apply_ready",
    description: "判断是否可以走最小改写路径，减少不必要的结构性扰动。",
  },
  {
    title: "global_data_change",
    description: "对 static、全局变量等变化保持高敏感度，优先考虑 wrapper 化策略。",
  },
  {
    title: "header_abi_change",
    description: "对头文件与 ABI 变化做高优先级拦截，避免生成不可安全装载的补丁。",
  },
  {
    title: "init_section / missing_fentry",
    description: "覆盖 livepatch 常见硬约束，帮助快速区分 patch 问题和 kpatch 限制。",
  },
];

export const skillHighlights: HighlightCard[] = [
  {
    title: "semantic_card",
    description: "消费 patch bundle 和归一化输入，输出 semantic_card.json。",
    meta: "只读分析阶段",
  },
  {
    title: "rewrite_recipe",
    description: "结合 semantic_card 和 constraint_report 生成 rewrite_plan 与 rewritten.patch。",
    meta: "主链路改写阶段",
  },
  {
    title: "validation",
    description: "围绕构建摘要与改写结果输出 validation_report 和校验日志。",
    meta: "交付验证阶段",
  },
];

export const settingsFacts: HighlightCard[] = [
  {
    title: "默认内核",
    description: "6.6.102-5.2.an23.x86_64",
  },
  {
    title: "工作区根目录",
    description: "workspaces",
  },
  {
    title: "数据库路径",
    description: "data/patchweaver.db",
  },
  {
    title: "Manifest 目录",
    description: "data/manifests",
  },
  {
    title: "默认最大尝试轮数",
    description: "5",
  },
  {
    title: "报告格式",
    description: "json / md",
  },
];

export const logGuides: HighlightCard[] = [
  {
    title: "system_log",
    description: "用于判断 API、调度器和目录扫描等系统层问题，是排查“为什么没跑起来”的第一入口。",
  },
  {
    title: "latest_build_log",
    description: "用于定位 patch apply、编译、kpatch-build 和装载细节，是判断失败阶段的第一证据。",
  },
];

export const engineeringPrinciples: HighlightCard[] = [
  {
    title: "不重写 Python 主链",
    description: "前端负责查看、展示、回放和轻量控制，不承接核心编排逻辑。",
  },
  {
    title: "先读后控",
    description: "先让人看清当前系统状态，再提供必要而克制的动作入口。",
  },
  {
    title: "证据链优先",
    description: "失败记录、日志尾流、报告和回放文件，比单一成功率更重要。",
  },
];

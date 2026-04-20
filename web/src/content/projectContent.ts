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
  alias: "PatchWeaver / 补天",
  title: "面向 Anolis OS ANCK 内核的 CVE 热补丁自动生成智能体",
  subtitle: "围绕检索、改写、构建、验证和回放组织最小可交付控制面。",
} as const;

export const controlPlanes = [
  { title: "任务总览" },
  { title: "阶段评测" },
  { title: "日志排障" },
  { title: "环境诊断" },
] as const;

export const logGuides = [
  { title: "先看 system log", description: "优先判断是否是路径、配置或数据库层问题。" },
  { title: "再看 build log", description: "确认已经推进到 patch apply、编译还是 kpatch 约束层。" },
  { title: "最后回看 report", description: "用 report.json 和 replay 摘要串起整轮证据。" },
] as const;

export const ruleHighlights = [
  { title: "风险规则", description: "对 missing_fentry、init_section、global_data_change 等高频问题做识别。" },
  { title: "原语规则", description: "把 wrapper、direct_apply 这类 livepatch 原语固定成可复用选择项。" },
  { title: "Recipe 配方", description: "把规则命中、原语组合和改写模板挂到同一条可解释链路上。" },
] as const;

export const skillHighlights = [
  { title: "retrieval", description: "负责来源链与 patch 证据整理。", meta: "先 stable，后 upstream。" },
  { title: "rewrite_recipe", description: "负责候选配方、原语选择和改写提示组织。", meta: "只写主链允许的产物。" },
  { title: "failure_analysis", description: "负责构建失败解释、回退建议和下一轮提示。", meta: "默认只读旁路。" },
  { title: "validation", description: "负责验证矩阵、语义守卫和阶段报告输入。", meta: "围绕 validation_report 汇总。" },
] as const;

export const settingsFacts = [
  { title: "目标内核", description: "6.6.102-5.2.an23.x86_64" },
  { title: "目标系统", description: "Anolis OS 23.4" },
  { title: "构建工具", description: "kpatch-build" },
  { title: "状态真相源", description: "SQLite + workspace artifacts" },
] as const;

export const buildProfiles = [
  {
    name: "dev",
    attempts: "2 次",
    description: "本地快速联调，优先压低尝试轮数和执行开销。",
    highlights: ["轻量验证", "便于排错", "适合开发期"],
  },
  {
    name: "demo",
    attempts: "3 次",
    description: "默认演示档位，兼顾链路完整性与运行成本。",
    highlights: ["主链可展示", "保留回放", "适合日常联调"],
  },
  {
    name: "full",
  },


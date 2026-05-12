const FAILURE_SIGNAL_MEANINGS: Record<string, string> = {
  build_cache_incomplete: "源码树缺少 Module.symvers、vmlinux 或模块缓存，需先修复构建基线",
  build_env_missing: "构建工具或内核调试文件缺失，需先完成环境诊断和修复",
  compile_failed: "补丁进入编译阶段后失败，通常需要检查源码上下文、依赖或编译参数",
  dependency_gap: "模块依赖没有补齐，modpost 或链接阶段找不到需要的符号",
  ineffective_retry: "上一轮策略没有带来有效变化，Agent 应降权或禁用该策略",
  kernel_src_missing: "没有找到目标内核源码树，无法进行 apply 预检或 kpatch 构建",
  kpatch_constraint: "kpatch 后端约束，补丁改动触发 fentry、section 或对象差异限制",
  kpatch_symbol_bundle_constraint: "kpatch 符号打包约束，差异符号或重定位布局不满足后端要求",
  module_load_failed: "热补丁模块已生成但加载失败，需检查 vermagic、符号和内核状态",
  patch_apply_failed: "补丁无法应用到当前源码基线，常见原因是上下文偏移或源码版本不匹配",
  source_unavailable: "CVE 缺少可定位的修复提交或源码映射，不能安全生成热补丁",
  target_already_patched: "目标源码已经包含修复，需要切换到未修复源码基线再构建",
  validation_failed: "构建产物未通过 load、unload、smoke 或 selftest 动态验证",
  unknown: "未识别失败类型，需要查看 failure_record 和构建日志做人工归因",
};

export type FailureSignalLike = {
  failure_type?: string | null;
  meaning?: string | null;
  description?: string | null;
  label?: string | null;
};

export function failureSignalMeaning(item: FailureSignalLike): string {
  const fromApi = item.meaning ?? item.description ?? item.label;
  if (fromApi?.trim()) {
    return fromApi.trim();
  }
  const failureType = item.failure_type?.trim();
  if (!failureType) {
    return FAILURE_SIGNAL_MEANINGS.unknown;
  }
  return FAILURE_SIGNAL_MEANINGS[failureType] ?? FAILURE_SIGNAL_MEANINGS.unknown;
}

# missing_fentry

- 适用场景：补丁触及 ftrace / fentry 相关入口或依赖函数进入点。
- 风险说明：目标符号缺少稳定入口时，直接套用普通 livepatch 包装容易失败。
- 推荐原语：`wrapper`
- 禁止动作：直接假定目标函数一定存在可用 `fentry`。

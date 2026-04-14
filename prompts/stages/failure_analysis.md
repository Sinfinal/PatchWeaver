失败归因阶段任务：
1. 阅读构建日志和结构化失败记录，优先判定环境问题还是补丁内容问题。
2. 对 `patch_apply_failed`、`compile_failed`、`kpatch_constraint` 给出不同的下一轮建议。
3. 结论必须能直接指导下一轮收缩范围，而不是只复述错误信息。

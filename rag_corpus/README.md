# PatchWeaver RAG Corpus

该目录存放可直接进入知识库/向量库的 CVE 修复语料。

## 目录说明
- `cards/*.md`: 人工可读的 CVE 修复知识卡。
- `cards/*.metadata.json`: 与知识卡对应的结构化元数据。
- `chunks/all_chunks.jsonl`: 推荐直接送入向量数据库的统一切片文件。
- `chunks/<CVE>.jsonl`: 按单个 CVE 拆分的切片文件。
- `raw/<CVE>/official/*`: NVD、cvelistV5、source evidence、原始补丁等官方语料。
- `raw/<CVE>/workspace/*`: 本地 PatchWeaver 任务命中的工程产物，仅在仓库已有任务时出现。
- `manifest.json`: 当前语料清单。

## 当前语料规模
- CVE 数量: 6
- CVE 列表: CVE-2024-1086, CVE-2022-0185, CVE-2024-26607, CVE-2024-26622, CVE-2024-26643, CVE-2024-26726

## 建议入库文件
- 首选: `chunks/all_chunks.jsonl`
- 如果需要按漏洞分批导入，可使用 `chunks/<CVE>.jsonl`

## 重建命令
```powershell
.\.venv\Scripts\python.exe .\scripts\build_rag_corpus.py
```

## 扩充语料
- 追加指定 CVE: `--cve CVE-2024-1086 --cve CVE-2022-0185`
- 追加新的种子文件: `--fixture-file path\to\seed.json`

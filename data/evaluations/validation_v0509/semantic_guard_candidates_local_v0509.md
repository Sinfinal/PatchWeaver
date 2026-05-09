# semantic_guard_rewrite 候选筛选报告

## 汇总

- generated_at: `2026-05-09T07:08:03.532301+00:00`
- total_records: `210`
- candidate_count: `30`
- validation_mode: `none`
- validation_executed: `False`

## 候选

| CVE | category | confidence | affected_files | validation | reason |
| --- | --- | --- | --- | --- | --- |
| CVE-2024-26726 | `null` | `0.83` | `fs/btrfs/inode.c` | `analyze` | 命中 null guard 语义；semantic_card 含必须保留条件；RAG seed 摘要直接命中 guard 语义；触达函数数量较少；触达文件数量较少；约束诊断当前为低风险 direct apply |
| CVE-2024-26736 | `size_len` | `0.83` | `fs/afs/volume.c` | `analyze` | 命中 size_len guard 语义；semantic_card 含必须保留条件；RAG seed 摘要直接命中 guard 语义；触达函数数量较少；触达文件数量较少；约束诊断当前为低风险 direct apply |
| CVE-2024-26607 | `invalid_state` | `0.8` | `drivers/gpu/drm/bridge/sii902x.c` | `analyze` | 命中 invalid_state guard 语义；semantic_card 含必须保留条件；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少；约束诊断当前为低风险 direct apply |
| CVE-2024-1086 | `size_len` | `0.61` | `net/netfilter/nf_tables_api.c` | `dry-run` | 命中 size_len guard 语义；触达函数数量较少；触达文件数量较少；新增分支含安全退出路径 |
| CVE-2024-26600 | `null` | `0.61` | `drivers/phy` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26608 | `bounds` | `0.61` | `fs/smb` | `dry-run` | 命中 bounds guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26623 | `invalid_state` | `0.61` | `drivers/net` | `dry-run` | 命中 invalid_state guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26631 | `invalid_state` | `0.61` | `net/ipv6` | `dry-run` | 命中 invalid_state guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26648 | `null` | `0.61` | `drivers/gpu` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26649 | `null` | `0.61` | `drivers/gpu` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26657 | `null` | `0.61` | `drivers/gpu` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26660 | `bounds` | `0.61` | `drivers/gpu` | `dry-run` | 命中 bounds guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26662 | `null` | `0.61` | `drivers/gpu` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26664 | `bounds` | `0.61` | `drivers/hwmon` | `dry-run` | 命中 bounds guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26665 | `bounds` | `0.61` | `net/ipv4` | `dry-run` | 命中 bounds guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26671 | `invalid_state` | `0.61` | `block/blk-mq.c` | `dry-run` | 命中 invalid_state guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26672 | `null` | `0.61` | `drivers/gpu` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26688 | `null` | `0.61` | `fs/hugetlbfs` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26692 | `size_len` | `0.61` | `fs/smb` | `dry-run` | 命中 size_len guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26695 | `null` | `0.61` | `drivers/crypto` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26698 | `invalid_state` | `0.61` | `drivers/net` | `dry-run` | 命中 invalid_state guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26699 | `bounds` | `0.61` | `drivers/gpu` | `dry-run` | 命中 bounds guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26700 | `null` | `0.61` | `drivers/gpu` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26715 | `null` | `0.61` | `drivers/usb` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26716 | `null` | `0.61` | `drivers/usb` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26717 | `null` | `0.61` | `drivers/hid` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26728 | `null` | `0.61` | `drivers/gpu` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26729 | `null` | `0.61` | `drivers/gpu` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26731 | `null` | `0.61` | `net/core` | `dry-run` | 命中 null guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |
| CVE-2024-26733 | `overflow` | `0.61` | `net/ipv4` | `dry-run` | 命中 overflow guard 语义；RAG seed 摘要直接命中 guard 语义；RAG seed 摘要包含修复/检查动词；触达文件数量较少 |

## 小规模验证入口


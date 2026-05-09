# Representative Holdout Metrics

## Metrics
- representative_total: 10
- representative_success_rate: 100.00%
- average_attempts: 1.0
- target_success_rate: 60%
- success_gap_to_60_percent: 0.00%

## .ko/load/unload/smoke/selftest Evidence
- ko: present=10 passed=10 total=10
- load: present=10 passed=10 total=10
- unload: present=10 passed=10 total=10
- smoke: present=10 passed=10 total=10
- selftest: present=10 passed=10 total=10

## Failure Buckets
- success: 10

## Model/RAG Participation
- rag_seed_hits: 10
- rag_subsystem_counts: {'drivers/scsi': 1, 'drivers/net': 4, 'net/tipc': 1, 'net/netfilter': 1, 'net/mac80211': 1, 'drivers/gpu': 1, 'fs/btrfs': 1}
- selected_route_counts: {'minimal_livepatch_wrap': 4, 'direct_apply_patch': 6}
- model_counts: {}
- model_missing: 10

## Target Gap
- status: meets_target
- explanation: 代表集 10/10 成功，成功率 100.0%，已达到赛题 60%+ 目标；平均尝试轮次为 1.0。

## Cases
- CVE-2024-26742: success=True attempts=1 bucket=success route=minimal_livepatch_wrap rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26742/attempts/001/output/patchweaver-finalholdout10v0509-26742-001.ko load=passed unload=passed smoke=passed selftest=passed
- CVE-2024-26675: success=True attempts=1 bucket=success route=minimal_livepatch_wrap rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26675/attempts/001/output/patchweaver-finalholdout10v0509-26675-001.ko load=passed unload=passed smoke=passed selftest=passed
- CVE-2024-26663: success=True attempts=1 bucket=success route=minimal_livepatch_wrap rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26663/attempts/001/output/patchweaver-finalholdout10v0509-26663-001.ko load=passed unload=passed smoke=passed selftest=passed
- CVE-2024-26668: success=True attempts=1 bucket=success route=minimal_livepatch_wrap rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26668/attempts/001/output/patchweaver-finalholdout10v0509-26668-001.ko load=passed unload=passed smoke=passed selftest=passed
- CVE-2024-26666: success=True attempts=1 bucket=success route=direct_apply_patch rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26666/attempts/001/output/patchweaver-finalholdout10v0509-26666-001.ko load=passed unload=passed smoke=passed selftest=passed
- CVE-2024-26656: success=True attempts=1 bucket=success route=direct_apply_patch rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26656/attempts/001/output/patchweaver-finalholdout10v0509-26656-001.ko load=passed unload=passed smoke=passed selftest=passed
- CVE-2024-26726: success=True attempts=1 bucket=success route=direct_apply_patch rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26726/attempts/001/output/patchweaver-finalholdout10v0509-26726-001.ko load=passed unload=passed smoke=passed selftest=passed
- CVE-2024-26698: success=True attempts=1 bucket=success route=direct_apply_patch rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26698/attempts/001/output/patchweaver-finalholdout10v0509-26698-001.ko load=passed unload=passed smoke=passed selftest=passed
- CVE-2024-26693: success=True attempts=1 bucket=success route=direct_apply_patch rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26693/attempts/001/output/patchweaver-finalholdout10v0509-26693-001.ko load=passed unload=passed smoke=passed selftest=passed
- CVE-2024-26694: success=True attempts=1 bucket=success route=direct_apply_patch rag=True ko=/home/patchweaver/current/workspaces/finalholdout10v0509-26694/attempts/001/output/patchweaver-finalholdout10v0509-26694-001.ko load=passed unload=passed smoke=passed selftest=passed

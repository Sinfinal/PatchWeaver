# PatchWeaver P2 Submission Summary

Generated at: `2026-05-07T11:28:56.098238+00:00`

## Confirmed Pool

- Total cases: 12
- Complete: 12
- Partial: 0
- Missing: 0

- CVE-2024-26742: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/p0-gate-fg-20260506210801-26742/attempts/001/output/patchweaver-p0-gate-fg-20260506210801-26742-001.ko`
- CVE-2024-26675: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/p1-smoke-20260507160113-26675/attempts/001/output/patchweaver-p1-smoke-20260507160113-26675-001.ko`
- CVE-2024-26663: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/p0-callsite-20260507144934-26663/attempts/001/output/patchweaver-p0-callsite-20260507144934-26663-001.ko`
- CVE-2024-26668: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/p0-callsite-20260507144934-26668/attempts/001/output/patchweaver-p0-callsite-20260507144934-26668-001.ko`
- CVE-2024-26666: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/p0-callsite-20260507144934-26666/attempts/001/output/patchweaver-p0-callsite-20260507144934-26666-001.ko`
- CVE-2024-26656: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/p0-callsite-20260507144934-26656/attempts/001/output/patchweaver-p0-callsite-20260507144934-26656-001.ko`
- CVE-2024-26726: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/s3sgpoolrerun0507-26726/attempts/001/output/patchweaver-s3sgpoolrerun0507-26726-001.ko`
- CVE-2024-26698: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/s1full0507-26698/attempts/001/output/patchweaver-s1full0507-26698-001.ko`
- CVE-2024-26693: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/s1full0507-26693/attempts/001/output/patchweaver-s1full0507-26693-001.ko`
- CVE-2024-26694: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/s1full0507-26694/attempts/001/output/patchweaver-s1full0507-26694-001.ko`
- CVE-2024-26615: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/s1full0507-26615/attempts/001/output/patchweaver-s1full0507-26615-001.ko`
- CVE-2024-26791: status=`complete`, validation=`passed`, module=`/home/patchweaver/current/workspaces/s1full0507-26791/attempts/001/output/patchweaver-s1full0507-26791-001.ko`

## Representative Metrics

- Positive evidence completion rate: 100.00%
- KO artifact count: 12
- Workspace report count: 104
- Standalone report count: 1

## P2 Holdout

- Status: `passed`
- Mode: `dry-run`
- Dry run: `True`
- Total cases: 1
- Blind identities preserved: `True`

## Bailian Entrypoint

- Entrypoint placeholder: `PATCHWEAVER_BAILIAN_APP_LINK_PENDING`
- Status: `placeholder`
- Secret policy: Environment variable names only; secret values are not read or written.
- Required env: `PATCHWEAVER_BAILIAN_API_KEY`, secret
- Required env: `PATCHWEAVER_API_BASE_URL`
- Required env: `PATCHWEAVER_API_TIMEOUT_SECONDS`

## Limits

- Generated from local manifests and dry-run reports only.
- Does not contact the validation machine.
- Does not read, print, or write secret values.

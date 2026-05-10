# PatchWeaver Web/API E2E Validation

- Base URL: `http://10.223.185.3:18084`
- Task ID: `judge-like-v0510-20260509191933-26698`
- Endpoint OK: `6/6`
- Module path: `workspaces/judge-like-v0510-20260509191933-26698/attempts/001/output/patchweaver-judge-like-v0510-20260509191933-26698-001.ko`
- Validation status: `passed`
- Report OK: `True`
- Replay OK: `True`
- Agent decision OK: `True`
- Validation success evidence: `True`

## Endpoints

| Name | Method | OK | Status |
| --- | --- | --- | --- |
| `healthz` | `GET` | `True` | `200` |
| `task_detail` | `GET` | `True` | `200` |
| `agent_decision` | `GET` | `True` | `200` |
| `task_report` | `GET` | `True` | `200` |
| `replay` | `GET` | `True` | `200` |
| `artifacts` | `GET` | `True` | `200` |

## Limits

- This check validates API evidence for an existing task; it does not rerun kpatch-build.
- Validation success still requires the referenced .ko and validation artifacts to be present on the validation machine.

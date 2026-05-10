# PatchWeaver Bailian / FC / MCP E2E Validation

- Mode: `execute`
- API base URL: `http://10.223.185.3:18084/api/v1`
- Task ID: `judge-like-v0510-20260509191933-26698`
- CVE ID: `not set`
- Actions: `status, agent_decision, report, replay`

## Summary

- Total: 4
- OK: 4
- Failed: 0
- Real HTTP invoked: `True`
- Secrets written: `False`

## Cases

| Action | Mode | OK | HTTP Status / Error |
| --- | --- | --- | --- |
| `status` | `execute` | `True` | `200` |
| `agent_decision` | `execute` | `True` | `200` |
| `report` | `execute` | `True` | `200` |
| `replay` | `execute` | `True` | `200` |

## Limits

- dry_run mode validates the FC/MCP tool contract but does not prove livepatch build success.
- execute mode validates real gateway-to-API calls; .ko success still requires task artifact checks.
- Secret values are never written to this report.

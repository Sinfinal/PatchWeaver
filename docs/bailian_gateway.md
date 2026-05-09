# Bailian Gateway Minimal Slice

This slice provides a small PatchWeaver gateway for Bailian Function Compute or MCP tool wiring.

## Environment

- `PATCHWEAVER_BAILIAN_API_KEY`: optional bearer token for outbound PatchWeaver API calls. Do not place the value in code, docs, logs, or test fixtures.
- `PATCHWEAVER_API_BASE_URL`: PatchWeaver API base URL. Defaults to `http://127.0.0.1:8000`.
- `PATCHWEAVER_API_TIMEOUT_SECONDS`: optional HTTP timeout. Defaults to `30`.

## CLI

Print the FC/MCP schema:

```bash
python scripts/run_bailian_gateway.py --schema
```

Print the OpenAPI document for Bailian plugin registration:

```bash
python scripts/run_bailian_gateway.py --openapi --server-url https://<reachable-gateway-host>
```

Dry-run a create request:

```bash
python scripts/run_bailian_gateway.py --action create --payload-json "{\"cve_id\":\"CVE-2024-26742\",\"profile\":\"demo\"}"
```

Call a real PatchWeaver API after configuring environment variables:

```bash
python scripts/run_bailian_gateway.py --action status --payload-json "{\"task_id\":\"pw-123\"}" --invoke
```

## Function Compute Package

Build a small deployable package:

```bash
python scripts/package_bailian_gateway.py \
  --output-zip data/submission/bailian_gateway_fc_package_v0509.zip \
  --manifest-output data/submission/bailian_gateway_fc_package_v0509.json
```

Upload the generated zip to Function Compute with:

- Entrypoint: `index.handler`
- Runtime: Python 3
- Required environment: `PATCHWEAVER_API_BASE_URL`
- Optional secret: `PATCHWEAVER_BAILIAN_API_KEY`

The first platform-side smoke test should use `dry_run: true`.

## FC/MCP Contract

Use `patchweaver.integrations.bailian_gateway.fc_handler(event, context)` as the Function Compute entrypoint.

Input:

```json
{
  "action": "run",
  "payload": {
    "task_id": "pw-123"
  },
  "dry_run": true
}
```

Supported actions are `create`, `status`, `analyze`, `run`, `report`, `replay`, and `agent_decision`. The default is dry-run mode, which returns the target method, URL, redacted headers, and JSON payload without sending a request.

## Bailian Console Steps

1. Create a Function Compute function using the repository package or deployment artifact.
2. Set `PATCHWEAVER_API_BASE_URL` in the function environment.
3. Add `PATCHWEAVER_BAILIAN_API_KEY` as a secret or protected environment variable if the PatchWeaver API requires authentication.
4. Configure the Bailian/MCP tool schema from `python scripts/run_bailian_gateway.py --schema`.
5. If using `插件 / 使用外部OpenAPI注册`, publish or host `python scripts/run_bailian_gateway.py --openapi --server-url ...` at a URL reachable by Bailian.
6. Keep initial console validation in `dry_run: true`, then switch selected calls to `dry_run: false` after network access to PatchWeaver is confirmed.

## PatchWeaver API Hosted Plugin Route

When the PatchWeaver Web/API service is reachable by Bailian, it can serve the plugin schema directly:

```text
GET /api/v1/integrations/bailian/openapi.json?server_url=https://<reachable-host>/api/v1/integrations/bailian
```

The generated OpenAPI document exposes:

```text
POST /api/v1/integrations/bailian/gateway
```

This endpoint defaults to `dry_run=true`. It is intended for Bailian plugin registration and first smoke tests; real task execution should be enabled only after network reachability and authentication are confirmed.

## Current Platform Status

On `2026-05-07`, the code-level gateway, FC package builder, schema generation, PatchWeaver hosted plugin route, and dry-run tests were completed.

Platform-side progress on the same day:

- Bailian application created and published: `PatchWeaver 热补丁生成Agent`
- Bailian app id: `fd3f32a0f7c64c028994ada2ddcfdb10`
- Model: `Qwen-Plus-Latest`
- Status observed in the console: `新版 / 已发布`
- MCP service created: `patchweaver-bailian-gateway`
- MCP service id: `mcp-ODEwY2JkM2Q0MTU2`
- Tool name: `patchweaver_gateway`
- Tool path: `POST /api/v1/integrations/bailian/gateway`
- Bailian app-side tool smoke test: passed with `dry_run=true`

The smoke test asked the Bailian app to call `patchweaver_gateway` with `action=status`, `task_id=flat-demo`, and `dry_run=true`. Bailian invoked the configured MCP tool successfully, and the returned response correctly stated that this was only a platform/tool integration dry run, not a real `kpatch-build`, `.ko` generation, or dynamic validation success.

Latest local focused verification after the platform status update:

```bash
python -m pytest tests/api/test_bailian_integration_router.py tests/integrations/test_bailian_gateway.py tests/integrations/test_bailian_fc_package.py tests/api/test_task_query_service.py tests/reporter/test_positive_pool_manifest.py tests/reporter/test_stable_baseline_evidence.py tests/reporter/test_submission_package.py tests/scripts/test_holdout_and_demo_scripts.py tests/scripts/test_plan_p1_expansion_batch.py tests/scripts/test_screen_semantic_guard_candidates.py tests/validator/test_light_semantic_equivalence.py tests/rag/test_context_injector.py tests/reporter/test_report_builder.py tests/rewriter/test_executor.py tests/scripts/test_screen_challenge_pool.py -q
```

Result: `96 passed, 2 warnings in 8.77s`.

Additional `2026-05-09` verification:

- The FC handler now accepts mapping events, JSON string events, and bytes events. This matches common Function Compute invocation shapes and avoids tying the gateway to a single local test payload format.
- The regenerated FC package is:
  - `data/submission/bailian_gateway_fc_package_v0509.zip`
  - `data/submission/bailian_gateway_fc_package_v0509.json`
- Focused local verification:

```bash
python -m pytest tests/api/test_bailian_integration_router.py tests/integrations/test_bailian_gateway.py tests/integrations/test_bailian_fc_package.py tests/scripts/test_holdout_and_demo_scripts.py tests/reporter/test_positive_pool_manifest.py -q
```

Result: `26 passed, 2 warnings in 3.53s`.

- Focused validation-machine verification on `10.223.185.3` after code sync:

```bash
.venv/bin/python -m pytest tests/api/test_bailian_integration_router.py tests/integrations/test_bailian_gateway.py tests/integrations/test_bailian_fc_package.py tests/scripts/test_holdout_and_demo_scripts.py tests/reporter/test_positive_pool_manifest.py -q
```

Result: `26 passed in 1.39s`.

Current delivery boundary:

- The current public gateway used for the smoke test is a temporary localtunnel URL. It proves the Bailian tool binding and request shape, but it is not a durable judge-facing endpoint.
- The published channel currently visible in the console is API/SDK based. A direct public Web/share link was not observed on the `发布渠道` page.
- Final delivery should replace the temporary tunnel with Function Compute, a stable HTTPS domain, or another durable public endpoint reachable by Bailian and judges.
- Real task execution must remain disabled or guarded until the durable endpoint, authentication, timeout policy, and PatchWeaver API reachability are confirmed.

Do not place API keys, server passwords, platform tokens, or private cookies in this document.

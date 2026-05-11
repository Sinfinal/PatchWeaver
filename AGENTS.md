# PatchWeaver Agent Guide

This project is the OS competition PatchWeaver codebase. Work should optimize for competition scoring, reliable verification, and delivery completeness.

## Proactive Skill Use

Use installed Codex skills proactively. Do not wait for the user to name a skill when the task clearly matches one.

- Use `grill-me` when goals, scoring targets, task boundaries, assumptions, or acceptance criteria are unclear.
- Use `grill-with-docs` when refining requirements, PRDs, design docs, or competition deliverables against local docs or contest requirements.
- Use `to-prd` when turning competition requirements, design notes, research notes, or meeting context into a product requirements document.
- Use `to-issues` when splitting a PRD, design doc, or milestone into actionable tasks.
- Use `tdd` when implementing or changing code that should be protected by tests.
- Use `diagnose` when debugging failed tests, build errors, kernel/livepatch failures, validation failures, or unexpected reports.
- Use `zoom-out` when checking project direction, priority, scoring risk, milestone risk, or whether the plan still matches the contest.
- Use `improve-codebase-architecture` when changes affect module boundaries, shared contracts, maintainability, or long-term extensibility.
- Use `prototype` when an uncertain approach needs a quick experiment before committing it to the main implementation.
- Use `triage` when multiple failures, candidate CVEs, issues, or work items need prioritization.

## Default Workflow

1. If the request is ambiguous, clarify just enough with `grill-me`.
2. For major OS competition planning or P0/P1 work, use `zoom-out` to check scoring impact and delivery risk.
3. For implementation, prefer `tdd`: add or update focused tests, implement, then run the relevant tests.
4. For failures, use `diagnose`: preserve evidence, isolate the failing layer, and avoid speculative fixes.
5. When project scope, scoring assumptions, or delivery plans change, update PRD/issues using `to-prd` or `to-issues`.

## Competition Priorities

- Keep the positive confirmed pool, stable source alignment, livepatch build success, report quality, and Bailian/FC/MCP delivery requirements visible in planning.
- Prefer changes that increase measurable success rate or unblock confirmed CVE expansion.
- Do not spend time on broad refactors unless they reduce immediate scoring or delivery risk.
- Treat tests, build logs, validation reports, and structured JSON outputs as first-class evidence.

## External Delivery Documentation Policy

- `README.md` is an external delivery page, not an internal development log.
- Keep README focused on three things: what PatchWeaver is, how external users can use it, and what verified effects/evidence it currently has.
- Do not add internal construction records, long risk diaries, work-progress sections, temporary environment notes, raw secrets, or broad design-history content to README.
- Put detailed design, research, phase reports, glossary, troubleshooting, and engineering retrospectives under `docs/` or `D:/spaces/python/b312_docs` instead.
- Put README and delivery-document images under `docs/images/`. Do not create a root-level `Images/` or scatter image files in the repository root. `submission/docs/images/` is a generated offline copy only.
- Treat `docs/` as the maintained documentation source. `submission/docs/` is generated from `docs/` and README during final packaging; do not hand-edit duplicate submission docs unless regenerating the package is impossible.
- If README behavior changes, update the README delivery tests so they protect the external delivery scope.
- Project documents should avoid committee-specific wording that makes the text look prompt-driven. Use neutral terms such as `验收人员`, `使用者`, `外部验收`, `提交验收`, or `测评环境` instead.
- Historical task IDs or artifact paths may keep their original values if renaming them would break evidence traceability, but new documents, examples, and task prefixes should not introduce committee-specific wording.

## Web Copywriting Policy

- Do not use the Chinese full stop character U+3002 in Web-visible copy. Keep UI labels, hints, empty states, notes, and banners concise, and omit terminal punctuation when possible.
- This rule applies to source files under `web/src` and any maintained Web copy source. Runtime JSON evidence can preserve original punctuation because it reflects task artifacts rather than UI copy.

## Secrets And Platform Access

- Never commit or document plaintext API keys, root passwords, platform tokens, or private cookies.
- Bailian / DashScope credentials must be injected through `PATCHWEAVER_BAILIAN_API_KEY`; keep local values in an ignored `.env` or shell environment only.
- `config/models.yaml` may name the environment variable, but its `api_key` fallback should stay empty in the repository.
- When Bailian console or other logged-in web operations are required, use `chrome-devtools-real` so the normal browser session can be inspected without copying credentials into code or docs.

## Working Style

- Read the relevant code and docs before editing.
- Preserve user or prior-agent changes; do not revert unrelated work.
- Keep patches scoped to the current task.
- End implementation tasks with a concise summary of changed files and the verification performed.

## Temporary Files Policy

- Put all temporary code, one-off Python scripts, shell snippets, scratch test inputs, and disposable validation artifacts under `D:\spaces\ai\PatchWeaver\tmp`.
- Keep internal/local test suites under `D:\spaces\ai\PatchWeaver\tmp\tests` unless the user explicitly asks to promote them into the submitted repository.
- Do not create ad-hoc temporary scripts in the repository root, `scripts/`, `tests/`, `docs/`, or `patchweaver/` unless they are intended to become maintained project files.
- If a temporary script becomes reusable or part of delivery, promote it deliberately into the proper project directory and add tests/docs as needed.
- Keep `tmp/` out of committed deliverables except for `tmp/README.md` and `tmp/.gitkeep`.

## Validation Machine Docker Channels

- Treat the validation machine `patchweaver:test` and `patchweaver-web:test` images as the manual acceptance channel.
- Do not sync new development code into the test channel or replace running test containers unless the user explicitly asks for it.
- Use `/home/patchweaver/dev`, `patchweaver:dev`, and `patchweaver-web:dev` for development verification after local changes.
- The running development containers are `patchweaver-dev-api` on host port `18086` and `patchweaver-dev-web` on host port `18087`.
- The running manual acceptance containers are `patchweaver-api` and `patchweaver-web` on host ports `18084` and `18085`.
- Development verification may build, run, or remove temporary dev containers, but it must not restart or retag the test containers.

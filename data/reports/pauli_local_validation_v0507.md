# Pauli Local Focused Test Validation - 2026-05-07

## Scope

Focused local validation for the Bailian gateway, Bailian Function Compute package, and submission package tests.

No API keys, root passwords, or platform secrets were read, written, or printed.

## Timeout Diagnosis

Plain pytest runs such as:

```bash
python -m pytest tests/integrations/test_bailian_gateway.py -q
```

can hang before producing pytest output on this Windows environment.

`faulthandler.dump_traceback_later()` showed the hang occurs during pytest startup, before test collection, in the built-in pytest debugging plugin:

```text
_pytest.debugging.py -> pdb -> rlcompleter -> readline -> pyreadline3 -> platform.system() -> platform._wmi_query
```

This matches the observed process-table symptoms: Windows WMI/process enumeration commands also timed out without output. The focused PatchWeaver test modules import quickly, so the hang is not caused by the Bailian/OpenAPI implementation or test module import side effects.

## Reliable Local Test Command

Use pytest with the built-in debugging plugin disabled:

```bash
python -m pytest -p no:debugging tests/integrations/test_bailian_gateway.py -q
python -m pytest -p no:debugging tests/integrations/test_bailian_fc_package.py -q
python -m pytest -p no:debugging tests/reporter/test_submission_package.py -q
python -m pytest -p no:debugging tests/integrations/test_bailian_gateway.py tests/integrations/test_bailian_fc_package.py tests/reporter/test_submission_package.py -q
```

For parallel agent runs on this Windows environment, use a unique `--basetemp` per worker. Reusing a fixed temp directory can leave SQLite files locked by another process, while the default Windows temp root may have local permission issues:

```bash
python -m pytest tests/api/test_bailian_integration_router.py tests/integrations/test_bailian_gateway.py tests/integrations/test_bailian_fc_package.py -q --basetemp data/cache/pytest-tmp-s4-main
```

## Results

```text
tests/integrations/test_bailian_gateway.py
10 passed in 0.78s

tests/integrations/test_bailian_fc_package.py
2 passed in 0.39s

tests/reporter/test_submission_package.py
2 passed in 0.26s

combined focused run
14 passed in 1.37s
```

After the Bailian OpenAPI/API route slice was added, the S4 focused run was:

```text
tests/api/test_bailian_integration_router.py
tests/integrations/test_bailian_gateway.py
tests/integrations/test_bailian_fc_package.py

14 passed, 2 warnings in 2.40s
```

## Process Handling

No Python, pytest, or Node process was killed manually. Short timeout probes were used to avoid long-running blocked commands. Windows process-table commands timed out, so any residual process cleanup should be handled manually only after confirming ownership and command line.

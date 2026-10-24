---
name: write-tests
description: Write and run tests (pytest, unittest, vitest/jest). Use when asked to add tests or improve coverage.
triggers: test, tests, pytest, coverage, unittest
---
# Writing tests
1. Detect the framework: look for pytest.ini/pyproject (pytest), package.json scripts (vitest/jest). If none, use `pytest` for Python and Node's built-in `node --test` for JS.
2. Test behavior, not implementation: one clear assertion focus per test, descriptive names (`test_login_rejects_wrong_password`).
3. Cover: happy path, edge cases, error cases. Use small fixtures; avoid network and real files (use tmp_path / mocks).
4. Run the tests with bash and fix failures. If a test fails, decide whether the test or the code is wrong before editing.

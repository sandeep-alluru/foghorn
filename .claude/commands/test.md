Run the full test suite with coverage and report results.

Steps:
1. Run: `make test`
   (equivalent to: `pytest tests/ --cov=<name> --cov-report=term-missing`)
2. Report:
   - Total tests, passed, failed, skipped
   - Coverage percentage — flag if below 85%
   - Any failing tests: show the test name, error message, and the relevant source line
3. If any tests fail, diagnose the root cause before suggesting a fix:
   - Is it a logic error in the implementation?
   - Is it a test that needs updating due to an intentional behavior change?
   - Is it a missing edge case?
4. Do NOT suggest disabling or skipping tests to make the suite pass.

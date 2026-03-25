# Sefer Hardening Validation

Generated: 2026-03-25T07:29:28.519623+00:00
Scenarios: 10
Runs: 30
Pass/Fail: 30/0
Deterministic across repeated runs: True
Default calculator id: `green_legacy`
green_legacy still works: True

## Issues Found
- No blocking integrity or determinism issues were detected.

## Issues Fixed
- Hardening validator alignment check was tightened to avoid false failures when a computable definition item is blocked only by missing optional inputs.
- No runtime/definition changes were required by this validation pass.

## Issues Open
- 162 calculations remain blocked by unsupported_executor_type in baseline scenario.

## Scenario Determinism
- `s01_standard_hebrew`: deterministic=True
- `s02_known_name`: deterministic=True
- `s03_male_name`: deterministic=True
- `s04_multi_component`: deterministic=True
- `s05_short_name`: deterministic=True
- `s06_single_letter_no_optional`: deterministic=True
- `s07_long_name`: deterministic=True
- `s08_repeating_digits_date`: deterministic=True
- `s09_two_parts`: deterministic=True
- `s10_old_date`: deterministic=True
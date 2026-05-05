# Sefer Executor Expansion Pass

Generated: 2026-03-25T07:04:52.503789+00:00

## Before / After
- Computable before: 69
- Computable after: 87
- unsupported_executor_type before: 191
- unsupported_executor_type after: 162

## Implemented Executor Types
- `birth_date_life_path_composites`: 11 unlocked
- `name_component_sum`: 5 unlocked
- `name_letter_position`: 2 unlocked

## Ranked Unsupported Executor Types (Before)
- `misc_formula_executor`: blocked=114, risk=high, uses_current_inputs=False, deterministic=False
- `external_identifier_digit_reduction`: blocked=16, risk=medium, uses_current_inputs=False, deterministic=True
- `birth_date_life_path_composites`: blocked=14, risk=low, uses_current_inputs=True, deterministic=True
- `numeric_rule_engine`: blocked=13, risk=medium, uses_current_inputs=True, deterministic=True
- `period_arithmetic_sequences`: blocked=12, risk=medium, uses_current_inputs=False, deterministic=True
- `name_component_sum`: blocked=7, risk=low, uses_current_inputs=True, deterministic=True
- `hebrew_calendar_conversion`: blocked=6, risk=high, uses_current_inputs=False, deterministic=False
- `matrix_structure_tables`: blocked=5, risk=high, uses_current_inputs=False, deterministic=False
- `pair_compatibility`: blocked=2, risk=high, uses_current_inputs=False, deterministic=False
- `name_letter_position`: blocked=2, risk=low, uses_current_inputs=True, deterministic=True

## Blocked After By Reason
- `unsupported_executor_type`: 162
- `interpretation_only`: 13
- `missing_input_mapping`: 11
- `missing_formula`: 9
- `missing_result_value_table`: 1
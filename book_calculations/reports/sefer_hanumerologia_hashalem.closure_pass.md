# Sefer Book Closure Pass

Generated: 2026-03-25T16:45:37.763006+00:00
Definition version: 1.0.0 -> 1.1.0
- Total entries: 283
- computable_with_trace: 92
- computable_partial: 0
- interpretation_only: 13
- blocked_with_reason: 178
- Computed with interpretation (sample runtime): 46
- Computed without interpretation (sample runtime): 46
- Newly promoted calculations: 5
- Interpretation tables added: 43

## Newly Promoted Calculations
- `civil_life_lesson`
- `life_lesson_number_civil`
- `outer_expression_calculation`
- `personality_number`
- `soul_expression_calculation`

## Blocked Counts By Reason
- `unsupported_executor_type`: 157
- `missing_input_mapping`: 11
- `missing_formula`: 9
- `missing_result_value_table`: 1

## Core Calculations Coverage
- `destiny_path` | final_state=`computable_with_trace` | runtime=`computed` | trace=True
- `destiny_number` | final_state=`computable_with_trace` | runtime=`computed` | trace=True
- `expression_of_the_soul` | final_state=`computable_with_trace` | runtime=`computed` | trace=True
- `soul_expression_number` | final_state=`computable_with_trace` | runtime=`computed` | trace=True
- `behavior_number` | final_state=`computable_with_trace` | runtime=`computed` | trace=True
- `personality_number` | final_state=`computable_with_trace` | runtime=`computed` | trace=True
- `birth_number` | final_state=`computable_with_trace` | runtime=`computed` | trace=True
- `life_path_number` | final_state=`computable_with_trace` | runtime=`computed` | trace=True
- `civil_life_lesson` | final_state=`computable_with_trace` | runtime=`computed` | trace=True
- `life_lesson_number_civil` | final_state=`computable_with_trace` | runtime=`computed` | trace=True

## Top Remaining Unresolved
- `44_or_8_destiny_number` | reason=`unsupported_executor_type` | deps=['תאריך לידה', 'שם מלא']
- `calculate_life_cycle_position` | reason=`unsupported_executor_type` | deps=['תאריך לידה', 'גיל נוכחי']
- `destiny_number_calculation` | reason=`unsupported_executor_type` | deps=['תאריך לידה עברי', 'תאריך לידה אזרחי']
- `harmony_between_soul_and_psyche` | reason=`unsupported_executor_type` | deps=['מפת לידה מקורית', 'מפת לידה חדשה']
- `hebrew_life_lesson` | reason=`missing_input_mapping` | deps=['תאריך לידה עברי']
- `life_lesson_number` | reason=`unsupported_executor_type` | deps=['לא מפורט בטקסט']
- `life_lesson_number_hebrew` | reason=`missing_input_mapping` | deps=[]
- `life_lesson_number_shared` | reason=`unsupported_executor_type` | deps=[]
- `life_lessons_calculation` | reason=`unsupported_executor_type` | deps=['שם מלא', 'תאריך לידה']
- `manifestation_ten_divine_soul_frequencies` | reason=`unsupported_executor_type` | deps=['תדרי נפש אלוהית', 'צבעים']
- `numerological_charts_geometry_life` | reason=`unsupported_executor_type` | deps=['נתוני לידה', 'שם']
- `personality_insight_name_family` | reason=`unsupported_executor_type` | deps=['שם פרטי', 'שם משפחה']
- `purpose_and_goals_of_the_new_soul` | reason=`unsupported_executor_type` | deps=['מפת לידה חדשה']
- `shiyur_haim_ivri` | reason=`missing_input_mapping` | deps=['תאריך לידה עברי']
- `shiyur_haim_meshutaf` | reason=`unsupported_executor_type` | deps=['שיעור חיים עברי', 'שיעור חיים אזרחי']

## Template Readiness
- ready_as_template_for_future_ocr: `False`
- green_legacy_still_works: `True`
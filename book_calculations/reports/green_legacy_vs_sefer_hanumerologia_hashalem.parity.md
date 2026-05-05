# Green Legacy vs Sefer Definition Parity Report

Generated: 2026-03-25T06:30:52.344933+00:00
Legacy calculator: `green_legacy`
Definition calculator: `sefer_hanumerologia_hashalem`

## Summary
- Overlapping calculations compared: 9
- Matching results count: 9
- Mismatching results count: 0
- Computable only in legacy (sample-level): 0
- Computable only in definition (sample-level): 0
- Definition still needs_review: 225
- Definition unsupported: 9
- Missing interpretation text (sample-level): 30
- Missing input dependency support (sample-level): 0
- Could not map reliably: 5

## Comparable Calculations
### soul_expression_number
- Legacy field: `soul_expression`
- Equivalence: `same_concept_different_method`
- Aggregate comparison: `same`
- Definition status: `computable`
- Notes: Both represent soul-expression from name vowels, but implementation details may differ.
- Sample counts: matched=5, mismatched=0, missing=0

### expression_of_the_soul
- Legacy field: `soul_expression`
- Equivalence: `same_concept_different_method`
- Aggregate comparison: `same`
- Definition status: `computable`
- Notes: Catalog alias of soul-expression concept; validate parity against legacy vowels output.
- Sample counts: matched=5, mismatched=0, missing=0

### outer_behavior
- Legacy field: `personality`
- Equivalence: `same_concept_different_method`
- Aggregate comparison: `same`
- Definition status: `computable`
- Notes: Both target external behavior/personality by name consonants.
- Sample counts: matched=5, mismatched=0, missing=0

### source_chapter_1
- Legacy field: `name_value`
- Equivalence: `same_concept_same_method`
- Aggregate comparison: `same`
- Definition status: `computable`
- Notes: Both represent full-name numeric sum.
- Sample counts: matched=5, mismatched=0, missing=0

### source_chapter_18
- Legacy field: `name_value`
- Equivalence: `same_concept_same_method`
- Aggregate comparison: `same`
- Definition status: `computable`
- Notes: Same formula text family as full-name sum.
- Sample counts: matched=5, mismatched=0, missing=0

### source_chapter_26
- Legacy field: `name_value`
- Equivalence: `same_concept_same_method`
- Aggregate comparison: `same`
- Definition status: `computable`
- Notes: Same formula text family as full-name sum.
- Sample counts: matched=5, mismatched=0, missing=0

### source_chapter_30
- Legacy field: `name_value`
- Equivalence: `same_concept_same_method`
- Aggregate comparison: `same`
- Definition status: `computable`
- Notes: Same formula text family as full-name sum.
- Sample counts: matched=5, mismatched=0, missing=0

### source_chapter_31
- Legacy field: `name_value`
- Equivalence: `same_concept_same_method`
- Aggregate comparison: `same`
- Definition status: `computable`
- Notes: Same formula text family as full-name sum.
- Sample counts: matched=5, mismatched=0, missing=0

### source_chapter_33
- Legacy field: `name_value`
- Equivalence: `same_concept_same_method`
- Aggregate comparison: `same`
- Definition status: `computable`
- Notes: Same formula text family as full-name sum.
- Sample counts: matched=5, mismatched=0, missing=0

## Non-Equivalent Mappings
- `destiny` -> `destiny_path`: Book definition computes destiny_path from soul+behavior; legacy destiny is a different core calculation.
- `personality` -> `personality_number`: Book catalog marks personality_number as birth-date based in current extracted schema, not legacy consonant personality.
- `personal_year` -> `yearly_life_path_number`: No stable formula-equivalent mapping validated yet.
- `hidden_year` -> `(none)`: No reliable definition-side key currently mapped.
- `birth_day` -> `birth_number`: birth_number in definition is full birth-date reduction, not reduced day component.
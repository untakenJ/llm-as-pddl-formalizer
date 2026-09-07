# p43 minimal-rewrite audit

## Decision

`REWRITE REQUIRED`

## Finding / 结论

The original description covered the inventories, placements, and complete goal, but it did not directly state that apt1–apt8 satisfy the independent location type and used “scattered across” instead of a unique airport-to-city mapping. Two local phrase replacements repair those defects.

原始描述覆盖了清单、位置和完整目标，但没有直接说明 apt1–apt8 满足独立的地点类型事实，并以“散布在”代替唯一的机场到城市映射。两处局部短语替换修复了这些问题。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics.
- `golden_problem.pddl`: 58 objects, 116 init atoms, and 23 goal atoms.
- `natural_original.txt`: original English description audited before the decision.
- Semantic-item total: 197.

## Before-rewrite coverage

| Measure | Count |
|---|---:|
| Objects covered | 58/58 |
| Init atoms covered | 100/116 |
| Goal atoms covered | 23/23 |
| Missing | 0 |
| Ambiguous | 16 |
| Contradictory | 0 |
| Over-generated | 0 |

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | an airport (apt1 through apt8) | an airport location (apt1 through apt8) | Adding “location” directly supports the independent LOCATION facts for apt1–apt8 while preserving their airport type. / 添加“地点”一词，可直接支持 apt1–apt8 各自独立的 LOCATION 事实，同时保留其机场类型。 | `golden_problem.pddl:105,107,109,111,113,115,117,119 ((LOCATION APT1) through (LOCATION APT8))`<br>`golden_problem.pddl:120-127 ((AIRPORT APT1) through (AIRPORT APT8))` |
| 2 | Airports apt1 through apt8 are scattered across cities cit1 to cit8. | Airports apt1 through apt8 are in cities cit1 through cit8, respectively. | “Scattered across” did not uniquely map each airport to a city. Ordered ranges plus “respectively” uniquely map aptN to citN. / “散布在”无法唯一确定每个机场所属的城市；有序范围加“分别”可唯一确定 aptN 到 citN 的映射。 | `golden_problem.pddl:165,167,169,171,173,175,177,179 ((IN-CITY APT1 CIT1) through (IN-CITY APT8 CIT8))` |

## Material deliberately preserved

- The complete package inventory, vehicle inventory, airplane placements, truck/package placements, position-to-city rule, and 23-pair goal enumeration.
- The original sentence structure and wording outside the two defective spans.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 58/58 |
| Init atoms covered | 116/116 |
| Goal atoms covered | 23/23 |
| Ledger rows | 197/197 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Final assertion: every golden object, init atom, and goal atom has unique direct or deterministic-rule evidence in `natural_rewritten.txt`; deterministic rules expand to exactly the golden items, with zero omissions, ambiguity, contradictions, or over-generation.

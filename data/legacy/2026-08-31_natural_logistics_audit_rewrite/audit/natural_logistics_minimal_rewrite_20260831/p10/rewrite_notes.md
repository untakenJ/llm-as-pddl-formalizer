# p10 audit and rewrite notes

Decision: `REWRITE REQUIRED`

The original uniquely identifies all objects and all golden relations except `(airport apt3)`: apt3 is named as a location and goal destination but never identified as an airport. One inserted finite rule supplies that missing type fact while also making the already implied airport set explicit.
原文唯一确定了所有对象和其他黄金关系，但没有唯一确定 `(airport apt3)`：apt3 被称为地点和目标目的地，却从未被说明为机场。插入一条有限规则即可补充该缺失类型事实，同时明确原文已经暗示的机场集合。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics; 85 lines.
- `golden_problem.pddl`: 29 objects, 58 init atoms, and 10 goal atoms; 97 semantic items total.
- `natural_original.txt`: original one-line English description.

## Before-rewrite coverage and defects

- Objects covered: 29/29.
- Init atoms covered: 57/58.
- Goal atoms covered: 10/10.
- Missing: 1 (`(airport apt3)`).
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | *(no text; insertion after the city/location mapping)* | `The locations apt1 through apt4 are airports.` | Supplies the missing airport type by a bounded four-item rule without changing existing prose. / 通过有界的四项规则补充缺失的机场类型，不改动现有文字。 | `golden_problem.pddl:9-10`: `(airport apt1)`, `(airport apt2)`, `(airport apt3)`, `(airport apt4)`; `golden_problem.pddl:8-9`: matching location atoms. |

## Material deliberately preserved

- The object enumerations, vehicle and city descriptions, and all initial-location statements were preserved verbatim.
- The entire irregular goal mapping was preserved verbatim because every package–destination pair already matches the golden goal.

## Post-rewrite verification

- Objects covered: 29/29.
- Init atoms covered: 58/58.
- Goal atoms covered: 10/10.
- Evidence ledger: 97/97 semantic items.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has direct or uniquely expandable deterministic evidence, and the final description introduces no extra object, atom, or goal.
每个黄金项都有直接证据或可唯一展开的确定性证据，最终描述没有引入额外对象、原子或目标。


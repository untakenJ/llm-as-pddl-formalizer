# p37 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original is complete except that “a location and an airport” does not state that each airport also has the golden `LOCATION` type. Replacing that phrase with “two locations, a position and an airport” is the smallest sufficient repair.

原文除一处外均完整：“一个地点和一个机场”没有说明每个机场同时具有黄金 PDDL 中的 `LOCATION` 类型。将其改为“两个地点，即一个位置和一个机场”是最小且充分的修复。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics.
- `golden_problem.pddl`: 51 objects (lines 3–55), 102 init atoms (lines 56–159), and 20 goal atoms (lines 160–181).
- `natural_original.txt`: original one-paragraph English description.
- Semantic total: **173** items.

## Before-rewrite coverage and defects

- Objects: **51/51** covered.
- Init: **95/102** covered; the seven `(LOCATION APT1)` through `(LOCATION APT7)` atoms were ambiguous.
- Goal: **20/20** covered.
- Missing: **0**; ambiguous: **7**; contradictory: **0**; over-generated: **0**.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `each containing a location and an airport` | `each containing two locations, a position and an airport` | Makes the airport members explicitly locations while preserving the sentence and all enumerated pairings. / 明确机场成员也属于地点，同时保留原句及全部列举关系。 | `golden_problem.pddl:92–105: (LOCATION POS1)…(LOCATION APT7)` and `golden_problem.pddl:106–112: (AIRPORT APT1)…(AIRPORT APT7)` |

## Material deliberately preserved

- The package, truck, city, airplane, initial-location, and goal enumerations were preserved verbatim because they already map directly and uniquely to the golden atoms.
- The original one-paragraph organization and logistics-game tone were preserved.

## Post-rewrite verification

- Objects: **51/51**; init: **102/102**; goal: **20/20**.
- Atomic evidence ledger: **173/173** rows covered, with one row per semantic item.
- Missing: **0**; ambiguous: **0**; contradictory: **0**; over-generated: **0**.

Final assertion: the repaired description uniquely supports every golden object, init atom, and goal atom and introduces no extra item.

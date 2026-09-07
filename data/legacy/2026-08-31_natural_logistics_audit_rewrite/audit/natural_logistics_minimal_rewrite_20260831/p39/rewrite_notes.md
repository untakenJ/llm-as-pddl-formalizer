# p39 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The package declaration both miscounts the 21 packages as seven and uses the over-generating pseudo-range `obj11` to `obj73`. The initial placement relies on “similarly” without an identifier mapping, seven airport-to-city facts are absent, and only six of 21 irregular goals are stated. A bounded inventory, one complete index rule, and a full goal list repair those defects; the unsupported efficiency implication is removed.

包裹声明把 21 个包裹误计为七个，并使用会过度生成标识符的伪范围 `obj11` 到 `obj73`。初始位置依赖没有标识符映射的“类似”表述，缺少七个机场到城市的事实，而且 21 个不规则目标中仅明确陈述了六个。用有界清单、一条完整索引规则和完整目标列表即可修复；同时删除无 PDDL 支持的效率暗示。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics.
- `golden_problem.pddl`: 51 objects (lines 3–55), 102 init atoms (lines 56–159), and 21 goal atoms (lines 160–182).
- `natural_original.txt`: original one-paragraph English description.
- Semantic total: **174** items.

## Before-rewrite coverage and defects

- Objects: **38/51** covered; 13 package identifiers lacked direct, non-over-generating evidence.
- Init: **46/102** covered; 42 unary/placement facts were ambiguous and seven airport-to-city facts were missing.
- Goal: **6/21** covered; 15 goal atoms were missing.
- Missing: **22**; ambiguous: **55**; contradictory: **1** (seven packages versus 21); over-generated: **42** pseudo-range labels.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `There are seven packages labeled from obj11 to obj73, seven trucks named tru1 to tru7, seven cities named cit1 to cit7, and seven airports, apt1 through apt7, which also serve as locations.` | `There are 21 packages: obj11, …, and obj73; seven trucks named tru1 to tru7; seven cities named cit1 to cit7; and seven airports, apt1 through apt7, which also serve as locations.` | Corrects the package count and replaces a pseudo-range with the exact 21-object inventory while retaining the valid vehicle/city/airport wording. / 修正包裹数量并用精确清单替换伪范围，同时保留正确的车辆、城市和机场表述。 | `golden_problem.pddl:4–54` (object inventory) and `golden_problem.pddl:57–77` (21 package atoms) |
| 2 | `Trucks are stationed at positions pos1 through pos7, each in their respective cities cit1 to cit7, along with three packages per position.` | `For every integer i from 1 through 7, position posi and airport apti are locations in city citi, truck trui is initially at posi, and packages obji1, obji2, and obji3 are initially at posi; in these identifiers, i is the same integer appended to pos, apt, cit, and tru and placed between obj and the package suffix 1, 2, or 3.` | Supplies complete, same-index construction for location types, all 14 city memberships, and all 28 truck/package placements. / 为地点类型、全部 14 个城市隶属关系及全部 28 个卡车/包裹位置提供完整同索引构造。 | `golden_problem.pddl:92–112`, `golden_problem.pddl:117–158` |
| 3 | `Similarly, the positions pos2 to pos7 in cities cit2 to cit7 are each associated with one truck and three packages.` | `The preceding complete rule covers indices 2 through 7 as well.` | Removes vague standalone evidence and makes clear that the finite rule—not an inferred analogy—covers the remaining indices. / 删除模糊的独立证据，并明确由有限规则覆盖其余索引。 | `golden_problem.pddl:121–158` |
| 4 | `These targets include … several other packages … For example, obj13 … obj32 … obj11 …` | `These targets are obj61 reaching apt5, …, and obj51 remaining at pos5.` | Replaces examples and a vague placeholder with all 21 irregular goal pairs. / 用全部 21 个不规则目标对替换示例和模糊占位语。 | `golden_problem.pddl:161–181` (complete goal conjunction) |
| 5 | `to meet the specified destinations efficiently` | `to meet the specified destinations` | Removes an optimization implication absent from the golden goal and domain. / 删除黄金目标与领域中不存在的优化含义。 | `golden_problem.pddl:160–182` contains only the destination conjunction; no `:metric` is present |

## Material deliberately preserved

- The opening, valid truck/city/airport ranges, explicit index-1 example, ordered airplane starts, goal introduction, and planning-oriented close were preserved.
- The original one-paragraph tone and organization were retained wherever they did not create semantic defects.

## Post-rewrite verification

- Objects: **51/51**; init: **102/102**; goal: **21/21**.
- Atomic evidence ledger: **174/174** rows covered. Expanding the rule for exactly `i = 1…7` yields 14 location names, 14 city-membership atoms, and 28 initial truck/package `AT` atoms, with no extras.
- Missing: **0**; ambiguous: **0**; contradictory: **0**; over-generated: **0**.

Final assertion: all golden items have unique direct or deterministic-rule evidence and no extra object, fact, or goal is implied.

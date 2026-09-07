# p91 Natural Logistics minimal rewrite audit

Decision: `REWRITE REQUIRED`

The original omits location identifiers and all initial mappings, falsely says package locations are distinct, and supplies only four of 14 goals while implying goals for nine nongolden packages. The final English repairs exactly those spans.

原文遗漏地点标识符和全部初始映射，错误声称包裹位置彼此不同，并且只给出 14 个目标中的 4 个，同时暗示九个非黄金包裹目标。最终英文只修复这些片段。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 56/56 parsed.
- Initial-state atoms: 112/112 parsed, including all unary type facts.
- Goal atoms: 14/14 parsed.
- Total semantic items: 182.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 42/56 |
| Initial atoms covered | 42/112 |
| Goal atoms covered | 4/14 |
| Missing | 74 |
| Ambiguous/incomplete | 3 |
| Contradictory | 17 |
| Over-generated | 9 |

The 74 missing items cover 14 location objects, 14 location-type atoms, 18 in-city atoms, 18 unmapped vehicle/package AT atoms not covered by the distinctness contradiction, and 10 missing goals. Three airport atoms are ambiguous. Seventeen package AT atoms participate in shared locations and contradict “distinct”; nine packages are additionally implied to have nongolden goals.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Specifically, package23 through package1 are scattered across distinct locations. | Specifically, the initial package locations are: package23 is at city1-5; package22 is at city1-5; package21 is at city2-4; package20 is at city2-3; package19 is at city1-2; package18 is at city3-3; package17 is at city2-3; package16 is at city3-5; package15 is at city2-2; package14 is at city2-1; package13 is at city3-4; package12 is at city1-6; package11 is at city1-4; package10 is at city3-3; package9 is at city3-3; package8 is at city1-2; package7 is at city1-4; package6 is at city1-4; package5 is at city3-1; package4 is at city2-1; package3 is at city1-5; package2 is at city3-3; package1 is at city1-2. | Replaces the false claim that all packages occupy distinct locations with the complete irregular initial package mapping. / 用完整的不规则包裹初始映射替换所有包裹位于不同地点的错误说法。 | `golden_problem.pddl:lines 101-123: all package (AT ...) atoms` |
| 2 | We have three major city hubs: city1, city2, and city3, each with various locations and airports within them. | We have three major city hubs: city1, city2, and city3; for each city index X from 1 to 3 and location index Y from 1 to 6, cityX-Y is a location in cityX, and cityX-6 is an airport. | Defines all 18 location identifiers, their cities, and the -6 airport suffix. / 定义全部 18 个地点标识符、所属城市和 -6 机场后缀。 | `golden_problem.pddl:lines 8-11: location objects`<br>`golden_problem.pddl:lines 50-88: location, airport, and in-city atoms` |
| 3 | Each vehicle is stationed at specific locations within these cities. | The airplanes are stationed as follows: plane7 is at city1-6; plane6 is at city2-6; plane5 is at city1-6; plane4 is at city1-6; plane3 is at city3-6; plane2 is at city1-6; plane1 is at city2-6. The trucks are stationed as follows: truck5 is at city3-4; truck4 is at city2-3; truck3 is at city1-5; truck2 is at city1-3; truck1 is at city1-6. | Expands unspecified vehicle positions into all seven airplane and five truck locations. / 将未指定的车辆位置展开为七架飞机和五辆卡车的全部位置。 | `golden_problem.pddl:lines 89-100: vehicle (AT ...) atoms` |
| 4 | For example, package23 needs to be transported to city2-3, while package22 should remain at city1-5. Other packages need to be carefully placed according to the requirements, such as transferring package21 to city1-6 and package20 to city1-1. Our end goal is to ensure all specified packages are accurately positioned at their respective target locations, thus completing the logistics challenge. | The required package destinations are: package23 must be at city2-3; package22 must be at city1-5; package21 must be at city1-6; package20 must be at city1-1; package19 must be at city1-3; package18 must be at city1-3; package17 must be at city1-5; package16 must be at city1-1; package15 must be at city3-3; package14 must be at city1-5; package13 must be at city2-5; package12 must be at city3-2; package11 must be at city2-6; package10 must be at city1-6. All 14 listed package destinations must hold simultaneously. | Replaces four examples and vague remaining requirements with the complete irregular 14-atom goal, excluding nine packages with no golden goal. / 用完整的不规则 14 原子目标替换四个示例和模糊剩余要求，并排除没有黄金目标的九个包裹。 | `golden_problem.pddl:lines 124-137: conjunctive 14-atom goal` |

## Material deliberately preserved

- The opening framing and finite fleet declarations.
- The task-transition sentence.
- All unaffected wording and narrative order.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 56/56 |
| Initial atoms covered | 112/112 |
| Goal atoms covered | 14/14 |
| Ledger rows | 182/182 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded against the golden sibling family, and every irregular initial or goal mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有界规则均已对照黄金同族项完整展开，每个不规则初始或目标映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

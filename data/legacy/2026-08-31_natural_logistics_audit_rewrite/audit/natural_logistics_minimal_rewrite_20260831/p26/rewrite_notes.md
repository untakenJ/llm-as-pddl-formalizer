# p26 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original names the packages, cities, trucks, and planes, but it never defines the 52 location identifiers or their exact city/airport roles, gives only examples or vague cities for every initial placement, and leaves every goal destination identifier unresolved. Four contiguous repairs add one bounded city-layout rule and exact vehicle, package, and goal mappings while preserving the surrounding inventory and tone.

原描述列出了包裹、城市、卡车和飞机，但没有定义 52 个地点标识符及其准确的城市/机场角色；所有初始位置都只用示例或模糊城市说明，所有目标地点标识符也都无法确定。四处连续修订增加一条有界城市布局规则，以及精确的车辆、包裹和目标映射，同时保留周围的清单与语气。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 100 objects on lines 3–16; 200 init atoms on lines 17–216; 7 goal atoms on lines 217–223.
- `natural_original.txt`: audited original English description.
- Exact totals: objects 100; init 200; goal 7; semantic items 307.

## Before-rewrite coverage and defects

- Objects covered: 48/100
- Init atoms covered: 48/200
- Goal atoms covered: 0/7
- Missing: 0
- Ambiguous/incomplete: 211 (52 location objects, 152 init atoms, and 7 goal atoms)
- Contradictory: 1 (the vehicle sentence says “different locations,” but three truck pairs are co-located)
- Over-generated: 0

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Each city has several locations and some also have airports. | For each N from 1 through 13, cityN has locations cityN-1, cityN-2, and cityN-3, plus the airport location cityN-4; all four locations are part of cityN. | Replaces vague quantities with a complete bounded identifier, type, airport, and city-membership rule. / 用完整的有界标识符、类型、机场和城市归属规则替换模糊数量。 | Location objects: `golden_problem.pddl:9–16`; location/airport types: lines 65–129; all 52 `(in-city ...)` atoms: lines 130–181. |
| 2 | For the initial setup, planes and trucks are stationed in different locations within their respective cities. For example, plane1 is currently located at the airport in city2, while truck23 is at a location in city13. | For the initial setup, the planes and trucks are stationed as follows. Plane5 is at city12-4, plane4 at city8-4, plane3 at city6-4, plane2 at city13-4, and plane1 at city2-4. Truck23 is at city13-2, truck22 at city12-3, truck21 at city11-3, truck20 at city10-1, truck19 at city9-1, truck18 at city8-2, truck17 at city7-3, truck16 at city6-3, truck15 at city5-2, truck14 at city4-1, truck13 at city3-3, truck12 at city2-1, truck11 at city1-1, truck10 at city10-3, truck9 at city8-1, truck8 at city2-2, truck7 at city9-4, truck6 at city9-2, truck5 at city8-2, truck4 at city7-3, truck3 at city7-1, truck2 at city8-1, and truck1 at city5-4. | Examples cannot recover the irregular five-plane and 23-truck mapping; “different locations” also conflicts with three golden truck co-locations. The replacement enumerates every golden pair. / 示例无法恢复不规则的五架飞机和 23 辆卡车映射；“不同地点”还与三组黄金卡车共址事实冲突。修订后枚举每个黄金对应对。 | Plane atoms: `golden_problem.pddl:182–186`; truck atoms: lines 187–209, including truck18/truck5 at `city8-2`, truck17/truck4 at `city7-3`, and truck9/truck2 at `city8-1`. |
| 3 | The packages are distributed as follows: package7 is at the airport in city1, package6 is at a location in city2, package5 is at the same location as truck20 in city10, package4 is at the airport in city5, package3 is at a location in city11, package2 is at the same location as truck21 in city11, and package1 is at a location in city4. | The packages are distributed as follows: package7 is at city1-4, package6 is at city2-3, package5 is at city10-1, package4 is at city5-4, package3 is at city11-1, package2 is at city11-3, and package1 is at city4-2. | Replaces city-only or relational descriptions with the seven exact initial identifiers. / 用七个精确初始标识符替换仅说明城市或依赖关系的描述。 | `golden_problem.pddl:210–216`: the seven package `(at ...)` atoms. |
| 4 | My goal is to move these packages to specific destinations: package7 needs to reach a location in city12, package6 has to be delivered to a location in city9, package5 should be transported to the same location as package7 in city12, package4 is to be sent to the airport in city8, package3 needs to arrive at the airport in city13, package2 is to be delivered to a location in city7, and finally, package1 has to reach a location in city13. | My goal is to move these packages to specific destinations: package7 needs to reach city12-3, package6 has to be delivered to city9-3, package5 should be transported to city12-3, package4 is to be sent to city8-4, package3 needs to arrive at city13-4, package2 is to be delivered to city7-1, and finally, package1 has to reach city13-1. | Makes every conjunctive goal destination explicit; the irregular mapping cannot be inferred from city names alone. / 明确每个合取目标的目的地；不规则映射不能仅凭城市名称推断。 | `golden_problem.pddl:217–223`: all seven goal atoms. |

## Material deliberately preserved

- The opening package/city counts and the exact package, city, truck, and airplane ranges.
- The availability sentence, list ordering, first-person tone, and single-paragraph organization.
- Every phrase that did not obscure an identifier or mapping.

## Post-rewrite verification

- Objects covered: 100/100
- Init atoms covered: 200/200
- Goal atoms covered: 7/7
- Evidence ledger rows: 307/307
- Substitution of each `N = 1, ..., 13` yields exactly 52 location objects, 52 location atoms, 13 airport atoms, and 52 city-membership atoms; all irregular placements are explicitly enumerated.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

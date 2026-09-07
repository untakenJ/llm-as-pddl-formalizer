# p92 Natural Logistics minimal rewrite audit

Decision: `REWRITE REQUIRED`

The original leaves most location identities and 66 of 72 initial placements unspecified; its seven package goals are complete. The final English adds the finite location rule, complete irregular initial mappings, and removes unsupported safety/efficiency objectives.

原文未指定大多数地点身份以及 72 个初始位置中的 66 个；七个包裹目标完整。最终英文加入有限地点规则、完整的不规则初始映射，并删除未受支持的安全/效率目标。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 116/116 parsed.
- Initial-state atoms: 232/232 parsed, including all unary type facts.
- Goal atoms: 7/7 parsed.
- Total semantic items: 355.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 91/116 |
| Initial atoms covered | 98/232 |
| Goal atoms covered | 7/7 |
| Missing | 149 |
| Ambiguous/incomplete | 10 |
| Contradictory | 0 |
| Over-generated | 2 |

The 149 missing items are 25 location objects, 25 location-type atoms, 33 in-city atoms, and 66 unspecified AT atoms. Ten airport atoms remain ambiguous after the one named airport. Safety and efficiency are two over-generated objectives.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Each city contains multiple locations, including airports. | For each city index X from 1 to 11 and location index Y from 1 to 3, cityX-Y is a location in cityX, and cityX-3 is an airport. | Defines the complete 11-by-3 location family, city correspondence, and airport suffix. / 定义完整的 11×3 地点族、城市对应关系和机场后缀。 | `golden_problem.pddl:lines 14-18: location objects`<br>`golden_problem.pddl:lines 102-178: location, airport, and in-city atoms` |
| 2 | The trucks and planes are stationed at specific locations within these cities at the start of the game. For example, plane1 is at airport city6-3, and truck1 is at city5-2. | Initially, the airplanes are stationed as follows: plane13 is at city10-3; plane12 is at city5-3; plane11 is at city11-3; plane10 is at city1-3; plane9 is at city9-3; plane8 is at city7-3; plane7 is at city1-3; plane6 is at city8-3; plane5 is at city7-3; plane4 is at city9-3; plane3 is at city1-3; plane2 is at city11-3; plane1 is at city6-3. The trucks are stationed as follows: truck52 is at city11-2; truck51 is at city10-1; truck50 is at city9-2; truck49 is at city8-1; truck48 is at city7-1; truck47 is at city6-1; truck46 is at city5-2; truck45 is at city4-1; truck44 is at city3-2; truck43 is at city2-2; truck42 is at city1-2; truck41 is at city7-2; truck40 is at city6-1; truck39 is at city2-3; truck38 is at city3-1; truck37 is at city2-3; truck36 is at city7-1; truck35 is at city8-2; truck34 is at city8-2; truck33 is at city7-2; truck32 is at city6-3; truck31 is at city2-2; truck30 is at city11-3; truck29 is at city1-2; truck28 is at city3-1; truck27 is at city9-2; truck26 is at city7-2; truck25 is at city1-3; truck24 is at city4-1; truck23 is at city9-2; truck22 is at city3-1; truck21 is at city1-1; truck20 is at city7-3; truck19 is at city4-3; truck18 is at city1-1; truck17 is at city4-3; truck16 is at city11-3; truck15 is at city6-2; truck14 is at city5-3; truck13 is at city5-1; truck12 is at city8-1; truck11 is at city8-1; truck10 is at city5-2; truck9 is at city8-3; truck8 is at city1-1; truck7 is at city8-2; truck6 is at city9-3; truck5 is at city10-2; truck4 is at city6-3; truck3 is at city11-1; truck2 is at city5-3; truck1 is at city5-2. | Replaces one plane and one truck example with all 13 airplane and 52 truck initial locations. / 用全部 13 架飞机和 52 辆卡车的初始位置替换一个飞机和一个卡车示例。 | `golden_problem.pddl:lines 179-243: vehicle (AT ...) atoms` |
| 3 | The packages are spread out in various locations as well; for instance, package1, package2, and package3 are all at city7-2, while package7 starts at city4-2. | The initial package locations are: package7 is at city4-2; package6 is at city4-1; package5 is at city11-2; package4 is at city2-2; package3 is at city7-2; package2 is at city7-2; package1 is at city7-2. | Replaces four package examples with the complete seven-package initial mapping. / 用完整的七包裹初始映射替换四个包裹示例。 | `golden_problem.pddl:lines 244-250: package (AT ...) atoms` |
| 4 | By using the available trucks and airplanes strategically, each package must reach its destination safely and efficiently. | All seven listed package destinations must hold simultaneously. | Removes unsupported safety and efficiency objectives and makes the seven-way goal conjunction explicit. / 删除未受支持的安全和效率目标，并明确七个目标同时成立。 | `golden_problem.pddl:lines 251-257: conjunctive seven-atom goal` |

## Material deliberately preserved

- All package, city, truck, and airplane range declarations.
- The complete seven-package goal sentence, verbatim.
- The original narrative order.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 116/116 |
| Initial atoms covered | 232/232 |
| Goal atoms covered | 7/7 |
| Ledger rows | 355/355 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded against the golden sibling family, and every irregular initial or goal mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有界规则均已对照黄金同族项完整展开，每个不规则初始或目标映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

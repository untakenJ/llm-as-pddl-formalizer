# p89 Natural Logistics minimal rewrite audit

Decision: `REWRITE REQUIRED`

The original leaves the entire location system and 59 of 61 initial placements unspecified, although its eight package goals are complete. The final English adds one finite location rule, the required irregular initial mappings, and removes the unsupported efficiency objective.

原文未指定整个地点系统以及 61 个初始位置中的 59 个，但八个包裹目标完整。最终英文加入一条有限地点规则、所需的不规则初始映射，并删除未受支持的效率目标。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 206/206 parsed.
- Initial-state atoms: 412/412 parsed, including all unary type facts.
- Goal atoms: 8/8 parsed.
- Total semantic items: 626.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 100/206 |
| Initial atoms covered | 104/412 |
| Goal atoms covered | 8/8 |
| Missing | 385 |
| Ambiguous/incomplete | 29 |
| Contradictory | 0 |
| Over-generated | 1 |

The 385 missing items are 106 location objects, 106 location-type atoms, 114 location-to-city atoms, and 59 unspecified AT atoms. The 29 airport atoms are ambiguous under “some designated as airports.” The efficiency objective is one over-generated requirement.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Each city has specific locations, including some designated as airports. | For each city index X from 1 to 29 and location index Y from 1 to 4, cityX-Y is a location in cityX, and cityX-4 is an airport. | Defines the complete 29-by-4 location family, city correspondence, and airport suffix. / 定义完整的 29×4 地点族、城市对应关系和机场后缀。 | `golden_problem.pddl:lines 14-31: all location objects`<br>`golden_problem.pddl:lines 122-382: location, airport, and in-city atoms` |
| 2 | Currently, the planes and trucks are parked at specific city locations, and packages are scattered across different places. For example, package 23 is currently located at city 26, location 2, while package 22 is at city 1, location 1. | Currently, the planes are parked as follows: plane9 is at city28-4; plane8 is at city23-4; plane7 is at city27-4; plane6 is at city29-4; plane5 is at city13-4; plane4 is at city4-4; plane3 is at city14-4; plane2 is at city14-4; plane1 is at city13-4. The trucks are parked as follows: truck29 is at city29-1; truck28 is at city28-2; truck27 is at city27-3; truck26 is at city26-1; truck25 is at city25-2; truck24 is at city24-3; truck23 is at city23-3; truck22 is at city22-3; truck21 is at city21-1; truck20 is at city20-1; truck19 is at city19-3; truck18 is at city18-2; truck17 is at city17-3; truck16 is at city16-2; truck15 is at city15-3; truck14 is at city14-3; truck13 is at city13-2; truck12 is at city12-3; truck11 is at city11-1; truck10 is at city10-2; truck9 is at city9-3; truck8 is at city8-2; truck7 is at city7-3; truck6 is at city6-3; truck5 is at city5-3; truck4 is at city4-2; truck3 is at city3-2; truck2 is at city2-3; truck1 is at city1-1. The packages are located as follows: package23 is at city26-2; package22 is at city1-1; package21 is at city3-1; package20 is at city18-2; package19 is at city17-2; package18 is at city21-1; package17 is at city1-4; package16 is at city29-4; package15 is at city1-2; package14 is at city4-4; package13 is at city10-1; package12 is at city13-1; package11 is at city24-3; package10 is at city5-4; package9 is at city9-4; package8 is at city3-4; package7 is at city13-1; package6 is at city7-3; package5 is at city16-1; package4 is at city3-2; package3 is at city17-1; package2 is at city11-1; package1 is at city21-4. | Replaces two package examples and unspecified vehicle placements with every irregular airplane, truck, and package initial location. / 用全部不规则的飞机、卡车和包裹初始位置替换两个包裹示例和未指定的车辆位置。 | `golden_problem.pddl:lines 383-443: all 61 initial (AT ...) atoms` |
| 3 | Your task is to efficiently coordinate the movement of vehicles and packages to achieve this desired outcome. | All eight listed package destinations must hold simultaneously. | Removes the unsupported efficiency objective and explicitly states the eight-way goal conjunction. / 删除未受支持的效率目标，并明确八个目标同时成立。 | `golden_problem.pddl:lines 444-451: conjunctive eight-atom goal` |

## Material deliberately preserved

- All package, city, truck, and airplane range declarations.
- The complete eight-package goal sentence, verbatim.
- The original setup-to-goal ordering.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 206/206 |
| Initial atoms covered | 412/412 |
| Goal atoms covered | 8/8 |
| Ledger rows | 626/626 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded against the golden sibling family, and every irregular initial or goal mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有界规则均已对照黄金同族项完整展开，每个不规则初始或目标映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

# p87 audit and rewrite notes

**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Four local sentences need repair because examples, vague regional descriptions, and a disjunction leave locations and irregular initial mappings unrecoverable.
中文：需要改写。四个局部句子需要修复，因为示例、模糊的区域描述和析取表达使地点及不规则初始映射无法恢复。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **48 objects**, **96 init atoms**, **8 goal atoms**, **152 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 46/48
- Init atoms covered: 57/96
- Goal atoms covered: 8/8
- Missing: 24; ambiguous: 17; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Locations within these cities include designated areas (like city3-2 and city2-1) and airports (such as city1-3 and city2-3). | For each integer i from 1 through 3, the locations cityi-1, cityi-2, and cityi-3 are formed by concatenating city, i, and respectively -1, -2, and -3; all three locations are in cityi, and cityi-3 is an airport. | Examples did not enumerate or deterministically construct all nine locations, three airports, and nine in-city facts. / 示例不能枚举或确定性构造全部九个地点、三个机场以及九个地点—城市关系。 | golden_problem.pddl:lines 8-9: nine location objects<br>golden_problem.pddl:lines 49-69: location, airport, and in-city atoms |
| 2 | Initially, the airplanes are positioned as follows: plane6 is at city2-3, plane5 and plane1 are both stationed at city1-3, and planes 4, 3, and 2 are at city3-3 or city2-3. | Initially, the airplanes are positioned as follows: plane6 is at city2-3, plane5 and plane1 are both stationed at city1-3, plane4 is at city3-3, and plane3 and plane2 are at city2-3. | The disjunction left the initial locations of Plane 4, Plane 3, and Plane 2 unresolved. / 析取表达使飞机 4、飞机 3 和飞机 2 的初始位置无法确定。 | golden_problem.pddl:lines 70-75: all six airplane initial locations |
| 3 | Regarding trucks: truck22 is at city3-2, trucks like truck21 and truck16 are at various city2 locations, whereas trucks 20, 18, and 13 are spread across city1 locations, and several others are in use around city3. | Regarding trucks: truck22 and truck4 are at city3-2; truck21 and truck16 are at city2-1; truck20, truck18, and truck13 are at city1-2; truck19, truck15, truck9, truck7, truck6, truck5, and truck1 are at city2-3; truck17, truck14, truck12, and truck3 are at city2-2; truck11 and truck8 are at city3-3; truck10 is at city3-1; and truck2 is at city1-1. | Vague examples and regional descriptions did not uniquely support 21 of the 22 irregular truck locations. / 模糊示例和区域性描述无法唯一支持 22 个不规则卡车位置中的 21 个。 | golden_problem.pddl:lines 76-97: all 22 truck initial locations |
| 4 | Packages are spread across the cities too: for example, package8 is at city1-2, package7 is at city2-1, package6 is at city3-2, and package5 and package1 both start at city1-3. | Packages are spread across the cities too: package8 is at city1-2; package7 is at city2-1; package6 and package2 are at city3-2; package5 and package1 are at city1-3; package4 is at city3-3; and package3 is at city2-2. | The example-only sentence omitted the initial locations of Package 4, Package 3, and Package 2. / 仅含示例的句子遗漏了包裹 4、包裹 3 和包裹 2 的初始位置。 | golden_problem.pddl:lines 98-105: all eight package initial locations |

## Material deliberately preserved / 有意保留的实质文本

- The opening context, complete package/city/vehicle inventories, and complete eight-atom goal sentence were preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 48/48
- Init atoms covered: 96/96
- Goal atoms covered: 8/8
- Ledger rows: 152 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked for exact equality with the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, with all four final defect counts equal to zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。


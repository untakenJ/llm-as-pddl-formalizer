# p75 audit and rewrite notes

**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Three local substitutions are necessary because the package pseudo-range over-generates labels and the example-based city and initial-location mappings do not expand uniquely.
中文：需要改写。必须进行三处局部替换，因为包裹伪范围会多生成标签，而基于示例的城市关系和初始位置关系不能唯一展开。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem; authoritative for this audit.
- `natural_original.txt`: original English description.
- Parsed totals: **95 objects**, **190 init atoms**, **38 goal atoms**, **323 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 91/95
- Init atoms covered: 105/190
- Goal atoms covered: 38/38
- Missing: 0; ambiguous: 89; contradictory: 0; over-generated: 84.
- The over-generation count is the 84 extra integer labels implied by the pseudo-range `obj11` through `obj133` beyond the 39 golden grouped labels.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Initially, we have 39 packages labeled from obj11 to obj133, 13 trucks named tru1 to tru13, 13 cities known as cit1 to cit13, and several locations, both positional and airport, across these cities. | Initially, for each integer i from 1 through 13, there are exactly three packages whose names are formed by concatenating obj, i, and each of 1, 2, and 3; one truck named by concatenating tru and i; one city named by concatenating cit and i; and two locations named by concatenating pos and i and apt and i, with the latter also being an airport. | The package pseudo-range over-generated 84 labels, and the locations were neither finitely named nor typed. / 包裹伪范围会多生成 84 个标签，而且地点既未被有限地命名，也未明确类型。 | golden_problem.pddl:lines 4-98: complete object declarations<br>golden_problem.pddl:lines 101-208: unary package, truck, city, location, airport, and airplane facts |
| 2 | Each city hosts a position and an airport, for example, pos1 and apt1 are within cit1. | For each integer i from 1 through 13, the position named by concatenating pos and i and the airport named by concatenating apt and the same i are both within the city named by concatenating cit and i. | One example did not establish the other 24 required in-city atoms. / 单个示例不能建立其余 24 个必需的地点—城市关系。 | golden_problem.pddl:lines 265-290: all 26 in-city atoms |
| 3 | Correspondingly, each truck, along with its respective packages, is located at a position within a city. For instance, tru1 and packages obj11, obj12, obj13 are located at pos1 within cit1. | For each integer i from 1 through 13, the truck named by concatenating tru and i and the three packages named by concatenating obj, i, and each of 1, 2, and 3 are all initially located at the position named by concatenating pos and the same i. | The vague correspondence plus one example did not define the other 48 initial truck/package locations. / 模糊的对应描述加一个示例，不能定义其余 48 个卡车/包裹初始位置。 | golden_problem.pddl:lines 213-264: all 52 initial truck/package at atoms |

## Material deliberately preserved / 有意保留的实质文本

- The opening sentence and both airplane sentences were preserved verbatim.
- The complete two-paragraph goal wording, including all 38 goal pairs, was preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 95/95
- Init atoms covered: 190/190
- Goal atoms covered: 38/38
- Ledger rows: 323 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked against its sibling atoms.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** all golden objects, init atoms, and conjunctive goal atoms are uniquely covered, and all four final defect counts are zero. / **最终断言：**全部黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。


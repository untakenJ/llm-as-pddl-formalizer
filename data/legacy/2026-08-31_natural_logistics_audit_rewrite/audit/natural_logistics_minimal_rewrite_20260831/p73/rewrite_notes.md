# p73 audit and rewrite notes

**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Three local rule substitutions are necessary to remove an over-generating package pseudo-range and make the package, truck, location, airport, and city mappings uniquely recoverable.
中文：需要改写。必须进行三处局部规则替换，以消除会过度生成的包裹伪范围，并使包裹、卡车、地点、机场和城市的对应关系都可被唯一恢复。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem; authoritative for this audit.
- `natural_original.txt`: original English description.
- Parsed totals: **95 objects**, **190 init atoms**, **37 goal atoms**, **322 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 92/95
- Init atoms covered: 106/190
- Goal atoms covered: 37/37
- Missing: 9; ambiguous: 78; contradictory: 0; over-generated: 84.
- The over-generation count is the 84 extra integer labels implied by the pseudo-range `obj11` through `obj133` beyond the 39 golden grouped labels.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | There are packages named obj11 through obj133 and these are located across various positions labeled pos1, pos2, ..., pos13. | There are exactly 39 packages: for each integer i from 1 through 13, the three package names are formed by concatenating obj, i, and each of 1, 2, and 3, and all three packages are initially located at the position named by concatenating pos and the same i. | The pseudo-range over-generated 84 package labels and 'across various positions' did not define the initial package-to-position mapping. / 该伪范围会多生成 84 个包裹标签，而“分布在各种位置”没有定义包裹初始位置的对应关系。 | golden_problem.pddl:lines 9-11,16-18,23-25,30-32,38-40,45-47,52-54,59-61,67-69,74-76,81-83,88-90,96-98: package objects<br>golden_problem.pddl:lines 101-139: package type atoms<br>golden_problem.pddl:lines 214-216,218-220,222-224,226-228,230-232,234-236,238-240,242-244,246-248,250-252,254-256,258-260,262-264: package initial positions |
| 2 | We also have a series of trucks, tru1 through tru13, which are stationed at these positions. | We also have a series of trucks, tru1 through tru13; for each integer i from 1 through 13, the truck named by concatenating tru and i is initially stationed at the position named by concatenating pos and the same i. | The phrase 'these positions' did not uniquely pair each truck with its initial position. / “这些位置”没有唯一确定每辆卡车与其初始位置的配对。 | golden_problem.pddl:lines 140-152: (TRUCK TRU1) through (TRUCK TRU13)<br>golden_problem.pddl:lines 213,217,221,225,229,233,237,241,245,249,253,257,261: truck initial positions |
| 3 | The setting includes cities cit1 through cit13, each containing a position and an airport, creating a map of interrelated locations. | The setting includes cities cit1 through cit13; for each integer i from 1 through 13, the names citi, posi, and apti are formed by concatenating cit, pos, and apt respectively with i, posi and apti are locations, apti is an airport, and both posi and apti are in citi, creating a map of interrelated locations. | The original did not name every position/airport or define the shared-index city correspondence and unary location/airport facts. / 原文没有给出全部位置与机场名称，也没有定义共享索引的城市对应关系及地点/机场类型事实。 | golden_problem.pddl:lines 153-165: city atoms<br>golden_problem.pddl:lines 166-204: location and airport atoms<br>golden_problem.pddl:lines 265-290: in-city atoms |

## Material deliberately preserved / 有意保留的实质文本

- The opening sentence was preserved verbatim because it is compatible context.
- The complete ordered airplane mapping was preserved verbatim.
- The complete 37-atom goal sentence and closing sentence were preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 95/95
- Init atoms covered: 190/190
- Goal atoms covered: 37/37
- Ledger rows: 322 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked against its sibling atoms.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** all golden objects, init atoms, and conjunctive goal atoms are uniquely covered, and all four final defect counts are zero. / **最终断言：**全部黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。


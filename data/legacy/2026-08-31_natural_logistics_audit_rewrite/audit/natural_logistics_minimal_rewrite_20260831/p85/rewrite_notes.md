# p85 audit and rewrite notes

**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Two local edits are needed to name both airplanes and state the six initial truck locations; all package and goal mappings are already complete.
中文：需要改写。需做两处局部修改，以命名两架飞机并说明六辆卡车的初始地点；所有包裹与目标对应关系已完整。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **32 objects**, **64 init atoms**, **6 goal atoms**, **102 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 30/32
- Init atoms covered: 54/64
- Goal atoms covered: 6/6
- Missing: 6; ambiguous: 6; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | City 6 through City 1 are home to Truck 6 to Truck 1 respectively. | Truck 6 through Truck 1 are initially at the normal locations of City 6 through City 1 respectively. | The original paired trucks with cities but did not uniquely state the six initial truck locations. / 原文只把卡车与城市配对，却没有唯一说明六辆卡车的初始地点。 | golden_problem.pddl:lines 20-25: truck type atoms<br>golden_problem.pddl:lines 60-65: (AT TRUCKi CITYi-1) for i=6..1 |
| 2 | There are two airplanes initially stationed at the airport in City 4. | There are two airplanes, Plane 2 and Plane 1, initially stationed at the airport in City 4. | Two airplanes were counted and located but not individually named, so Plane 1 and Plane 2 were not recoverable as distinct objects. / 原文只说明两架飞机及其位置，却未逐一命名，因此无法恢复飞机 1 和飞机 2 这两个独立对象。 | golden_problem.pddl:line 5: plane2 and plane1 objects<br>golden_problem.pddl:lines 26-27: airplane type atoms<br>golden_problem.pddl:lines 58-59: both airplanes at city4-2 |

## Material deliberately preserved / 有意保留的实质文本

- The package, city, location, and airport descriptions were preserved because their six-city mapping is complete.
- All six explicit package initial locations and all six goal destinations were preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 32/32
- Init atoms covered: 64/64
- Goal atoms covered: 6/6
- Ledger rows: 102 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked for exact equality with the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, with all four final defect counts equal to zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。


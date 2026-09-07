# p76 audit and rewrite notes

**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Two local substitutions are necessary because 'similarly' and 'continuing in the same way' do not uniquely support the unlisted initial-location and in-city atoms.
中文：需要改写。必须进行两处局部替换，因为“同样”及“以同样方式继续”无法唯一支持未列出的初始位置原子和地点—城市原子。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem; authoritative for this audit.
- `natural_original.txt`: original English description.
- Parsed totals: **95 objects**, **190 init atoms**, **38 goal atoms**, **323 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 95/95
- Init atoms covered: 124/190
- Goal atoms covered: 38/38
- Missing: 0; ambiguous: 66; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | The trucks and packages are initially located as follows: tru1 along with packages obj11, obj12, and obj13 are at position pos1; tru2 with obj21, obj22, and obj23 at pos2, and similarly for the other trucks at their respective positions and corresponding packages. | The trucks and packages are initially located as follows: for each integer i from 1 through 13, the truck named by concatenating tru and i and the three packages named by concatenating obj, i, and each of 1, 2, and 3 are all at the position named by concatenating pos and the same i. | 'Similarly' and 'respective/corresponding' left 44 initial at atoms without a uniquely expandable rule. / “同样”以及“各自/对应”没有为其余 44 个初始位置原子提供可唯一展开的规则。 | golden_problem.pddl:lines 213-264: all 52 initial truck/package at atoms |
| 2 | Each position and airport is situated within different cities: pos1 and apt1 in cit1, pos2 and apt2 in cit2, continuing in the same way up to pos13 and apt13 in cit13. | Each position and airport is situated within its indexed city: for each integer i from 1 through 13, the position named by concatenating pos and i and the airport named by concatenating apt and the same i are both in the city named by concatenating cit and i. | 'Continuing in the same way' did not count as a complete deterministic correspondence for the remaining 22 in-city atoms. / “以同样方式继续”不能作为其余 22 个地点—城市原子的完整确定性对应规则。 | golden_problem.pddl:lines 265-290: all 26 in-city atoms |

## Material deliberately preserved / 有意保留的实质文本

- The explicit package, vehicle, city/location, airport, and airplane sentences were preserved verbatim.
- The complete 38-atom goal sentence was preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 95/95
- Init atoms covered: 190/190
- Goal atoms covered: 38/38
- Ledger rows: 323 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked against its sibling atoms.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** all golden objects, init atoms, and conjunctive goal atoms are uniquely covered, and all four final defect counts are zero. / **最终断言：**全部黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。


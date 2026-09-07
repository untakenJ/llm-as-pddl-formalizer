# p54 audit and rewrite notes

## Decision

REWRITE REQUIRED

The original goal list and airplane placements are correct, but the package pseudo-range over-generates identifiers, all truck/package initial locations are unspecified, seven airport type facts are absent, and the location-to-city correspondence is vague. Four local edits supply exact finite rules and repair the single spaced identifier apt 10.

原文的目标列表和飞机位置正确，但包裹伪范围会多生成标识符，所有卡车和包裹的初始位置均未指定，缺少七个机场类型事实，而且地点到城市的对应关系含糊。四处局部修改补充了精确的有限规则，并修正了带空格的标识符 apt 10。

## Source inventory and totals

- golden_domain.pddl: logistics predicate and action semantics.
- golden_problem.pddl: 73 objects, 146 init atoms, and 28 goal atoms; 247 semantic items total.
- natural_original.txt: original English description.

## Before-rewrite audit

- Object coverage: 71/73. Obj62 and obj81 occur only inside the over-generating pseudo-range.
- Init coverage: 77/146. Sixty-two init atoms are ambiguous (two package type facts, 40 truck/package placements, and 20 in-city atoms), and seven airport type facts are missing.
- Goal coverage: 28/28; apt 10 is uniquely intended as apt10 but is repaired to preserve the exact identifier.
- Defects across golden semantic items: missing 7; ambiguous 64; contradictory 0.
- Over-generated items: 63 non-golden package identifiers suggested by treating obj11 through obj103 as an integer range.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | In the Logistics game, we start with the following initial conditions: We have several packages including obj11 through obj103, and trucks tru1 through tru10. | In the Logistics game, we start with the following initial conditions: for every index i from 1 through 10, the three package labels are formed by writing obj, then i, then 1, 2, or 3, and the trucks are tru1 through tru10. | The pseudo-range is not the exact 30-object family; the bounded construction is exact. / 伪范围并非准确的 30 个对象集合；有限构造恰好匹配。 | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47,52-54,59-61,66-68,74-76 (OBJ declarations); 79-118 (PACKAGE and TRUCK type facts). |
| 2 | Each package and truck is located in a specific position or city. | Initially, for every index i from 1 through 10, tru followed by i and the three package labels formed by writing obj, then i, then 1, 2, or 3 are all at pos followed by the same i. | The original asserts locations without giving any object-location correspondence; the rule expands to exactly 40 AT atoms. / 原句声称存在位置却没有给出对象到地点的对应；该规则恰好展开为 40 个 AT 原子。 | golden_problem.pddl:165-204 (all truck and package (AT ...) atoms). |
| 3 | apt 10 | apt10 | The space breaks the exact golden identifier; the local edit makes the goal pair literal and unique. / 空格破坏了黄金标识符的精确形式；局部修改使目标对直接且唯一。 | golden_problem.pddl:241: (AT OBJ61 APT10). |
| 4 | Each location including pos1 through pos10 and apt1 through apt10, is situated in various cities, from cit1 to cit10. | Each location, including pos1 through pos10 and apt1 through apt10, is situated in a city from cit1 through cit10: for every index i from 1 through 10, pos followed by i and apt followed by i are both in cit followed by the same i, and each of apt1 through apt10 is an airport. | Various cities gives no correspondence and only apt1, apt6, and apt9 were called airports; the finite same-index rule and airport range supply exactly the missing facts. / “若干城市”没有给出对应关系，且原文只称 apt1、apt6 和 apt9 为机场；有限同索引规则和机场范围恰好补齐事实。 | golden_problem.pddl:119-158 (CITY, LOCATION, AIRPORT facts); 205-224 (all IN-CITY atoms). |

## Deliberately preserved

- The airplane sentence remains verbatim because it identifies all three airplanes, their airport type evidence, and their ordered initial positions correctly. / 飞机句逐字保留，因为它正确给出了三架飞机、相关机场类型证据和有序初始位置。
- The complete 28-pair goal sentence is preserved apart from removing the internal space in apt10. / 完整的 28 对目标句除删除 apt10 内部空格外均予保留。
- The closing constraint sentence and single-paragraph organization remain unchanged. / 结尾约束句和单段结构保持不变。

## Post-rewrite verification

- Object coverage: 73/73.
- Init coverage: 146/146.
- Goal coverage: 28/28.
- Atomic ledger: 247/247 rows covered with unique evidence.
- Missing 0; ambiguous 0; contradictory 0; over-generated 0.

Final assertion: every golden item is uniquely recoverable from the revised English description, and no non-golden item is generated.

最终断言：修订后的英文描述可唯一恢复每个黄金语义项，且不会生成任何非黄金语义项。

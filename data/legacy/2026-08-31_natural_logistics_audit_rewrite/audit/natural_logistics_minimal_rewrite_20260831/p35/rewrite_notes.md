# p35 audit and minimal rewrite notes

Decision: REWRITE REQUIRED

A rewrite is required only for the incorrect package-count span. The localized replacement removes the confirmed defect while preserving every unaffected sentence verbatim.

仅错误的包裹数量片段需要改写。局部替换消除了已确认缺陷，同时逐字保留所有未受影响的句子。

## Source inventory and totals / 来源清单与总数

- golden_domain.pddl: authoritative predicate and action semantics; retained unchanged.
- golden_problem.pddl: authoritative objects, init, and goal; retained unchanged.
- natural_original.txt: audited source description; retained unchanged.
- Exact totals: objects 51/51; init atoms 102/102; goal atoms 19/19; semantic items 172/172.
- 精确总数：对象 51/51；初始原子 102/102；目标原子 19/19；语义项 172/172。

## Before-rewrite audit / 改写前审计

- Coverage: objects 51/51; init 102/102; goal 19/19.
- Defects: missing 0; ambiguous 0; contradictory 1; over-generated 0.
- 覆盖：对象 51/51；初始状态 102/102；目标 19/19。
- 缺陷：缺失 0；歧义 0；冲突 1；过生成 0。

The exact inventory covers every golden package, but its stated count of seven contradicts the 21 enumerated and golden packages.

精确清单覆盖了所有黄金包裹，但所述数量七与列出的 21 个黄金包裹冲突。

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | There are seven packages to manage: | There are twenty-one packages to manage: | The sentence explicitly lists 21 golden package objects, so changing only the incorrect count removes the contradiction.<br>该句明确列出了黄金 PDDL 中的 21 个包裹对象，因此只修改错误数量即可消除冲突。 | golden_problem.pddl:8-10,15-17,23-25,30-32,37-39,44-46,52-54: package objects<br>golden_problem.pddl:57-77: (PACKAGE OBJ11) through (PACKAGE OBJ73) |

## Material deliberately preserved / 有意保留的重要文本

- The exact package inventory after the corrected count was retained verbatim.
  - 修正数量后的精确包裹清单逐字保留。
- All vehicle and package initial placements and all fourteen city memberships were retained verbatim.
  - 所有车辆和包裹初始位置以及全部十四个城市隶属关系均逐字保留。
- The complete irregular goal mapping was retained verbatim.
  - 完整的不规则目标映射逐字保留。

## Post-rewrite verification / 改写后验证

- Coverage: objects 51/51; init 102/102; goal 19/19; ledger rows 172/172.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.
- 覆盖：对象 51/51；初始状态 102/102；目标 19/19；证据账本行数 172/172。
- 缺陷：缺失 0；歧义 0；冲突 0；过生成 0。

Final assertion: every golden item has direct or uniquely expandable evidence, and all missing, ambiguous, contradictory, and over-generated counts are zero.

最终断言：每个黄金项都有直接证据或可唯一展开的证据，且缺失、歧义、冲突和过生成计数均为零。

# p33 audit and minimal rewrite notes

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
- Defects: missing 0; ambiguous 1; contradictory 1; over-generated 42.
- 覆盖：对象 51/51；初始状态 102/102；目标 19/19。
- 缺陷：缺失 0；歧义 1；冲突 1；过生成 42。

The ordinary inclusive reading of obj11 to obj73 suggests 63 integer labels; only 21 are golden, so 42 unsupported labels are counted as over-generated, in addition to one ambiguous range and one contradictory count.

按 obj11 到 obj73 的普通闭区间理解会得到 63 个整数标签；黄金对象仅有 21 个，因此计入 42 个过生成标签，另有 1 个歧义范围和 1 个冲突数量。

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | We have seven packages labeled from obj11 to obj73. | We have twenty-one packages: obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, obj63, obj71, obj72, and obj73. | The original count contradicts the 21 golden package objects, and the endpoint range can suggest 42 unsupported integer labels. Explicit enumeration is the smallest safe repair.<br>原文的数量与黄金 PDDL 中的 21 个包裹对象冲突，而且端点范围可能暗示 42 个不受支持的整数标签。显式列举是最小且安全的修复。 | golden_problem.pddl:8-10,15-17,23-25,30-32,37-39,44-46,52-54: package objects<br>golden_problem.pddl:57-77: (PACKAGE OBJ11) through (PACKAGE OBJ73) |

## Material deliberately preserved / 有意保留的重要文本

- All seven truck/package initial-location sentences were retained verbatim.
  - 七个卡车/包裹初始位置句均逐字保留。
- The complete indexed city membership rule was retained verbatim.
  - 完整的索引化城市隶属规则逐字保留。
- The complete irregular goal mapping was retained verbatim.
  - 完整的不规则目标映射逐字保留。

## Post-rewrite verification / 改写后验证

- Coverage: objects 51/51; init 102/102; goal 19/19; ledger rows 172/172.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.
- 覆盖：对象 51/51；初始状态 102/102；目标 19/19；证据账本行数 172/172。
- 缺陷：缺失 0；歧义 0；冲突 0；过生成 0。

Final assertion: every golden item has direct or uniquely expandable evidence, and all missing, ambiguous, contradictory, and over-generated counts are zero.

最终断言：每个黄金项都有直接证据或可唯一展开的证据，且缺失、歧义、冲突和过生成计数均为零。

# p31 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original description covers every golden object, initial atom, and goal atom, but the package phrase `obj11 to obj63` is a pseudo-range that can imply 35 nonexistent identifiers. Replacing only that span with the exact 18-name list removes the ambiguity and over-generation.

原描述覆盖了全部金标对象、初始原子和目标原子，但包裹表述 `obj11 to obj63` 是伪范围，可能暗示 35 个不存在的标识符。仅将该片段替换为准确的 18 个名称即可消除歧义和过度生成。

## Source inventory and semantic totals

| Source | Inventory |
|---|---|
| `golden_domain.pddl` | Golden Logistics predicate and action semantics; 85 lines. |
| `golden_problem.pddl` | Golden objects, initial state, and conjunctive goal; 160 lines. |
| `natural_original.txt` | Original English description audited before any decision. |

| Section | Total |
|---|---:|
| Objects | 44 |
| Init atoms, including unary type facts | 88 |
| Goal atoms | 18 |
| Semantic items | 150 |

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 18/18 |
| Missing | 0 |
| Ambiguous | 1 |
| Contradictory | 0 |
| Over-generated | 35 |

Coverage counts reflect that every golden item is mentioned; the defect is the original phrase’s additional non-golden readings.

覆盖计数表明全部金标项均被提及；缺陷在于原短语还允许额外的非金标解读。

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `obj11 to obj63` | `obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, and obj63` | The pseudo-range can be read as every integer label from 11 through 63; the explicit list is exact. / 伪范围可能被理解为 11 至 63 的所有整数标签；显式列表与金标完全一致。 | Objects: lines 8–10, 16–18, 23–25, 30–32, 37–39, 45–47; package atoms: lines 50–67. |

## Material deliberately preserved

- The opening, location ranges, airplane placement, all initial placements, all city connections, and the complete goal mapping remain verbatim because each is already semantically correct.
- 除包裹伪范围外，开头、地点范围、飞机位置、所有初始位置、城市连接及完整目标映射均逐字保留，因为这些内容已在语义上正确。

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 18/18 |
| Ledger rows | 150/150 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

The renewed atomic audit confirms that every correspondence is unique and that all deterministic rules expand to exactly the golden siblings with no unstated exception.

重新进行的逐项审计确认：每项对应关系都是唯一的，所有确定性规则都仅展开为金标同组项目，且没有未说明的例外。

**Final assertion:** missing, ambiguous, contradictory, and over-generated counts are all zero.

**最终断言：** 缺失、歧义、矛盾和过度生成计数均为零。

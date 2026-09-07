# p28 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original package pseudo-range can generate 35 identifiers absent from the golden problem, and its parallel city/position/airport ranges do not state which airport belongs to which city. Replacing the package range with the exact 18-name list and adding “same-numbered” twice resolves both defects without changing any placement or goal clause.

原描述中的包裹伪范围可能生成黄金问题中不存在的 35 个标识符，并且并列的城市、位置和机场范围没有说明每座机场属于哪座城市。把包裹范围替换为精确的 18 项名称列表，并两次加入“同编号”，即可消除两类缺陷，且不改动任何位置或目标子句。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 44 objects on lines 4–47; 88 init atoms on lines 50–137; 16 goal atoms on lines 140–155.
- `natural_original.txt`: audited original English description.
- Exact totals: objects 44; init 88; goal 16; semantic items 148.

## Before-rewrite coverage and defects

- Objects covered: 44/44
- Init atoms covered: 82/88
- Goal atoms covered: 16/16
- Missing: 0
- Ambiguous: 7 (one package pseudo-range and six airport-to-city correspondences)
- Contradictory: 0
- Over-generated: 35 non-golden package identifiers under the pseudo-range reading

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | There are packages labeled obj11 through obj63 and trucks labeled tru1 through tru6. | There are packages labeled obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, and obj63, and trucks labeled tru1 through tru6. | Replaces a pseudo-range that can imply every integer label from 11 through 63 with the exact golden package set. / 用精确的黄金包裹集合替换可能暗示 11 到 63 之间每个整数标签的伪范围。 | Package objects: `golden_problem.pddl:8–10,16–18,23–25,30–32,37–39,45–47`; package atoms: lines 50–67. |
| 2 | Each city, cit1 through cit6, has a position (pos1 through pos6) and an airport (apt1 through apt6). | Each city, cit1 through cit6, has its same-numbered position (pos1 through pos6) and its same-numbered airport (apt1 through apt6). | Adds the missing unique index correspondence; the bounded rule now yields exactly `posi` and `apti` in `citi` for `i = 1, ..., 6`. / 补充缺失的唯一索引对应关系；有界规则现在对 `i = 1, ..., 6` 恰好生成 `posi` 和 `apti` 属于 `citi`。 | Objects and types: `golden_problem.pddl:4–47,74–97`; city-membership atoms: lines 126–137. |

## Material deliberately preserved

- The opening inventory frame, truck range, both airplane placements, and original sentence order.
- All six truck/package co-location groups and all 16 explicit goals.
- Every word outside the package inventory and the two inserted correspondence modifiers.

## Post-rewrite verification

- Objects covered: 44/44
- Init atoms covered: 88/88
- Goal atoms covered: 16/16
- Evidence ledger rows: 148/148
- The same-number rule expands to exactly 12 city-membership pairs, and the package enumeration introduces no extra identifier.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

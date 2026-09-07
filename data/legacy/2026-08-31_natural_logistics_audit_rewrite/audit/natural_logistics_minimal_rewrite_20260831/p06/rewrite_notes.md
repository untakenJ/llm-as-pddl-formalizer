# p06 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original identifies every golden item, but two local spans fail the audit: the pseudo-range “from obj11 to obj33” can imply 14 non-golden package labels, and “obj33 remains at apt3” contradicts the explicit initial state that places obj33 at pos3. Replacing only those spans makes the description exact.

原文能够识别每个黄金语义项，但有两个局部片段未通过审核：“from obj11 to obj33”这一伪范围可能暗示 14 个非黄金包裹标签，而“obj33 remains at apt3”与明确将 obj33 初始放在 pos3 的状态相矛盾。仅替换这两个片段即可使描述精确。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, 16 lines.
- `natural_original.txt`: source description, 918 bytes.
- Exact totals: 22 objects; 44 init atoms; 8 goal atoms; 74 semantic items.

## Before-rewrite audit

- Object coverage: 22/22; all nine golden packages are also named later in the initial-state sentences.
- Init coverage: 44/44.
- Goal coverage: 8/8; the intended destination for obj33 is stated, but the persistence word adds a contradictory initial-state implication.
- Missing: 0.
- Ambiguous: 1 defective span.
- Contradictory: 1 defective span.
- Over-generated: 14 possible non-golden labels (`obj14`–`obj20` and `obj24`–`obj30`) under the ordinary inclusive reading of the pseudo-range.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `nine packages labeled from obj11 to obj33` | `nine packages labeled obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, and obj33` | The original pseudo-range does not uniquely construct the nine labels and can over-generate 14 labels; the replacement explicitly enumerates exactly the golden set. / 原伪范围无法唯一构造九个标签，并可能多生成 14 个标签；替换文本明确枚举且仅枚举黄金集合。 | `golden_problem.pddl:3: (:objects ... obj33 obj32 obj31 obj23 obj22 obj21 obj13 obj12 obj11)`; `golden_problem.pddl:4-5: (package obj11) ... (package obj33)`. |
| 2 | `obj33 remains at apt3` | `obj33 is moved to apt3` | “Remains” falsely implies that obj33 starts at apt3; the golden init places it at pos3 while the goal requires apt3. / “remains”错误暗示 obj33 初始位于 apt3；黄金初始状态将其置于 pos3，而目标要求 apt3。 | `golden_problem.pddl:11: (at obj33 pos3)`; `golden_problem.pddl:14-15: (at obj33 apt3)`. |

## Material text deliberately preserved

- The original sentence order, tone, punctuation, city/location mappings, vehicle inventory, and all unaffected wording were preserved.
- The three explicit initial co-location groups were preserved because they uniquely cover all truck and package positions.
- The seven unaffected goal mappings were preserved verbatim.

## Post-rewrite verification

- Object coverage: 22/22.
- Init coverage: 44/44.
- Goal coverage: 8/8.
- Evidence-ledger coverage: 74/74.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: after the two minimal span replacements, missing, ambiguous, contradictory, and over-generated counts are all zero.

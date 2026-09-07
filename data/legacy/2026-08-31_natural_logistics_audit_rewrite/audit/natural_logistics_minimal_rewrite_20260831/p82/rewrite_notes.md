# p82 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original gives exact examples for indices 1–3 and 14 but relies on “this pattern continues” and “and so forth” for the remaining objects and initial facts. It states only seven of 41 irregular goals and then implies a target for every package; it also calls all targets “new,” although two golden goals equal their initial locations. Two bounded rules, a full goal list, and two local scope/newness repairs are sufficient.
原文为索引 1–3 和 14 给出精确示例，但其余对象和初始事实依赖“该模式继续”和“等等”。原文只陈述 41 个不规则目标中的七个，随后却暗示每个包裹都有目标；它还把所有目标称为“新”地点，但两个黄金目标与其初始位置相同。两条有界规则、一份完整目标清单以及两处局部范围/新旧措辞修复即可解决问题。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics; 85 lines.
- `golden_problem.pddl`: 102 objects on lines 4–105; 204 init atoms on lines 108–311; 41 goal atoms on lines 314–354.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 347 semantic items.

## Before-rewrite coverage and defects

- Objects: 45/102; init: 80/204; goal: 7/41.
- Missing: 34 omitted irregular goal pairs.
- Ambiguous: 181 (57 object items and 124 init atoms dependent on continuation phrases rather than a complete rule).
- Contradictory: 0; over-generated: 1 (the unlisted package implied to have a goal by “Each package”).

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `This pattern continues up to packages obj141, obj142, and obj143 at location pos14 with truck tru14.` | `For every integer X from 1 through 14, truck truX and packages objX1, objX2, and objX3 are initially at posX, where X is replaced by the same decimal numeral in every identifier (so X = 10 yields tru10, obj101, obj102, obj103, and pos10).` | Defines every package/truck identifier and all 56 placements while retaining the preceding exact examples. / 定义每个包裹/卡车标识符及全部 56 个位置，同时保留前面的精确示例。 | Objects: lines 7–10, 15–18, 22–25, 29–39, 44–105; placements: `golden_problem.pddl:228–283`. |
| 2 | `Each location is associated with a specific city, so pos1 and airport apt1 are in city cit1, pos2 and airport apt2 are in city cit2, and so forth, up to pos14 and airport apt14 in city cit14.` | `For every integer X from 1 through 14, posX is a location in citX and aptX is an airport location in citX.` | Replaces `and so forth` with exact types and 28 same-index city memberships. / 用精确类型和 28 个同索引城市隶属关系替换“等等”。 | `golden_problem.pddl:164–219`, `284–311`. |
| 3 | `Our objective is to transport these packages to new destinations.` | `Our objective is for the packages listed below to reach their target destinations.` | Limits scope to the goal conjunction and accommodates goals already true initially. / 将范围限定为目标合取式，并容纳初始时已成立的目标。 | Goal scope: lines 313–355; unchanged `(AT OBJ62 POS6)` at lines 250/323 and `(AT OBJ111 POS11)` at lines 269/348. |
| 4 | `Specifically, we want obj52 at airport apt13, obj101 at airport apt10, obj42 at location apt11, obj83 at pos14, obj143 at pos11, obj91 at pos5, obj41 at apt14, and continue this relocation for all listed packages.` | `Specifically, we want obj52 at apt13; obj101 at apt10; obj42 at apt11; obj83 at pos14; obj143 at pos11; obj91 at pos5; obj41 at apt14; obj22 at apt12; obj131 at apt12; obj62 at pos6; obj71 at apt13; obj141 at apt9; obj61 at pos13; obj13 at pos3; obj82 at pos14; obj63 at pos13; obj11 at apt3; obj102 at pos14; obj123 at apt12; obj12 at apt10; obj21 at apt11; obj72 at apt2; obj122 at apt10; obj121 at pos6; obj92 at pos12; obj103 at apt3; obj43 at pos3; obj73 at pos14; obj53 at apt9; obj133 at pos10; obj23 at apt4; obj31 at pos11; obj81 at pos13; obj132 at pos2; obj111 at pos11; obj113 at pos6; obj93 at pos1; obj32 at pos10; obj142 at pos12; obj112 at apt1; and obj51 at apt14.` | Replaces seven examples and vague continuation with all 41 irregular pairs. / 用全部 41 个不规则目标对替换七个示例和模糊续写。 | `golden_problem.pddl:314–354`. |
| 5 | `Each package has a specific new target location` | `Each listed package has a specific target location` | Restricts scope to the 41 listed subjects and removes incorrect newness. / 将范围限定为列出的 41 个主体并删除不正确的“新”。 | `golden_problem.pddl:313–355`; unchanged goals at lines 323 and 348. |

## Material deliberately preserved

- The opening and exact initial placement examples for indices 1, 2, and 3.
- The complete ordered airplane-start sentence.
- Goal framing and destination classification apart from the necessary scope/newness wording.

## Post-rewrite verification

- Objects: 102/102; init: 204/204; goal: 41/41; ledger: 347/347 rows.
- X = 1…14 expands to the exact 42-package, 14-truck, 14-city, 28-location initial instance, with no extras.
- The goal sentence contains exactly 41 pairs; missing 0, ambiguous 0, contradictory 0, over-generated 0.

Every golden item has unique direct or deterministic-rule evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据或确定性规则证据，最终描述没有引入任何额外项。

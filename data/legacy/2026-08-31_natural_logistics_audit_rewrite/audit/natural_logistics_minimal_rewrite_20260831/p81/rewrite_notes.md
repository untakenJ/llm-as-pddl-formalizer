# p81 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original uses an over-generating package pseudo-range, examples and undefined correspondences for most initial facts, and only five examples for the 40 irregular goals. It also omits two airplane starts, implies goals for all 42 packages, and adds unsupported route-efficiency language. Bounded index rules, the complete goal list, and local scope/optimization edits repair those defects while preserving all unaffected wording.
原文使用会过度生成的包裹伪范围，以示例和未定义的对应关系代替大多数初始事实，并且对 40 个不规则目标只给出五个示例。原文还遗漏两个飞机初始位置，暗示全部 42 个包裹都有目标，并加入无支持的路线效率表述。有界索引规则、完整目标清单以及局部范围/优化措辞修改修复了这些缺陷，同时保留所有不受影响的文字。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics; 85 lines.
- `golden_problem.pddl`: 102 objects on lines 4–105; 204 init atoms on lines 108–311; 40 goal atoms on lines 314–353.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 346 semantic items.

## Before-rewrite coverage and defects

- Objects: 45/102; init: 52/204; goal: 5/40.
- Missing: 37 (two airplane starts and 35 goal pairs).
- Ambiguous: 207 (57 object items and 150 init atoms dependent on the pseudo-range, examples, `such as`, `various locations`, or undefined correspondence).
- Contradictory: 0.
- Over-generated: 94 (91 non-golden integer labels from `obj11` through `obj143`, two extra package goals implied by “each package,” and one efficiency objective).

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `Specifically, we have packages named obj11 through obj143, and our fleet includes trucks tru1 to tru14, and airplanes apn1 to apn4.` | `Specifically, for every integer X from 1 through 14, we have packages objX1, objX2, and objX3, where X is replaced by its decimal numeral in each identifier (so X = 10 yields obj101, obj102, and obj103); our fleet includes trucks tru1 to tru14, and airplanes apn1 to apn4.` | Replaces the pseudo-range with the exact 42-package construction; valid vehicle ranges remain. / 用精确的 42 包裹构造替换伪范围；正确的交通工具范围保持不变。 | Package objects: lines 8–10, 16–18, 23–25, 30–32, 37–39, 45–47, 52–54, 59–61, 66–68, 74–76, 81–83, 88–90, 95–97, 103–105; package types: lines 108–149. |
| 2 | `Our cities, numbered cit1 to cit14, contain specific positions and airports.` | `Our cities, numbered cit1 to cit14, each contain a position and an airport; specifically, for every integer X from 1 through 14, posX is a location in citX and aptX is an airport location in citX.` | Supplies exact location/airport identifiers, types, and all city memberships. / 补充精确的地点/机场标识符、类型和全部城市隶属关系。 | `golden_problem.pddl:164–219`, `284–311`. |
| 3 | `Trucks are stationed at positions such as pos1 in cit1 and pos2 in cit2, corresponding to the packages they need to load initially.` | `For every integer X from 1 through 14, truck truX and packages objX1, objX2, and objX3 are stationed at posX initially.` | Replaces examples and undefined correspondence with the complete finite placement rule. / 用完整的有限位置规则替换示例和未定义对应。 | `golden_problem.pddl:228–283`: 56 truck/package `AT` atoms. |
| 4 | `Airplanes, on the other hand, start at specific airports such as apn1 at apt3 in cit3 and apn2 at apt4 in cit4.` | `Airplanes, on the other hand, start at specific airports: apn1 at apt3 in cit3, apn2 at apt4 in cit4, apn3 at apt8 in cit8, and apn4 at apt4 in cit4.` | Removes `such as` and adds the two omitted starts. / 删除“例如”并补充两个遗漏位置。 | `golden_problem.pddl:224–227`. |
| 5 | First goal-introduction occurrence of `each package` | `the packages listed below` | Restricts the goal to the 40 golden goal subjects. / 将目标限定为 40 个黄金目标主体。 | `golden_problem.pddl:313–354`. |
| 6 | `The main objectives include moving obj52 to pos7, obj142 to apt4, and obj42 to pos10 among others. Each package's final destination is clearly defined, such as obj11 going to apt5 and obj123 to pos7.` | `The main objectives are to move obj52 to pos7; obj142 to apt4; obj42 to pos10; obj11 to apt5; obj123 to pos7; obj33 to pos4; obj112 to apt14; obj113 to apt8; obj61 to apt8; obj73 to apt5; obj132 to apt12; obj111 to pos11; obj103 to apt11; obj51 to apt3; obj122 to pos10; obj31 to pos7; obj72 to apt11; obj131 to apt13; obj91 to apt8; obj13 to apt11; obj41 to apt14; obj102 to pos13; obj12 to apt9; obj23 to pos12; obj83 to apt4; obj62 to apt4; obj81 to apt8; obj92 to apt13; obj43 to apt7; obj143 to pos4; obj82 to apt11; obj32 to apt13; obj133 to apt3; obj71 to pos9; obj63 to apt1; obj21 to pos1; obj93 to apt4; obj141 to pos9; obj53 to pos1; and obj101 to pos13.` | Replaces examples and `among others` with all 40 irregular pairs. / 用全部 40 个不规则目标对替换示例和“其他”。 | `golden_problem.pddl:314–353`. |
| 7 | `optimizing` | `selecting` | Removes an unsupported optimization criterion. / 删除无支持的优化标准。 | `golden_problem.pddl:313–354` has no metric. |
| 8 | Closing occurrence of `each package` | `each listed package` | Prevents two extra package goals. / 防止产生两个额外包裹目标。 | `golden_problem.pddl:313–354`. |
| 9 | `efficiently` | *(deleted)* | Removes the remaining unsupported optimization implication. / 删除剩余的无支持优化含义。 | `golden_problem.pddl:313–354` has no metric. |
| 10 | `such as trucks and airplanes` | `namely trucks and airplanes` | Closes the vehicle-mode inventory instead of suggesting unnamed modes. / 封闭交通方式清单，避免暗示未命名方式。 | Complete truck/airplane objects: `golden_problem.pddl:7,11,15,22,29,36,40,44,51,58,65,69,73,80,87,94,98,102`. |
| 11 | `various locations` | `the specified locations` | Refers the overview to the exact bounded rules rather than a vague set. / 使概述指向精确的有界规则，而非模糊集合。 | `golden_problem.pddl:178–219`: complete location/airport inventories. |

## Material deliberately preserved

- The opening challenge and initial-state overview were preserved as compatible summaries; exact rules later provide the evidence.
- The valid truck, airplane, and city ranges and the goal/planning organization were retained.
- All unaffected wording in the closing sentence was preserved.

## Post-rewrite verification

- Objects: 102/102; init: 204/204; goal: 40/40; ledger: 346/346 rows.
- X = 1…14 expands to exactly 42 packages, 14 trucks, 14 cities, 28 locations, 14 airports, 56 truck/package placements, and 28 city memberships.
- The goal sentence contains exactly the 40 golden pairs; missing 0, ambiguous 0, contradictory 0, over-generated 0.

Every golden item has unique direct or deterministic-rule evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据或确定性规则证据，最终描述没有引入任何额外项。

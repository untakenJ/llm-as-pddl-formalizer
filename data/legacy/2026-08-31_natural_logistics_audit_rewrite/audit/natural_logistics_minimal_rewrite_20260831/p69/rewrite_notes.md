# p69 Natural Logistics minimal rewrite audit

Decision: `REWRITE REQUIRED`

The original names only examples for most initial package placements and goals, uses an over-generating package pseudo-range, leaves city indexing implicit, and gives ambiguous airplane locations. The final text makes only the bounded and irregular mappings explicit that are necessary for complete recovery.

原文对大多数包裹初始位置和目标只给出示例，使用会过度生成的包裹伪范围，未明确城市索引，并含有歧义的飞机位置。最终文本只补充了实现完整恢复所必需的有界规则和不规则映射。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, preserved unchanged.
- `natural_original.txt`: original English description, preserved unchanged.
- Objects: 87/87 parsed.
- Initial-state atoms: 174/174 parsed, including every unary type fact.
- Goal atoms: 35/35 parsed.
- Total semantic items: 296.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 47/87 |
| Initial atoms covered | 63/174 |
| Goal atoms covered | 5/35 |
| Missing | 54 |
| Ambiguous/incomplete | 127 |
| Contradictory | 0 |
| Over-generated | 78 |

The over-generation count comprises 77 nongolden package identifiers implied by the literal integer pseudo-range plus one unsupported extra goal claim (all-package coverage in p69; efficiency in p70). Missing and ambiguous counts classify uncovered golden semantic items and therefore do not include those extras.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Initial setup for the logistics game includes 36 packages labeled from obj11 to obj123 and 12 trucks labeled from tru1 to tru12. | Initial setup for the logistics game includes, for each X from 1 to 12, the three packages objX1, objX2, and objX3, and includes 12 trucks labeled from tru1 to tru12. | Replaces the pseudo-range obj11 to obj123 with a bounded two-index construction while preserving the truck declaration. / 用有界的双索引构造替换 obj11 到 obj123 的伪范围，并保留卡车声明。 | `golden_problem.pddl:lines 4-90: exact object set`<br>`golden_problem.pddl:lines 93-140: (PACKAGE ...) and (TRUCK ...) facts` |
| 2 | There are also 12 cities each with a position and airport location. | There are also 12 cities labeled from cit1 to cit12, each with a position and airport location. | Adds the missing city labels while preserving the original count and city/location framing. / 补充缺失的城市标签，同时保留原有数量和城市/地点表述。 | `golden_problem.pddl:lines 141-152: (CITY CIT1) through (CITY CIT12)` |
| 3 | Every airplane (apn1, apn2, and apn3) is initially stationed at apt12 or apt7. | Every airplane (apn1, apn2, and apn3) is initially stationed as follows: apn1 and apn2 are at apt12, and apn3 is at apt7. | Resolves the ambiguous apt12-or-apt7 placement into the three exact initial airplane locations. / 将含糊的 apt12 或 apt7 表述改为三架飞机各自的确切初始位置。 | `golden_problem.pddl:line 192: (AT APN1 APT12)`<br>`golden_problem.pddl:line 193: (AT APN2 APT12)`<br>`golden_problem.pddl:line 194: (AT APN3 APT7)` |
| 4 | Each position from pos1 to pos12 is located within its corresponding city, and similarly, each airport (apt1 to apt12) is located in its respective city. | For each X from 1 to 12, posX and aptX are locations in citX, and aptX is an airport. | Defines the index correspondence, location types, airport types, and all location-to-city relations without guessing. / 明确索引对应、地点类型、机场类型和全部地点到城市关系，无需猜测。 | `golden_problem.pddl:lines 153-188: (LOCATION ...) and (AIRPORT ...) facts`<br>`golden_problem.pddl:lines 243-266: (IN-CITY ...) facts` |
| 5 | Specifically, the packages start at various locations; for example, obj11, obj12, and obj13 are at pos1, with the corresponding truck tru1. | Specifically, initially, for each X from 1 to 12, truck truX and packages objX1, objX2, and objX3 are at posX. | Replaces a vague example with the complete bounded initial mapping for all 12 trucks and 36 packages. / 用完整有界规则替换模糊示例，覆盖 12 辆卡车和 36 个包裹的初始位置。 | `golden_problem.pddl:lines 195-242: all truck and package (AT ...) facts` |
| 6 | For instance, obj81 needs to be at pos1, obj62 at pos5, obj123 at pos7, obj42 at apt12, and obj112 at apt6. | Specifically, obj81 needs to be at pos1; obj62 needs to be at pos5; obj123 needs to be at pos7; obj42 needs to be at apt12; obj112 needs to be at apt6; obj63 needs to be at apt8; obj111 needs to be at pos5; obj122 needs to be at apt5; obj72 needs to be at pos1; obj52 needs to be at apt2; obj103 needs to be at apt3; obj61 needs to be at apt5; obj21 needs to be at apt9; obj31 needs to be at apt12; obj121 needs to be at pos12; obj41 needs to be at apt10; obj51 needs to be at apt5; obj22 needs to be at pos3; obj93 needs to be at apt10; obj13 needs to be at apt5; obj71 needs to be at pos7; obj73 needs to be at pos7; obj92 needs to be at apt2; obj12 needs to be at apt6; obj83 needs to be at apt8; obj33 needs to be at pos12; obj102 needs to be at pos11; obj23 needs to be at pos12; obj11 needs to be at apt9; obj32 needs to be at apt3; obj43 needs to be at apt7; obj91 needs to be at pos5; obj53 needs to be at apt6; obj113 needs to be at pos9; obj101 needs to be at apt12. | Expands the five examples into the exact irregular 35-atom goal mapping. / 将五个示例扩展为精确的不规则 35 原子目标映射。 | `golden_problem.pddl:lines 269-303: all 35 goal atoms` |
| 7 | The comprehensive list outlines destinations for all packages ensuring proper distribution and logistics management to achieve the described end positions for each package. | These 35 package destinations must all hold simultaneously. | Removes the unsupported claim about all 36 packages and states that the 35 listed goals are simultaneous. / 删除关于全部 36 个包裹的不受支持声明，并明确列出的 35 个目标同时成立。 | `golden_problem.pddl:lines 268-304: conjunctive goal containing 35 atoms` |

## Material deliberately preserved

- The original narrative order (setup, initial state, then goal).
- The sentence “The goal is to rearrange these packages such that specific packages end up at certain locations.”
- All wording not implicated in an atomic defect.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 87/87 |
| Initial atoms covered | 174/174 |
| Goal atoms covered | 35/35 |
| Ledger rows | 296/296 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was expanded over X = 1 through 12 and checked against its complete sibling family. The final expansion introduces no identifier or atom outside the golden problem. Every irregular goal mapping was checked individually.

已将每条有界规则在 X = 1 到 12 的完整范围内展开，并与全部同族事实核对；最终展开不会引入黄金问题之外的标识符或原子。每个不规则目标映射也已逐项核对。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

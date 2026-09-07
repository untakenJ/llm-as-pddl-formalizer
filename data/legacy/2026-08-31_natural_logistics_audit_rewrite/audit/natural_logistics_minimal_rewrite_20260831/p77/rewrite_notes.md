# p77 Natural Logistics minimal rewrite audit

Decision: `REWRITE REQUIRED`

The original gives open-ended sequential examples for city and ground mappings, only three of 39 irregular goal destinations, and unsupported truck/efficiency goal language. The final English repairs only those three spans with two bounded rules and the complete goal mapping.

原文用开放式顺序示例描述城市和地面映射，只给出 39 个不规则目标中的 3 个，并加入了未受支持的卡车/效率目标措辞。最终英文仅修复这三个片段，加入两条有界规则和完整目标映射。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 95/95 parsed.
- Initial-state atoms: 190/190 parsed, including all unary type facts.
- Goal atoms: 39/39 parsed.
- Total semantic items: 324.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 75/95 |
| Initial atoms covered | 96/190 |
| Goal atoms covered | 3/39 |
| Missing | 36 |
| Ambiguous/incomplete | 114 |
| Contradictory | 0 |
| Over-generated | 14 |

The 114 ambiguous items are 20 city/position objects plus 94 init items left dependent on “continuing”/“corresponding” language. The 36 missing items are the unlisted goal mappings. The 14 over-generated requirements are 13 truck-goal implications plus the unsupported efficiency objective.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Cities and their corresponding locations include: cit1 with pos1 and apt1; cit2 with pos2 and apt2; continuing sequentially up to cit13 with pos13 and apt13. | For each X from 1 to 13, city citX has locations posX and aptX, and aptX is an airport. | Replaces an open-ended sequential example with the exact finite city/location/airport construction. / 用精确的有限城市/地点/机场构造替换开放式顺序示例。 | `golden_problem.pddl:lines 4-98: CIT/POS/APT objects`<br>`golden_problem.pddl:lines 153-204: city, location, and airport type atoms`<br>`golden_problem.pddl:lines 265-290: all (IN-CITY ...) atoms` |
| 2 | Trucks and packages have initial positions within their respective city locations; for example, tru1 and obj11 to obj13 are at pos1, tru2 and obj21 to obj23 are at pos2, this continues up to tru13 having obj131 to obj133 at pos13. | For each X from 1 to 13, truck truX and packages objX1, objX2, and objX3 are initially at posX. | Replaces examples plus “this continues” with a bounded rule for all 13 trucks and 39 packages. / 用有界规则替换示例和“继续如此”的模糊说法，覆盖 13 辆卡车和 39 个包裹。 | `golden_problem.pddl:lines 213-264: all truck/package (AT ...) atoms` |
| 3 | Our goal is to rearrange packages to specific targets: obj21 to apt3, obj62 to apt8, obj133 to apt10, and similar specific end locations for each package respectively. The remaining packages and trucks need to be arranged as follows: variously in airports, positions, or cities, as specified for each, ultimately organizing the logistics for efficient distribution. | Our goal is to rearrange packages to specific targets: obj21 must be at apt3; obj62 must be at apt8; obj133 must be at apt10; obj132 must be at apt11; obj63 must be at pos10; obj92 must be at pos12; obj93 must be at apt3; obj32 must be at apt7; obj72 must be at pos2; obj91 must be at pos9; obj43 must be at pos7; obj33 must be at pos11; obj53 must be at pos8; obj31 must be at pos12; obj113 must be at apt7; obj23 must be at pos4; obj41 must be at apt13; obj52 must be at apt10; obj103 must be at pos13; obj83 must be at apt12; obj123 must be at pos6; obj73 must be at apt11; obj122 must be at apt7; obj13 must be at apt3; obj121 must be at pos7; obj82 must be at apt2; obj11 must be at apt4; obj101 must be at apt13; obj71 must be at pos3; obj131 must be at apt4; obj42 must be at apt8; obj61 must be at pos9; obj102 must be at apt2; obj112 must be at apt11; obj12 must be at pos13; obj111 must be at pos1; obj51 must be at apt12; obj22 must be at pos1; obj81 must be at apt13. All 39 package destinations must hold simultaneously. | Replaces three examples and vague remaining goals with the exact irregular 39-atom package goal and removes unsupported truck/efficiency goals. / 用精确的不规则 39 原子包裹目标替换三个示例和模糊的剩余目标，并删除未受支持的卡车/效率目标。 | `golden_problem.pddl:lines 292-332: conjunctive 39-atom goal` |

## Material deliberately preserved

- The opening framing and exhaustive 39-package list.
- The complete truck and airplane declarations.
- All four correct airplane placements.
- The original ordering from objects through initial state to goal.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 95/95 |
| Initial atoms covered | 190/190 |
| Goal atoms covered | 39/39 |
| Ledger rows | 324/324 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded and matched against its complete golden sibling family. Every direct and irregular mapping was checked atom by atom, with no extra identifier or relation introduced.

每条有界规则均已完整展开，并与其全部黄金同族项核对；每个直接和不规则映射也已逐原子检查，未引入额外标识符或关系。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

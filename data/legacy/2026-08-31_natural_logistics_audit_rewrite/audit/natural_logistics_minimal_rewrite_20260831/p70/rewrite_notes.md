# p70 Natural Logistics minimal rewrite audit

Decision: `REWRITE REQUIRED`

The original goal list and airplane placements are correct, but its package pseudo-range, unnamed city family, and undefined “corresponding” initial mapping prevent unique recovery; its efficiency wording also adds an unsupported objective. The final text repairs only those spans.

原文的目标清单和飞机位置正确，但包裹伪范围、未命名的城市族以及未定义的“对应”初始映射妨碍唯一恢复；效率措辞还增加了 PDDL 未支持的目标。最终文本仅修复这些片段。

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
| Objects covered | 75/87 |
| Initial atoms covered | 92/174 |
| Goal atoms covered | 35/35 |
| Missing | 22 |
| Ambiguous/incomplete | 72 |
| Contradictory | 0 |
| Over-generated | 78 |

The over-generation count comprises 77 nongolden package identifiers implied by the literal integer pseudo-range plus one unsupported extra goal claim (all-package coverage in p69; efficiency in p70). Missing and ambiguous counts classify uncovered golden semantic items and therefore do not include those extras.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | The packages are labeled from obj11 to obj123, the trucks are labeled from tru1 to tru12, and the airplanes are labeled apn1, apn2, and apn3. | For each X from 1 to 12, the three packages are labeled objX1, objX2, and objX3; the trucks are labeled from tru1 to tru12; and the airplanes are labeled apn1, apn2, and apn3. | Replaces the package pseudo-range with the exact bounded construction and preserves the truck and airplane declarations. / 用精确的有界构造替换包裹伪范围，并保留卡车和飞机声明。 | `golden_problem.pddl:lines 4-90: exact object set`<br>`golden_problem.pddl:lines 93-140 and 189-191: type facts` |
| 2 | There are also twelve cities, each with two locations: a posX location and an aptX airport, where X is the city number from 1 to 12. | There are also twelve cities labeled from cit1 to cit12, each with two locations: a posX location and an aptX airport, where X is the city number from 1 to 12. | Adds the missing cit1-through-cit12 labels; the existing X rule then uniquely links posX and aptX to citX. / 补充缺失的 cit1 到 cit12 标签，使原有 X 规则能唯一关联 posX、aptX 与 citX。 | `golden_problem.pddl:lines 141-188: city, location, and airport facts`<br>`golden_problem.pddl:lines 243-266: location-to-city facts` |
| 3 | Initially, each truck is located at its corresponding posX location with three corresponding packages, and each airplane is stationed at a specific airport: apn1 is at apt11, apn2 is at apt9, and apn3 is at apt2. | Initially, for each X from 1 to 12, truX and packages objX1, objX2, and objX3 are at posX, and each airplane is stationed at a specific airport: apn1 is at apt11, apn2 is at apt9, and apn3 is at apt2. | Defines the complete truck/package suffix correspondence while preserving the already-correct airplane mapping verbatim. / 明确完整的卡车/包裹后缀对应，并逐字保留原本正确的飞机映射。 | `golden_problem.pddl:lines 192-242: all airplane, truck, and package (AT ...) facts` |
| 4 | The goal is to move the packages efficiently to these locations using the trucks and airplanes available. | All 35 listed package destinations must hold simultaneously. | Removes an unsupported efficiency objective and makes the conjunction of the 35 listed destinations explicit. / 删除 PDDL 未支持的效率目标，并明确 35 个列出目的地构成合取目标。 | `golden_problem.pddl:lines 268-304: conjunctive goal containing 35 atoms` |

## Material deliberately preserved

- The opening Logistics-game framing.
- The cit1/pos1/apt1 example.
- The exact airplane-to-airport mapping.
- The complete irregular 35-package goal sentence, unchanged verbatim.

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

# p57 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original uses the over-generating pseudo-range `obj11` through `obj103`, leaves the regular package placements and indexed city memberships non-unique, and states only six of 29 irregular goals. It also suggests city-valued package targets and an efficiency objective that do not occur in the golden PDDL. Exact finite construction rules repair the regular families, while the complete goal conjunction is enumerated.

原描述使用会过度生成标识符的伪范围 `obj11` 到 `obj103`，没有唯一确定规则性的包裹初始位置与按索引对应的城市隶属关系，并且 29 个不规则目标中只明确陈述了 6 个。原文还暗示黄金 PDDL 中不存在的以城市为包裹目标以及效率优化目标。精确的有限构造规则修复规则性事实，完整目标合取则逐项列出。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 73 objects on lines 4–76; 146 init atoms on lines 79–224; 29 goal atoms on lines 227–255.
- `natural_original.txt`: original three-paragraph English description.
- Exact totals: objects 73; init 146; goal 29; semantic items 248.

## Before-rewrite coverage and defects

- Objects covered: 72/73; `obj82` had no direct, non-over-generating occurrence.
- Init atoms covered: 98/146; 27 non-example package placements, 20 indexed city-membership atoms, and the `obj82` package typing lacked unique evidence.
- Goal atoms covered: 6/29; only the six named examples had exact destinations.
- Missing: 23 goal atoms.
- Ambiguous: 49 semantic items (one object, 28 package type/placement items, and 20 city memberships).
- Contradictory: 2 unsupported claims (city-valued package targets and efficiency optimization).
- Over-generated: 63 non-golden package identifiers under the literal integer-range reading of `obj11` through `obj103`.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `Initially, I have packages labeled obj11 through obj103 distributed in various positions.` | `For each integer i from 1 through 10, I have exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3; for example, i=1 gives obj11, obj12, and obj13, while i=10 gives obj101, obj102, and obj103.` | Replaces the pseudo-range with a bounded identifier construction that expands to exactly 30 package objects and package types. / 用有界标识符构造替换伪范围，恰好展开为 30 个包裹对象及其包裹类型。 | Package objects: `golden_problem.pddl:8–10,16–18,23–25,30–32,37–39,45–47,52–54,59–61,66–68,74–76`; `(PACKAGE ...)`: lines 79–108. |
| 2 | `I've got specific locations like pos1 to pos10 and airports from apt1 to apt10, with their corresponding city affiliations as cit1 through cit10.` | `For each integer i from 1 through 10, pos{i} and apt{i} are locations in cit{i}, and apt{i} is an airport, where every {i} is replaced by the same decimal integer.` | Removes `like` and defines every location type, airport type, and same-index city membership without guessing. / 删除 `like`，并无须猜测地定义全部地点类型、机场类型与同索引城市隶属关系。 | `(LOCATION ...)`: `golden_problem.pddl:129–148`; `(AIRPORT ...)`: lines 149–158; `(IN-CITY ...)`: lines 205–224. |
| 3 | `For the trucks, tru1 through tru10 are at pos1 through pos10 respectively, each with a few packages.` | `For each integer i from 1 through 10, tru{i} is at pos{i}, and the three packages obj{i}1, obj{i}2, and obj{i}3 are at pos{i}, where every {i} is replaced by the same decimal integer.` | Retains the valid truck mapping and supplies the previously unstated complete package mapping. / 保留正确的卡车映射并补充原先未说明的完整包裹映射。 | Truck/package placements: `golden_problem.pddl:165–204`. |
| 4 | `specific items are relocated to other designated positions` | `specific items are at their designated locations` | Avoids implying that every package moves or that airport goals are not locations. / 避免暗示每个包裹都必须移动或机场目标不是地点。 | Goal conjunction includes unchanged initial locations at lines 227, 235, and 253 and airport targets throughout lines 228–255. |
| 5 | `For instance, I want obj63 to remain at pos6, obj93 to move to apt2, and obj72 to relocate to pos8. Some packages need to change airports or positions, such as obj12 to apt10, obj92 to apt10, and obj41 to apt4. Other packages need adjustments similarly, with clear targets of either city, airport, or position outlined.` | `The complete goal is that all of the following package locations hold simultaneously: obj63 at pos6; obj93 at apt2; obj72 at pos8; obj92 at apt10; obj41 at apt4; obj73 at pos9; obj12 at apt10; obj43 at apt5; obj53 at pos5; obj11 at pos4; obj101 at pos7; obj52 at pos10; obj91 at apt4; obj81 at apt8; obj13 at pos10; obj71 at apt1; obj61 at apt2; obj33 at apt9; obj42 at pos6; obj103 at apt4; obj83 at pos2; obj23 at pos3; obj31 at apt6; obj21 at pos6; obj102 at pos6; obj22 at apt2; obj51 at pos5; obj62 at pos4; and obj32 at apt2.` | Replaces examples, vague continuation, and the unsupported city-target suggestion with all 29 irregular goal pairs as a simultaneous conjunction. / 用全部 29 个须同时成立的不规则目标对替换示例、模糊续写和无支持的城市目标暗示。 | Complete goal conjunction: `golden_problem.pddl:226–256`, with atoms on lines 227–255. |
| 6 | `meet the problem’s requirements efficiently` | `meet the problem’s requirements` | Removes an optimization implication absent from the goal and domain. / 删除目标与领域中不存在的优化含义。 | `golden_problem.pddl:226–256` contains only a conjunction and no `:metric`; `golden_domain.pddl:4–85` defines no optimization criterion. |

## Material deliberately preserved

- The opening, first-person voice, three-paragraph organization, valid truck/airplane/city ranges, and exact airplane placements.
- The correct `tru1`/`obj11`–`obj13` example and the non-semantic planning-oriented close apart from `efficiently`.
- All unaffected wording was retained verbatim.

## Post-rewrite verification

- Objects covered: 73/73.
- Init atoms covered: 146/146.
- Goal atoms covered: 29/29.
- Evidence ledger rows: 248/248.
- Expanding each rule for exactly `i = 1…10` yields 30 package names, 20 location names, 20 city memberships, 10 truck placements, and 30 package placements, with no extras.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

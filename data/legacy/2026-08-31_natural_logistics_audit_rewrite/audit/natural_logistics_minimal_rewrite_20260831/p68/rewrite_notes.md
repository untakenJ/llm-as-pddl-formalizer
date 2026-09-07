# p68 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original package pseudo-range over-generates identifiers, the initial placements rely on “similarly,” and the city mapping uses examples plus a continuation phrase instead of a complete rule. Only seven of 34 irregular goal pairs are stated, while the closing sentence adds an unsupported efficiency objective. Six localized replacements provide bounded identifier and mapping rules, enumerate the complete goal, and remove only the optimization phrase.
原文的包裹伪范围会过度生成标识符，初始位置依赖“类似地”的表述，城市映射也使用示例和续写短语，而非完整规则。34 个不规则目标对中仅陈述了七个，结尾还增加了无 PDDL 支持的效率目标。六处局部替换给出有界的标识符和映射规则、列出完整目标，并且只删除优化含义短语。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics; 85 lines.
- `golden_problem.pddl`: 87 objects on lines 4–90; 174 init atoms on lines 93–266; 34 goal atoms on lines 269–302.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 295 semantic items.

## Before-rewrite coverage and defects

- Objects: 62/87. Eleven package identifiers are explicit in examples or stated goals; the other 25 are not uniquely established by the pseudo-range. All 51 non-package objects are recoverable.
- Init: 89/174. The remaining 85 atoms depend on the package pseudo-range, “similarly,” or the example-plus-continuation city mapping.
- Goal: 7/34; 27 irregular goal pairs are missing.
- Missing: 27; ambiguous: 110 (25 object items plus 85 init atoms); contradictory: 0.
- Over-generated: 78 (77 non-golden package labels implied by the inclusive `obj11`–`obj123` pseudo-range, plus one unsupported efficiency objective).

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `In the initial setup of this logistics challenge, we have packages labeled from obj11 to obj123, which are spread across various locations.` | `In the initial setup of this logistics challenge, we have packages objX1, objX2, and objX3 for every integer X from 1 through 12, where X is replaced by its decimal numeral in each identifier (so X = 10 yields obj101, obj102, and obj103); these packages are spread across various locations.` | Replaces the 113-label inclusive pseudo-range with the exact 36-label construction while preserving the surrounding sentence. / 用精确的 36 项构造替换含 113 个标签的包含式伪范围，同时保留周边句式。 | Package objects: `golden_problem.pddl:8–10,15–17,22–24,30–32,37–39,51–53,59–61,66–68,73–75,80–82,88–90`; package types: lines 93–128. |
| 2 | `The scenario includes twelve cities, each having a position and an airport as a location.` | `The scenario includes twelve cities, cit1 through cit12; for every integer X from 1 through 12, posX and aptX are locations, and aptX is an airport in citX.` | Names every city/location and supplies exact location and airport typing. / 明确每个城市与地点，并给出精确的地点和机场类型。 | `golden_problem.pddl:141–188`: all city, location, and airport atoms. |
| 3 | `Each truck and package also begins at a specific position: for example, tru1 along with packages obj11, obj12, and obj13 are at position pos1 in city 1, tru2 with packages obj21, obj22, and obj23 are situated at position pos2 in city 2, and this pattern continues similarly for all twelve trucks and positions.` | `For every integer X from 1 through 12, truck truX and packages objX1, objX2, and objX3 begin at posX.` | Replaces two examples and “similarly” with the complete finite mapping. / 用完整的有限映射替换两个示例和“类似地”。 | `golden_problem.pddl:195–242`: all 48 truck/package initial `AT` atoms. |
| 4 | `Each position and airport location is designated to be within a specific city, such as pos1 and apt1 in city 1, pos2 and apt2 in city 2, continuing sequentially up to city 12.` | `For every integer X from 1 through 12, posX and aptX are in citX.` | Makes all 24 same-index city memberships explicit as one bounded rule. / 用一条有界规则明确全部 24 个同索引城市隶属关系。 | `golden_problem.pddl:243–266`: all 24 `IN-CITY` atoms. |
| 5 | `For instance, obj13 should remain at pos1, while obj53 needs to be relocated to the airport in city 1. We need obj21 to reach the airport in city 9, obj32 to be delivered to pos12, and similar specific targets for each package listed, including obj122 arriving at pos7, obj72 being transferred to pos2, and obj111 staying at pos11.` | `Specifically, obj13 should remain at pos1; obj53 needs to be relocated to apt1; obj21 needs to reach apt9; obj32 should be delivered to pos12; obj23 should reach apt11; obj122 should arrive at pos7; obj73 should reach pos3; obj42 should reach pos6; obj22 should reach apt2; obj81 should reach apt7; obj121 should reach pos3; obj52 should reach pos9; obj11 should reach apt8; obj72 should be transferred to pos2; obj112 should reach apt11; obj111 should stay at pos11; obj93 should reach apt7; obj63 should reach pos12; obj123 should reach pos11; obj83 should reach pos6; obj33 should reach apt10; obj12 should reach apt6; obj41 should reach pos8; obj92 should reach pos6; obj61 should reach apt2; obj91 should reach apt1; obj101 should reach apt3; obj31 should reach apt1; obj62 should reach pos11; obj82 should reach apt6; obj51 should reach pos10; obj71 should reach apt2; obj113 should reach apt2; and obj43 should reach apt1.` | Replaces examples and a vague placeholder with all 34 irregular package–destination pairs. / 用全部 34 个不规则包裹—目的地对替换示例和模糊占位语。 | `golden_problem.pddl:269–302`: complete goal conjunction. |
| 6 | `the most efficient route` | `a route` | Removes an optimization criterion absent from the golden PDDL while preserving the close. / 删除黄金 PDDL 中不存在的优化标准，同时保留结尾句。 | `golden_problem.pddl:268–303`: only a destination conjunction; no metric. |

## Material deliberately preserved

- The airplane inventory and the three initial airplane locations, whose airport-in-city references are unique under the repaired city rule.
- The goal introduction, the harmless general phrase “spread across various locations” because exact placements follow, and all other unaffected challenge-oriented wording.
- The single-paragraph organization and closing sentence apart from `the most efficient route`.

## Post-rewrite verification

- Objects: 87/87; init: 174/174; goal: 34/34; ledger: 295/295 rows.
- Expanding X over exactly 1 through 12 yields 36 packages, 12 trucks, 12 cities, 24 locations, 12 airports, 48 truck/package placements, and 24 city memberships. Multi-digit indices produce `obj101`–`obj103`, `obj111`–`obj113`, and `obj121`–`obj123`, with no integer pseudo-range expansion.
- The explicit goal sentence contains exactly the 34 golden pairs and requires no analogy or unstated continuation.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has unique direct or deterministic-rule evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据或确定性规则证据，最终描述没有引入任何额外项。

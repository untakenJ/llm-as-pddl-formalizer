# p27 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original falsely says that each city has six packages and uses the pseudo-range `obj11` to `obj63`, which can generate 35 non-golden identifiers. It also never types `apt1`, `apt3`, `apt5`, or `apt6` as airports. One sentence replacement and one short bounded type rule repair those defects; all placements, city mappings, and goals remain verbatim.

原描述错误地声称每座城市有六个包裹，并使用从 `obj11` 到 `obj63` 的伪范围，可能生成 35 个非黄金标识符。此外，原文从未把 `apt1`、`apt3`、`apt5` 或 `apt6` 标为机场。替换一个句子并增加一条简短的有界类型规则即可修复这些缺陷；所有位置、城市映射和目标均保持原样。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 44 objects on lines 4–47; 88 init atoms on lines 50–137; 16 goal atoms on lines 140–155.
- `natural_original.txt`: audited original English description.
- Exact totals: objects 44; init 88; goal 16; semantic items 148.

## Before-rewrite coverage and defects

- Objects covered: 44/44
- Init atoms covered: 84/88
- Goal atoms covered: 16/16
- Missing: 4 (`(airport apt1)`, `(airport apt3)`, `(airport apt5)`, and `(airport apt6)`)
- Ambiguous: 0
- Contradictory: 1
- Over-generated: 35 non-golden package identifiers under the pseudo-range reading

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Initially, we have six packages in each city, numbered from obj11 to obj63. | Initially, we have 18 packages labeled obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, and obj63. | Corrects the false per-city count and replaces the pseudo-range with exactly the 18 golden package identifiers. / 更正错误的每城数量，并用恰好 18 个黄金包裹标识符替换伪范围。 | Package objects: `golden_problem.pddl:8–10,16–18,23–25,30–32,37–39,45–47`; package type atoms: lines 50–67. |
| 2 | No sentence after the six-city location mapping. | The locations apt1 through apt6 are airports. | Adds the four missing airport type facts through a bounded range that expands to exactly all six golden airport atoms; apt2 and apt4 were already directly typed. / 通过恰好展开为六个黄金机场原子的有界范围补充四个缺失类型事实；apt2 和 apt4 原本已有直接类型证据。 | `golden_problem.pddl:92–97`: `(airport apt1)` through `(airport apt6)`. |

## Material deliberately preserved

- The six exact truck/package co-location clauses and both airplane placements.
- The explicit city-to-`pos`/`apt` mapping and all 16 irregular goal pairs.
- The single-paragraph organization and all unaffected wording.

## Post-rewrite verification

- Objects covered: 44/44
- Init atoms covered: 88/88
- Goal atoms covered: 16/16
- Evidence ledger rows: 148/148
- The package list contains exactly 18 names; `apt1` through `apt6` expands to exactly the six golden airports.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

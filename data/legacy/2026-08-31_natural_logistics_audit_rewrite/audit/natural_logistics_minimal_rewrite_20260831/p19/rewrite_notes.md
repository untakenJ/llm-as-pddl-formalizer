# p19 audit and rewrite notes

Decision: `REWRITE REQUIRED`

The original description uniquely states all objects, types, vehicle/package placements, airplane placements, and goals, but it never links `pos1` to `cit1` or airports `apt2`, `apt3`, and `apt4` to their cities. One bounded index rule supplies exactly those missing facts while also making the already described regular family explicit. All original sentences remain verbatim.

原描述唯一地说明了全部对象、类型、运输工具/包裹位置、飞机位置和目标，但没有将 `pos1` 归入 `cit1`，也没有将机场 `apt2`、`apt3`、`apt4` 分别归入其城市。新增的一条有界索引规则恰好补足这些缺失事实，并把原本已部分描述的规则族明确化。所有原句均逐字保留。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics.
- `golden_problem.pddl`: 37 objects on line 3; 74 init atoms on lines 4–19; 14 goal atoms on lines 20–23.
- `natural_original.txt`: one-line original description.
- Exact semantic-item total: 37 + 74 + 14 = 125.

## Before-rewrite coverage

- Objects: 37/37.
- Init atoms: 70/74.
- Goal atoms: 14/14.
- Missing: 4 — `(in-city pos1 cit1)`, `(in-city apt2 cit2)`, `(in-city apt3 cit3)`, and `(in-city apt4 cit4)`.
- Ambiguous: 0; contradictory: 0; over-generated: 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | No sentence between `...with truck tru5.` and `We also have two airplanes...` | `For each index i from 1 through 5, position posi and airport apti are locations in city citi, where i is replaced by that index in all three identifiers.` | Adds one finite deterministic rule. Expanding `i = 1, 2, 3, 4, 5` generates exactly the ten golden `in-city` pairs, as well as the stated location/airport/city types, with no extra identifier or relation. / 新增一条有限确定规则；展开 `i = 1, 2, 3, 4, 5` 后恰好生成十个黄金 `in-city` 对，同时给出地点/机场/城市类型，不产生额外标识符或关系。 | Objects: line 3; types: lines 8–11; exact `in-city` family: lines 16–19. |

## Material deliberately preserved

- Every original sentence and the single-paragraph tone were preserved verbatim.
- All five ground co-location clauses and both airplane placements were preserved.
- The complete 14-item goal clause and closing sentence were preserved.

## Post-rewrite verification

- Objects: 37/37; init atoms: 74/74; goal atoms: 14/14.
- Rule expansion: `i=1..5` yields `pos1..pos5`, `apt1..apt5`, `cit1..cit5`, and exactly the ten golden position/airport city-membership atoms.
- Atomic ledger: 125/125 semantic items, one row per item.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Final assertion: after the single bounded-rule insertion, every golden object and atom has unique natural-language evidence and all four defect counts are zero.

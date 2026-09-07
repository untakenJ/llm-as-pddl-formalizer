# p11 audit and rewrite notes

Decision: `REWRITE REQUIRED`

The original names the relevant positions and apt locations, but its generic opening does not map each apt identifier to the airport type, and it never states that the apt identifiers have the separate location type required by the golden problem. One inserted bounded sentence resolves all seven unsupported type facts.
原文列出了相关位置和 apt 地点，但其笼统开头没有将每个 apt 标识符映射到机场类型，也从未说明这些 apt 标识符还具有黄金问题要求的独立地点类型。插入一个有界句子即可解决全部七个缺乏支持的类型事实。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics; 85 lines.
- `golden_problem.pddl`: 29 objects, 58 init atoms, and 11 goal atoms; 98 semantic items total.
- `natural_original.txt`: original one-line English description.

## Before-rewrite coverage and defects

- Objects covered: 29/29.
- Init atoms covered: 51/58.
- Goal atoms covered: 11/11.
- Missing: 0.
- Ambiguous/incomplete: 7: `(location apt1)` through `(location apt4)`, plus `(airport apt1)`, `(airport apt2)`, and `(airport apt4)`.
- Contradictory: 0.
- Over-generated: 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | *(no text; insertion after the city-membership mapping)* | `The positions pos1 through pos4 and the airports apt1 through apt4 are all locations.` | Explicitly types every apt object as an airport and every pos/apt object as a location using two exact four-item ranges. / 用两个精确的四项范围，明确将每个 apt 对象标为机场，并将每个 pos/apt 对象标为地点。 | Location atoms: `golden_problem.pddl:8-9`; airport atoms: `golden_problem.pddl:9-10`. |

## Material deliberately preserved

- All package and truck type/location statements and the complete city-membership mapping were preserved verbatim.
- The airplane statement and all eleven irregular goal pairs were preserved verbatim because they already match the golden problem exactly.

## Post-rewrite verification

- Objects covered: 29/29.
- Init atoms covered: 58/58.
- Goal atoms covered: 11/11.
- Evidence ledger: 98/98 semantic items.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has direct or uniquely expandable deterministic evidence, and the final description introduces no extra object, atom, or goal.
每个黄金项都有直接证据或可唯一展开的确定性证据，最终描述没有引入额外对象、原子或目标。


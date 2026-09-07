# p04 audit and rewrite notes

## Decision

`NO REWRITE REQUIRED`

The original description uniquely enumerates the nine packages, three position/airport pairs and their cities, all vehicles and initial locations, and all seven irregular goal mappings. “Initial positions” and the named airports are unambiguous natural-language locations, so every golden location type fact is directly recoverable without an added convention.

原始描述唯一地列出了九个包裹、三组位置/机场及其所属城市、全部运输工具及其初始地点，以及全部七个不规则目标映射。“初始位置”和文中点名的机场在自然语言中都是无歧义的地点，因此无需补充约定即可直接恢复黄金文件中的每个地点类型事实。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 22 objects on line 3; 44 init atoms on lines 4–13; 7 goal atoms on lines 14–15.
- `natural_original.txt`: one complete English description; preserved byte-for-byte in `natural_rewritten.txt`.
- Exact totals: objects 22; init 44; goal 7; semantic items 73.

## Before-rewrite coverage

- Objects: 22/22 covered.
- Init atoms: 44/44 covered.
- Goal atoms: 7/7 covered.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte identical to the original. | The original already passes full atomic coverage and uniqueness checks. / 原文已经通过完整的逐项覆盖与唯一对应检查。 | `golden_problem.pddl:3–15` contains exactly the objects, init atoms, and goals stated in the description. |

## Material deliberately preserved

- “Three packages at each of three initial positions” and the following explicit lists, because together they identify exactly nine package objects and their initial locations.
- The truck list, because it uniquely states all three truck objects and their initial positions.
- The airport/city sentence, because it explicitly pairs each airport with one city and locates the sole airplane.
- The seven-item objective sentence, because every irregular package-destination pair is stated explicitly.
- All wording and paragraph structure, because no semantic repair was needed.

## Post-rewrite verification

- Objects: 22/22 covered.
- Init atoms: 44/44 covered.
- Goal atoms: 7/7 covered.
- Evidence-ledger rows: 73/73 semantic items.
- Every correspondence is unique; finite list expansion introduces no extra item.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

# p20 audit and rewrite notes

Decision: `NO REWRITE REQUIRED`

The original description explicitly inventories every package, truck, airplane, and city; gives an exhaustive position/airport-to-city mapping; uniquely states all 22 vehicle/package placements; and enumerates all 15 goal atoms. The correspondence sentence refers back to an already explicit mapping and does not require guessing. No rewrite is needed, so the final English text is preserved byte-for-byte.

原描述明确列出了每个包裹、卡车、飞机和城市，给出了完整的位置/机场到城市映射，唯一地说明了全部 22 个运输工具/包裹初始位置，并逐项列出了全部 15 个目标原子。“corresponding cities”句明确回指前一句已经给出的映射，无需猜测。因此无需改写，最终英文文本按字节原样保留。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics.
- `golden_problem.pddl`: 37 objects on line 3; 74 init atoms on lines 4–19; 15 goal atoms on lines 20–23.
- `natural_original.txt`: one-line original description.
- Exact semantic-item total: 37 + 74 + 15 = 126.

## Before-rewrite coverage

- Objects: 37/37.
- Init atoms: 74/74.
- Goal atoms: 15/15.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of the original. | The exact inventories, mappings, placements, and goals already satisfy the atomic audit. / 精确的清单、映射、初始位置和目标已经满足逐原子审计。 | Objects: line 3; init: lines 4–19; goal: lines 20–23. |

## Material deliberately preserved

- The explicit inventories of 15 packages, five trucks, two airplanes, and five cities were preserved.
- The five exact `posN`/`aptN`–`citN` mappings and grouped initial placements were preserved.
- The complete 15-item goal list was preserved verbatim.

## Post-rewrite verification

- Objects: 37/37; init atoms: 74/74; goal atoms: 15/15.
- Atomic ledger: 126/126 semantic items, one row per item.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Final assertion: every golden object and atom has unique natural-language evidence, and all four defect counts are zero.

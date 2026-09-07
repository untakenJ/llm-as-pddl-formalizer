# p61 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original directly supplies all 80 golden objects, all 160 initial atoms, and all 31 goal atoms, but its package-label pseudo-range `obj11` to `obj113` also denotes 70 non-golden integer labels under a literal range reading. Replacing only that clause with a bounded concatenation rule removes the over-generation; all other wording remains verbatim.

原描述直接提供了全部 80 个黄金对象、160 个初始原子和 31 个目标原子，但若按字面整数范围理解，包裹标签伪范围 `obj11` 到 `obj113` 还会表示 70 个非黄金标签。仅将该分句替换为有界连接规则即可消除过度生成；其余文字均逐字保留。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 80 objects on lines 4–83; 160 init atoms on lines 86–245; 31 goal atoms on lines 248–278.
- `natural_original.txt`: original one-paragraph English description.
- Exact totals: objects 80; init 160; goal 31; semantic items 271.

## Before-rewrite coverage and defects

- Objects covered: 80/80; every golden package is also named in the complete initial-placement list.
- Init atoms covered: 160/160.
- Goal atoms covered: 31/31.
- Missing: 0; ambiguous: 0; contradictory: 0.
- Over-generated: 70 non-golden package identifiers under the literal integer-range reading of `obj11` through `obj113`.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `Initially, we have packages labeled from obj11 to obj113, eleven trucks from tru1 to tru11, and cities from cit1 to cit11.` | `Initially, for each integer i from 1 through 11, we have exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3; we also have eleven trucks from tru1 to tru11 and cities from cit1 to cit11.` | Replaces only the over-generating package pseudo-range with a finite rule that expands to exactly the 33 golden package labels. / 仅以有限规则替换会过度生成的包裹伪范围，恰好展开为 33 个黄金包裹标签。 | Package objects: `golden_problem.pddl:8–10,15–17,23–25,30–32,37–39,44–46,52–54,59–61,66–68,73–75,81–83`; `(PACKAGE ...)`: lines 86–118. |

## Material deliberately preserved

- The opening, one-paragraph organization, valid truck/city/location/airport/airplane inventories, and exact airplane placements.
- The complete truck/package initial-location enumeration and all 22 location-to-city relations.
- All 31 irregular goal destinations and every word outside the single defective object-range sentence.

## Post-rewrite verification

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 31/31.
- Evidence ledger rows: 271/271.
- Expanding the package rule for exactly `i = 1…11` and final digits `1`, `2`, and `3` yields exactly 33 package names and no extra name.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

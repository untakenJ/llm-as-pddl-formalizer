# p22 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original contains malformed `city]-1` and `city]-2` placeholders, so the complete location, airport, city-membership, and truck-location families cannot be uniquely expanded. It also says that the packages are in “different places,” although package3 and package4 are both initially at city1-1. Three sentence-local repairs remove these defects while preserving every unaffected sentence.

原文包含格式错误的 `city]-1` 和 `city]-2` 占位符，因此无法唯一展开完整的地点、机场、城市隶属关系和卡车位置系列。原文还称包裹位于“不同地点”，但 package3 与 package4 初始时都位于 city1-1。三处句内局部修订消除了这些缺陷，并保留了所有未受影响的句子。

## Source inventory

- `golden_domain.pddl`: logistics predicates and action semantics.
- `golden_problem.pddl`: 32 objects, 64 init atoms, and 6 goal atoms (102 semantic items total).
- `natural_original.txt`: audited original English description.
- `natural_rewritten.txt`: minimally repaired English description.

## Before-rewrite coverage and defects

- Objects covered: 28/32
- Init atoms covered: 32/64
- Goal atoms covered: 6/6
- Missing: 6 (the six `(location cityN-2)` type facts were not stated)
- Ambiguous: 30 (four location objects and 26 init atoms depended on malformed or non-unique correspondence wording)
- Contradictory: 1 (the “different places” claim conflicts with the co-location of package3 and package4)
- Over-generated: 0

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | There are six packages, named package1 through package6, and each is located in different places across six cities, labeled city1 through city6. | There are six packages, named package1 through package6, and six cities, labeled city1 through city6. | Removes the unsupported implication that the six packages occupy different places while preserving the package and city inventories. / 删除六个包裹位于不同地点这一无依据的含义，同时保留包裹和城市清单。 | `golden_problem.pddl:68: (at package4 city1-1)`; `golden_problem.pddl:69: (at package3 city1-1)`. |
| 2 | Each city has a distinct location labeled city]-1 and an airport labeled city]-2 (for example, city1-1 and city1-2 for city1). | For each N from 1 through 6, cityN has a distinct location cityN-1 and an airport location cityN-2 (for example, city1-1 and city1-2 for city1). | Replaces malformed placeholders with a bounded index rule and states that every airport is also a location. / 用有界索引规则替换错误占位符，并明确每个机场同时也是地点。 | Objects: `golden_problem.pddl:3-7`; `(location city6-1)` through `(location city1-1)`: lines 28-33; `(airport city6-2)` and `(location city6-2)` through the city1 counterparts: lines 34-45; all `(in-city ...)` atoms: lines 46-57. |
| 3 | The trucks are initially located at their corresponding city]-1 locations, and both airplanes are initially stationed at city4-2. | For each N from 1 through 6, truckN is initially located at cityN-1, and both airplanes are initially stationed at city4-2. | Makes the finite truck-to-location correspondence explicit and uniquely expandable. / 明确有限的卡车到地点对应关系，使其可唯一展开。 | `golden_problem.pddl:60: (at truck6 city6-1)` through `golden_problem.pddl:65: (at truck1 city1-1)`. |

## Material deliberately preserved

- The opening setup phrase, package/truck/airplane naming style, and overall single-paragraph organization were retained.
- The exact airplane initial locations, all six package initial locations, and all six goal mappings were preserved verbatim because they already match `golden_problem.pddl:58-59,66-77`.
- The city1 example was preserved as an illustration after the complete bounded rule; it no longer substitutes for missing evidence.

## Post-rewrite verification

- Objects covered: 32/32
- Init atoms covered: 64/64
- Goal atoms covered: 6/6
- Evidence ledger rows: 102/102
- Expanding each `N = 1, 2, 3, 4, 5, 6` rule yields exactly the golden location, airport, city-membership, and truck-location items and no others.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

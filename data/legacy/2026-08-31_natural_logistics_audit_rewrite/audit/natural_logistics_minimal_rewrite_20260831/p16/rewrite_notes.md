# p16 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original is complete except for two local semantic defects. “Holding packages” expresses truck containment instead of the golden package-at-location atoms, and “within a specific city” lists cities without defining the location-to-city correspondence. Two phrase-level substitutions make both relations unique while preserving every unaffected word.

除两处局部语义缺陷外，原始描述是完整的。“holding packages”表达包裹在卡车内，而不是黄金文件中的包裹位于地点原子；“within a specific city”虽然列出了城市，却未定义地点与城市的对应关系。两处短语级替换使这两类关系都变得唯一，同时保留所有未受影响的文字。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines; `(at ?obj ?loc)` and `(in ?obj ?obj)` are distinct predicates at lines 13-14.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, 24 lines.
- `natural_original.txt`: source natural-language description.
- Exact totals: 37 objects; 74 init atoms; 13 goal atoms; 124 semantic items.

## Before-rewrite audit

- Object coverage: 37/37.
- Init coverage: 61/74.
- Goal coverage: 13/13.
- Missing: 0.
- Ambiguous: 10 (the ten golden `in-city` atoms lack a stated city-index correspondence).
- Contradictory: 3 (the three obj3* package placements are described as truck containment rather than package-at-pos3 facts).
- Over-generated: 3 (the phrase “holding packages” implies three absent initial `(in obj3* tru3)` atoms).

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `holding packages obj31, obj32, and obj33` | `along with packages obj31, obj32, and obj33` | Replaces containment wording with unambiguous co-location wording. / 用明确的同位置措辞替换表示装载关系的措辞。 | `golden_problem.pddl:14`: `(at obj31 pos3)`, `(at obj32 pos3)`, `(at obj33 pos3)`; `golden_domain.pddl:13-14`: `at` and `in` are distinct predicates. |
| 2 | `within a specific city (cit1, cit2, cit3, cit4, cit5)` | `within its same-numbered city (cit1, cit2, cit3, cit4, cit5)` | Adds the missing finite index correspondence: for each i from 1 through 5, posi and apti are in citi. / 补充缺失的有限索引对应关系：对 1 至 5 的每个 i，posi 和 apti 都在 citi 中。 | `golden_problem.pddl:16-19`: `(in-city pos1 cit1)`, `(in-city apt1 cit1)`, `(in-city pos2 cit2)`, `(in-city apt2 cit2)`, `(in-city pos3 cit3)`, `(in-city apt3 cit3)`, `(in-city pos4 cit4)`, `(in-city apt4 cit4)`, `(in-city pos5 cit5)`, `(in-city apt5 cit5)`. |

## Material text deliberately preserved

- All object inventories and unary-type wording were preserved.
- Both airplane placements and the other four truck/package co-location clauses were preserved.
- The order, identifiers, and grouping in the city sentence were preserved; only the correspondence phrase changed.
- The complete thirteen-item goal sentence was preserved verbatim.

## Post-rewrite verification

- Object coverage: 37/37.
- Init coverage: 74/74.
- Goal coverage: 13/13.
- Evidence-ledger coverage: 124/124.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: after the two phrase-level repairs, missing, ambiguous, contradictory, and over-generated counts are all zero.

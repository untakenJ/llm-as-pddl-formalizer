# p18 audit and rewrite notes

Decision: `REWRITE REQUIRED`

The original names only `apn1` and `apn2` but calls them three airplanes, uses an imprecise city/location inventory whose “each containing … such as” scope can be read as non-golden cross-city membership, and says the three `obj5*` packages are being carried by `tru5` instead of locating them at `pos5`. Three local phrase substitutions remove those defects without changing the organization, mappings, or goals.

原文只列出 `apn1` 和 `apn2`，却称其为三架飞机；城市/地点清单中“each containing … such as”的作用域不精确，可能被解读为黄金 PDDL 中不存在的跨城市归属；原文还称三个 `obj5*` 包裹由 `tru5` 装载，而不是明确将它们置于 `pos5`。三处局部短语替换消除了这些缺陷，同时保留了原有组织、映射和目标。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics; `(in ?obj ?obj)` on line 14 distinguishes loaded cargo from co-location represented by `(at ...)`.
- `golden_problem.pddl`: 37 objects on line 3; 74 init atoms on lines 4–19; 14 goal atoms on lines 20–23.
- `natural_original.txt`: four-paragraph original description.
- Exact semantic-item total: 37 + 74 + 14 = 125.

## Before-rewrite coverage

- Objects: 37/37.
- Init atoms: 71/74; the three golden `(at obj51 pos5)`, `(at obj52 pos5)`, and `(at obj53 pos5)` atoms were not uniquely stated by “carrying.”
- Goal atoms: 14/14.
- Missing: 0; ambiguous: 4 (the city/location scope plus three package placements); contradictory: 1 (three airplanes versus the two golden airplanes); over-generated: 4 (one unnamed extra airplane and three implied loaded-cargo relations).

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `three airplanes named apn1 and apn2` | `two airplanes named apn1 and apn2` | Repairs the numerical contradiction while preserving the named objects. / 修复数量矛盾并保留原有对象名称。 | Object list: line 3 (`apn2 apn1`); airplane type facts: lines 11–12 (`(airplane apn1)`, `(airplane apn2)`). |
| 2 | `each containing locations such as` | `along with locations` | Converts an ambiguous per-city example construction into a neutral exact inventory; the next paragraph retains the explicit one-to-one city mapping. / 将含糊的逐城市举例结构改为中性的精确清单，下一段仍保留明确的一一城市映射。 | Location types: lines 8–10; exact `in-city` pairs: lines 16–19. |
| 3 | `carrying obj51, obj52, and obj53` | `with packages obj51, obj52, and obj53` | States co-location at `pos5` and avoids inventing `(in obj5* tru5)` cargo atoms. / 明确包裹与卡车同处 `pos5`，避免虚构 `(in obj5* tru5)` 装载原子。 | Lines 15–16: `(at tru5 pos5)`, `(at obj51 pos5)`, `(at obj52 pos5)`, `(at obj53 pos5)`; no `(in ...)` init atoms occur. |

## Material deliberately preserved

- All object names and the four-paragraph structure were preserved.
- Both airplane placements at `apt2` and all five exact city mappings were preserved.
- The complete 14-item goal description was preserved verbatim.

## Post-rewrite verification

- Objects: 37/37; init atoms: 74/74; goal atoms: 14/14.
- Atomic ledger: 125/125 semantic items, one row per item.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Final assertion: after the three minimal substitutions, every golden object and atom has unique natural-language evidence and all four defect counts are zero.

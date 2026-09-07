# p47 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The object lists and relational mappings are complete, but the opening sentence says there are only nine packages and only nine locations. The golden problem has 27 packages and 18 location-typed objects (nine positions plus the nine airports). Two local count repairs remove the contradictions and directly support every location type fact; all other wording remains unchanged.  
对象列表和关系映射均完整，但开头句称只有九个包裹和九个地点。黄金问题实际包含 27 个包裹和 18 个具有地点类型的对象（九个普通位置加九个机场）。两处局部数量修正消除了矛盾，并直接支持每个地点类型事实；其余文字均保持不变。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics (85 lines).
- `golden_problem.pddl`: 66 objects, 132 init atoms, and 25 goal atoms (223 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 66/66; init 123/132; goal 25/25.
- Defects: missing 0; ambiguous 9 (the nine `(location aptX)` facts were not directly recoverable from the stated nine-location count); contradictory 2 (package count and location count); over-generated 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| 1 | `nine packages` | `twenty-seven packages` | Correct the contradicted package count while preserving the explicit package list. / 修正与黄金问题矛盾的包裹数量，同时保留明确清单。 | Package objects: lines 9–11, 16–18, 23–25, 30–32, 38–40, 45–47, 52–54, 59–61, 67–69; `(PACKAGE ...)`: lines 72–98. |
| 2 | `nine locations, nine airports` | `eighteen locations (the nine positions and nine airports)` | State that all nine airports are also among the 18 location-typed objects. / 明确九个机场也属于 18 个地点类型对象。 | Position and airport objects: lines 5–6, 12–13, 19–20, 26–27, 34–35, 41–42, 48–49, 55–56, 63–64; `(LOCATION ...)`: lines 117–134; `(AIRPORT ...)`: lines 135–143. |

## Material deliberately preserved

- The exhaustive package list and bounded truck/city/location identifiers were preserved because they already match all golden objects.
- The airplane mapping, every truck/package initial-location mapping, and the `posX`/`aptX` to `citX` rule were preserved because each is complete and unique.
- The complete irregular goal sentence and all surrounding prose were preserved verbatim.

## Post-rewrite verification

- Coverage: objects 66/66; init 132/132; goal 25/25; ledger 223/223 rows.
- The ranges were expanded for X=1 through X=9: 9 trucks, 9 cities, 18 locations, 9 airports, and exactly 18 `in-city` atoms, with no extra identifier or relation.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

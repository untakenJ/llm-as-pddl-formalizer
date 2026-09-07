# p48 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The goal and airplane locations are complete, but the original phrase “corresponding vehicles and packages” neither names the full package/truck inventory nor defines their initial-location correspondence. It also leaves most location-to-city mappings non-unique. Replacing that one sentence with a finite X=1..9 construction supplies exactly the missing object, type, initial-location, and city-membership evidence.  
目标和飞机位置已经完整，但原文“对应的车辆和包裹”既未给出完整的包裹/卡车清单，也未定义其初始位置对应关系，并且使大多数地点到城市的映射不唯一。仅用一个有限的 X=1..9 构造规则替换该句，即可精确补足缺失的对象、类型、初始位置和城市隶属证据。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics (85 lines).
- `golden_problem.pddl`: 66 objects, 132 init atoms, and 25 goal atoms (223 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 57/66; init 79/132; goal 25/25.
- Defects: missing 18 (9 unnamed objects and their 9 unary type facts); ambiguous 44 (28 unspecified truck/package initial positions and 16 non-unique location-to-city facts); contradictory 0; over-generated 0.
- The six explicitly named packages, tru1/tru2, all goal pairs, and all three airplane locations were credited; the vague word “corresponding” was not expanded by guesswork.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| 1 | `Each city from cit1 to cit9 has a position and an airport location (apt1 to apt9) with corresponding vehicles and packages.` | `For each integer X from 1 through 9, citX is a city, posX and aptX are locations in citX, aptX is an airport, truX is a truck, and objX1, objX2, and objX3 are packages; initially, truX and those three packages are at posX.` | Replace an undefined correspondence with one bounded construction whose substitutions are explicit. / 用一个替换范围和对应关系均明确的有限构造替代未定义的“对应”。 | Object families: lines 4–69; unary facts: lines 72–146; truck/package positions: lines 150–185; city memberships: lines 186–203. |

## Material deliberately preserved

- The introductory sentence and the explicit cit1/cit2 examples were preserved because they are compatible with and illustrate the repaired rule.
- The airplane sentence was preserved because its ordered `respectively` mapping exactly matches lines 147–149.
- All six goal sentences were preserved verbatim because together they enumerate exactly the 25 goal atoms at lines 206–230.

## Post-rewrite verification

- Coverage: objects 66/66; init 132/132; goal 25/25; ledger 223/223 rows.
- Expanding X=1 through X=9 yields exactly 9 cities, 18 locations, 9 airports, 9 trucks, 27 packages, 18 `in-city` atoms, 9 truck-position atoms, and 27 package-position atoms. The airplane sentence adds exactly 3 airplanes and 3 airplane-position atoms.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

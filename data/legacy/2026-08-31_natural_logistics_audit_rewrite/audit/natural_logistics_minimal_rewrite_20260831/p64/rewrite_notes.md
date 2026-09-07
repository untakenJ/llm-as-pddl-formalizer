# p64 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original names all golden objects and goals, but its package pseudo-range over-generates identifiers; its city, airport, truck, and package patterns do not uniquely define 54 initial atoms; and several phrases imply non-golden facts. Seven local sentence or phrase repairs supply exact finite rules, state co-location rather than containment in a truck, and remove the false `remain`/`stay` implications while preserving the complete goal list and overall format.

原描述提到了全部黄金对象和目标，但包裹伪范围会过度生成标识符；城市、机场、卡车和包裹的模式没有唯一确定 54 个初始原子；另有若干短语暗示非黄金事实。七处局部句子或短语修订补充精确有限规则，明确包裹与卡车同处地点而非装在卡车中，并删除错误的 `remain`/`stay` 含义，同时保留完整目标列表和整体格式。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines), including distinct `at` and `in` predicates on lines 13–14.
- `golden_problem.pddl`: 80 objects on lines 4–83; 160 init atoms on lines 86–245; 33 goal atoms on lines 248–280.
- `natural_original.txt`: original multi-paragraph, bulleted English description.
- Exact totals: objects 80; init 160; goal 33; semantic items 273.

## Before-rewrite coverage and defects

- Objects covered: 80/80; all 33 actual package labels also occur in the complete goal list.
- Init atoms covered: 106/160.
- Goal atoms covered: 33/33; the two false continuity words still identify their intended goal locations.
- Missing: 0.
- Ambiguous: 51 init atoms: 32 middle-group package/truck placements and 19 unstated same-index city memberships.
- Contradictory: 7 defects: the three `obj2*` package placements are described as truck containment rather than package-at-`pos2` facts, plus the one-airplane-per-city claim, unspecified airport proximity, `obj83` already remaining at `pos3`, and `obj82` already staying at `apt4`.
- Over-generated: 73 items: 70 non-golden package identifiers under the literal integer-range reading of `obj11` through `obj113`, plus three absent initial `(in obj2* tru2)` atoms implied by `holds packages`.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `Initially, we have packages labeled obj11 through obj113, a total of 33 packages.` | `Initially, for each integer i from 1 through 11, we have exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3, for a total of 33 packages.` | Replaces the pseudo-range with a bounded construction that yields exactly 33 labels. / 用恰好生成 33 个标签的有界构造替换伪范围。 | Package objects: `golden_problem.pddl:8–10,15–17,23–25,30–32,37–39,44–46,52–54,59–61,66–68,73–75,81–83`; package types: lines 86–118. |
| 2 | `Each city has an airport location, apt1 through apt11, and contains one airplane: apn1 is at apt3, apn2 is at apt2, and apn3 is at apt11.` | `For each integer i from 1 through 11, the city labeled by concatenating cit and i contains the two locations labeled by concatenating pos and i and by concatenating apt and i, and the apt location is an airport; the three airplanes are apn1 at apt3, apn2 at apt2, and apn3 at apt11.` | Defines the same-index city/location mapping and airport types, and corrects the one-airplane-per-city implication while preserving all three placements. / 定义同索引城市地点映射和机场类型，并纠正每城一架飞机的暗示，同时保留三架飞机的位置。 | Cities/locations/airplanes: `golden_problem.pddl:4–83`; `(LOCATION ...)`: lines 141–162; `(AIRPORT ...)`: lines 163–173; `(AIRPLANE ...)` and airplane placements: lines 174–179; `(IN-CITY ...)`: lines 224–245. |
| 3 | `- In city cit1, located at pos1, we have truck tru1 with packages obj11, obj12, and obj13.` | `- In city cit1, truck tru1 and packages obj11, obj12, and obj13 are initially at pos1.` | Makes all four co-location atoms direct without implying containment. / 直接表述四个同地点原子，不暗示装载关系。 | `(AT TRU1 POS1)` and `(AT OBJ11/OBJ12/OBJ13 POS1)`: `golden_problem.pddl:180–183`. |
| 4 | `- In city cit2, at pos2, truck tru2 holds packages obj21, obj22, and obj23.` | `- In city cit2, truck tru2 and packages obj21, obj22, and obj23 are initially at pos2.` | Replaces non-golden in-truck containment with the four golden `at` atoms. / 用四个黄金 `at` 原子替换非黄金的车内装载关系。 | `(AT TRU2 POS2)` and `(AT OBJ21/OBJ22/OBJ23 POS2)`: `golden_problem.pddl:184–187`; `golden_domain.pddl:13–14` distinguishes `at` from `in`. |
| 5 | `- Similarly, the pattern continues across the cities up to city cit11 where truck tru11 is at pos11 with packages obj111, obj112, and obj113. Each city's airport is nearby, but initially, our focus is on the packages at different positions.` | `- For each integer i from 3 through 11, the truck labeled by concatenating tru and i and the three packages labeled by concatenating obj, i, and one of 1, 2, or 3 are initially at the position labeled by concatenating pos and i.` | Replaces an undefined continuation and unsupported proximity relation with the exact remaining 36 placements. / 用精确的其余 36 个位置关系替换未定义的续写和无支持的邻近关系。 | Truck/package placements for indices 3–11: `golden_problem.pddl:188–223`. |
| 6 | `obj83 should remain at pos3 along with obj33` | `obj83 should be at pos3 along with obj33` | Removes the false implication that `obj83` initially occupies its goal; `obj33` genuinely does. / 删除 `obj83` 初始即在目标位置的错误暗示；`obj33` 的确如此。 | Initial `(AT OBJ83 POS8)`: `golden_problem.pddl:211`; goals `(AT OBJ83 POS3)` and `(AT OBJ33 POS3)`: lines 267–268. |
| 7 | `obj82 should stay at apt4` | `obj82 should be at apt4` | Removes the false implication that `obj82` initially occupies `apt4`. / 删除 `obj82` 初始即在 `apt4` 的错误暗示。 | Initial `(AT OBJ82 POS8)`: `golden_problem.pddl:210`; goal `(AT OBJ82 APT4)`: line 275. |

## Material deliberately preserved

- The first-person voice, multi-paragraph bullet layout, opening and closing, and valid truck/city/location ranges.
- Every correct airplane placement and every one of the 33 explicitly stated goal destinations.
- All goal wording except the two continuity words that contradicted the golden initial state.

## Post-rewrite verification

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 33/33.
- Evidence ledger rows: 273/273.
- The package rule yields 33 names; the city/location rule yields 22 memberships and 11 airport types; the placement rules yield all 44 truck/package `at` atoms, with no extras.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

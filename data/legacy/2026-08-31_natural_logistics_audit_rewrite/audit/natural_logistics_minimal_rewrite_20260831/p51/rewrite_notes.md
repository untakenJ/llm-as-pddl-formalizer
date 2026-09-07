# p51 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original package pseudo-range can denote 56 nonexistent integer labels, the weakening word “various” does not establish all nine trucks, and “and so forth” leaves six truck positions and 21 package positions without a unique expansion. It also fails to state unambiguously that every airport is a location and describes the last three packages as contained in tru9. Replacing only the three defective sentences with bounded X=1..9 rules repairs those families while preserving every correct airplane, city-membership, and goal statement.  
原文中的包裹伪范围可能表示 56 个不存在的整数标签；弱化词“various”不能确定全部九辆卡车；“and so forth”也无法唯一展开六辆卡车和 21 个包裹的初始位置。此外，原文没有明确说明每个机场也是地点，并把最后三个包裹描述为装在 tru9 中。仅将这三处有缺陷的句子替换为 X=1..9 的有限规则，即可修复这些事实族，同时保留所有正确的飞机位置、城市隶属关系和目标陈述。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics (85 lines; predicate `(in ?obj ?obj)` at line 14 distinguishes containment from `(at ?obj ?loc)` at line 13).
- `golden_problem.pddl`: 66 objects, 132 init atoms, and 27 goal atoms (225 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 60/66; init 90/132; goal 27/27.
- Defects: missing 0; ambiguous 48; contradictory 0; over-generated 115.
- The 48 non-unique golden items are six truck objects, six truck type facts, nine airport `LOCATION` facts, six truck-position atoms, and 21 package-position atoms. The pseudo-range `obj11` to `obj93` suggests 56 extra object labels and 56 extra `PACKAGE` atoms; “tru9 ... containing” additionally suggests three non-golden `IN` atoms.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| 1 | `Packages are labeled from obj11 to obj93, with various trucks from tru1 to tru9, and cities from cit1 to cit9.` | `Packages are labeled objX1, objX2, and objX3 for each integer X from 1 through 9, with trucks tru1 through tru9 and cities cit1 through cit9.` | Replace the over-generating package pseudo-range and weakened truck inventory with exact bounded constructions; keep the correct city range. / 用精确的有限构造替换会过度生成的包裹伪范围和被弱化的卡车清单，并保留正确的城市范围。 | Package objects: lines 9–11, 16–18, 23–25, 30–32, 38–40, 45–47, 52–54, 59–61, 67–69; truck/city objects: lines 7–8, 14–15, 21–22, 28–29, 36–37, 43–44, 50–51, 57–58, 65–66; `(PACKAGE ...)`: lines 72–98; `(TRUCK ...)`: lines 99–107; `(CITY ...)`: lines 108–116. |
| 2 | `Each city contains specific locations, named as pos1 to pos9, and airports apt1 to apt9, with apt1 to apt9 designated as airports containing airplanes apn1 to apn3.` | `The locations are pos1 through pos9 and apt1 through apt9, with apt1 through apt9 designated as airports and apn1 through apn3 designated as airplanes.` | State the two exact location families and their types without implying that the airplanes are contained in the airports. / 明确两个地点族及其类型，且不再暗示飞机被装在机场中。 | Location/airport/airplane objects: lines 4–6, 12–13, 19–20, 26–27, 33–35, 41–42, 48–49, 55–56, 62–64; `(LOCATION ...)`: lines 117–134; `(AIRPORT ...)`: lines 135–143; `(AIRPLANE ...)`: lines 144–146. |
| 3 | `Trucks and packages are placed at the corresponding positions: tru1 is at pos1 with packages obj11, obj12, and obj13; tru2 is at pos2 with obj21, obj22, and obj23, and so forth up to tru9 at pos9 containing obj91, obj92, and obj93.` | `Trucks and packages are placed at the corresponding positions: for each integer X from 1 through 9, truX and packages objX1, objX2, and objX3 are at posX.` | Replace the prohibited vague continuation and containment wording with one finite same-index rule for all trucks and packages. / 用一个覆盖全部卡车和包裹的有限同索引规则替换被禁止的模糊续写和包含关系措辞。 | Truck/package initial positions: lines 150–185, exactly `(AT TRU1 POS1)` through `(AT TRU9 POS9)` and the three same-prefix package atoms at each position. |

## Material deliberately preserved

- The opening sentence was preserved because its broad inventory categories are compatible with the exact repaired inventories.
- The airplane-location sentence was preserved verbatim because it exactly supplies `(AT APN1 APT9)`, `(AT APN2 APT4)`, and `(AT APN3 APT9)` at lines 147–149.
- The bounded `respectively` city-membership sentence was preserved because it expands to exactly the 18 `(IN-CITY ...)` atoms at lines 186–203.
- The complete irregular goal sentence was preserved verbatim because it directly enumerates all 27 goal atoms at lines 206–232.

## Post-rewrite verification

- Coverage: objects 66/66; init 132/132; goal 27/27; ledger 225/225 rows.
- Expanding X=1 through X=9 yields exactly 27 packages, nine trucks, nine cities, 18 locations, nine airports, nine truck-position atoms, and 27 package-position atoms. The separate airplane and `respectively` sentences yield exactly three airplane positions and 18 city-membership atoms.
- The renewed item-by-item ledger check found no unstated exception, alternative correspondence, extra identifier, or extra relation.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

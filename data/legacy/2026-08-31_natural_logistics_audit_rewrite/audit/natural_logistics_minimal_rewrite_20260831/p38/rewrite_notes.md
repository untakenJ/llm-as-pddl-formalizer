# p38 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The goals and explicitly listed facts are correct, but “and so forth” and “continues similarly” do not uniquely recover the middle location, city-membership, truck-location, and package-location facts. Three local replacements supply finite index bounds and exact identifier construction.

目标和明确列出的事实均正确，但“等等”和“以此类推”无法唯一恢复中间各地点、城市隶属、卡车位置与包裹位置事实。三处局部替换补充了有限索引范围及精确标识符构造规则。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics.
- `golden_problem.pddl`: 51 objects (lines 3–55), 102 init atoms (lines 56–159), and 21 goal atoms (lines 160–182).
- `natural_original.txt`: original one-paragraph English description.
- Semantic total: **174** items.

## Before-rewrite coverage and defects

- Objects: **43/51** covered; eight middle position/airport identifiers depended on vague continuation.
- Init: **70/102** covered; 32 middle type, location, or city-membership atoms depended on vague continuation.
- Goal: **21/21** covered.
- Missing: **0**; ambiguous: **40**; contradictory: **0**; over-generated: **0**.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `each city has a position and an airport respective to them, such as pos1 and apt1 for cit1, and so forth up to pos7 and apt7 for cit7` | `for every integer i from 1 through 7, city citi has position posi and airport apti, where citi, posi, and apti denote the prefixes cit, pos, and apt followed by the same integer i` | Replaces an example plus vague continuation with a bounded, uniquely expandable construction. / 用有界且可唯一展开的构造规则替代示例和模糊续写。 | `golden_problem.pddl:85–112` (city/location/airport types) and `golden_problem.pddl:145–158` (same-index city memberships) |
| 2 | `This pattern continues similarly for all trucks, packages, and positions up to tru7 at pos7 with packages obj71, obj72, and obj73.` | `For each integer i from 4 through 6, truck trui and packages obji1, obji2, and obji3 are at posi, where identifiers are formed by appending i to tru and pos and by placing i between obj and each suffix 1, 2, or 3; tru7 is at pos7 with packages obj71, obj72, and obj73.` | Gives the previously omitted middle groups an exact range and preserves the explicit index-7 endpoint. / 为此前省略的中间组提供精确范围，并保留明确的第 7 组。 | `golden_problem.pddl:129–144: (AT TRU4 POS4)…(AT OBJ73 POS7)` |
| 3 | `pos1 and apt1 lie in cit1, pos2 and apt2 are in cit2, and so forth up to pos7 and apt7 in cit7` | `for every integer i from 1 through 7, posi and apti lie in citi, where posi, apti, and citi denote the prefixes pos, apt, and cit followed by the same integer i` | Makes all 14 `IN-CITY` correspondences exact and finite. / 使全部 14 个 `IN-CITY` 对应关系精确且有限。 | `golden_problem.pddl:145–158: (IN-CITY POS1 CIT1)…(IN-CITY APT7 CIT7)` |

## Material deliberately preserved

- All package, vehicle, city, airplane-start, and goal wording was preserved because every explicitly stated item was correct.
- The explicit starting groups for indices 1–3 and 7 were preserved.
- The original paragraph structure and tone were preserved.

## Post-rewrite verification

- Objects: **51/51**; init: **102/102**; goal: **21/21**.
- Atomic evidence ledger: **174/174** rows covered. Each rule row was expanded against every in-range index and introduced no sibling or identifier outside the golden set.
- Missing: **0**; ambiguous: **0**; contradictory: **0**; over-generated: **0**.

Final assertion: every correspondence is unique and the rewritten description exactly recovers the golden problem.

# p25 audit and rewrite notes

## Decision

`REWRITE REQUIRED`

The original description contradicts five golden truck placements by extending a first-location pattern across trucks that are actually at their cities' second locations, and it omits package4's initial location. Replacing only that truck-assignment bullet and adding one package bullet repairs all six atoms and preserves every unaffected sentence.

原描述把“位于第一个地点”的模式延伸到实际位于各自城市第二个地点的五辆卡车，因此与五个黄金卡车位置相矛盾；同时还遗漏了 package4 的初始位置。仅替换该卡车分配条目并增加一个包裹条目，即可修复全部六个原子，并保留所有未受影响的句子。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 83 objects on lines 3–13; 166 init atoms on lines 14–179; 7 goal atoms on lines 180–186.
- `natural_original.txt`: audited original English description.
- Exact totals: objects 83; init 166; goal 7; semantic items 256.

## Before-rewrite coverage and defects

- Objects covered: 83/83
- Init atoms covered: 160/166
- Goal atoms covered: 7/7
- Missing: 1
- Ambiguous: 0
- Contradictory: 5
- Over-generated: 5

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Truck assignments: truck14 is at the first location in city14, truck13 at the first location in city13, continuing similarly down to truck1 at the first location in city1. | Truck assignments: trucks truck14, truck13, truck12, truck11, truck10, truck7, truck5, truck2, and truck1 are at the first location in their same-numbered cities, while trucks truck9, truck8, truck6, truck4, and truck3 are at the second location in their same-numbered cities. | The original continuation generates five false first-location atoms and contradicts the five golden second-location atoms. The replacement exhaustively partitions all 14 trucks and preserves the same-number correspondence. / 原有延续规则会生成五个错误的第一地点原子，并与五个黄金第二地点原子矛盾。修订后穷尽划分全部 14 辆卡车，并保留同编号对应关系。 | `golden_problem.pddl:157–170`; exceptions are `(at truck9 city9-2)` at line 162, `(at truck8 city8-2)` at 163, `(at truck6 city6-2)` at 165, `(at truck4 city4-2)` at 167, and `(at truck3 city3-2)` at 168. |
| 2 | No sentence between the package5/package2 bullet and the package3 bullet. | Package4 is situated at the first location in city8. | Adds the one missing initial package-location atom without changing any existing package wording. / 补充唯一缺失的初始包裹—地点原子，且不改动任何既有包裹措辞。 | `golden_problem.pddl:176: (at package4 city8-1)`. |

## Material deliberately preserved

- The object inventory and three-location city rule, because they uniquely expand to all 83 objects and all type/city-membership atoms.
- All four airplane placements, the eight already-stated package placements, and all seven goal mappings, because they already match the golden atoms.
- The paragraph order, bullet structure, tone, and every non-truck phrase.

## Post-rewrite verification

- Objects covered: 83/83
- Init atoms covered: 166/166
- Goal atoms covered: 7/7
- Evidence ledger rows: 256/256
- The two explicit truck groups expand to all and only the 14 golden truck-location atoms.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

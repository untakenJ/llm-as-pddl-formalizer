# p42 minimal-rewrite audit

## Decision

`REWRITE REQUIRED`

## Finding / 结论

The original description was not atomically recoverable: its package continuation and location-to-city distribution were vague, the airplane pairing lacked an explicit ordered correspondence, and its closing sentence added unsupported all-package and efficiency objectives. Four local sentence replacements repair these defects without changing the complete goal list or unaffected setup.

原始描述无法逐项唯一还原：包裹续写和地点到城市的分布表述含糊，飞机配对缺少明确的有序对应，结尾还加入了不受支持的“所有包裹”和效率目标。四处局部句子替换修复了这些问题，同时保留完整目标列表和其他设置。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics.
- `golden_problem.pddl`: 58 objects, 116 init atoms, and 23 goal atoms.
- `natural_original.txt`: original English description audited before the decision.
- Semantic-item total: 197.

## Before-rewrite coverage

| Measure | Count |
|---|---:|
| Objects covered | 43/58 |
| Init atoms covered | 69/116 |
| Goal atoms covered | 23/23 |
| Missing | 1 |
| Ambiguous | 61 |
| Contradictory | 0 |
| Over-generated | 2 |

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | This pattern continues up to city cit8, where packages obj81, obj82, and obj83 are located at pos8. | This pattern applies to every index i from 1 through 8: for each such i, where i is replaced by the same index in every identifier, the three packages obji1, obji2, and obji3 are initially at posi. | The vague continuation did not uniquely enumerate package groups 3–7 or their initial positions. The bounded substitution rule expands to exactly obji1–obji3 at posi for i=1…8. / 原有模糊续写无法唯一枚举第 3–7 组包裹及其初始位置；有界替换规则恰好展开为 i=1…8 时 obji1–obji3 位于 posi。 | `golden_problem.pddl:8-10,15-17,22-24,30-32,37-39,44-46,51-53,59-61 (all OBJ objects)`<br>`golden_problem.pddl:64-87 ((PACKAGE OBJ11) through (PACKAGE OBJ83))`<br>`golden_problem.pddl:133-163 (all package AT atoms)` |
| 2 | Airplanes apn1 and apn2 are at airports apt8 and apt7. | Airplanes apn1 and apn2 are at airports apt8 and apt7, respectively. | Without “respectively,” the two airplanes could not be uniquely paired with the two airports. / 缺少“分别”时，两架飞机与两个机场之间无法唯一配对。 | `golden_problem.pddl:130: (AT APN1 APT8)`<br>`golden_problem.pddl:131: (AT APN2 APT7)` |
| 3 | The locations pos1 to pos8, along with apt1 to apt8, are distributed among the cities cit1 to cit8. | For every index i from 1 through 8, where i is replaced by the same index in every identifier, posi and apti are locations in city citi, apti is an airport, and citi is a city. | “Distributed among” did not define the index correspondence, and apt3 was not otherwise explicitly typed as an airport. The replacement supplies the exact finite location, airport, city, and in-city rule. / “分布于”没有定义索引对应关系，且 apt3 在其他地方未被明确标为机场；替换文本给出了精确有限的地点、机场、城市及隶属城市规则。 | `golden_problem.pddl:96-103 ((CITY CIT1) through (CITY CIT8))`<br>`golden_problem.pddl:104-119 ((LOCATION POS1)/(LOCATION APT1) through (LOCATION POS8)/(LOCATION APT8))`<br>`golden_problem.pddl:120-127 ((AIRPORT APT1) through (AIRPORT APT8))`<br>`golden_problem.pddl:164-179 ((IN-CITY POS1 CIT1)/(IN-CITY APT1 CIT1) through index 8)` |
| 4 | The objective is to move all packages to their respective destinations efficiently. | All 23 listed destination conditions must hold simultaneously. | “All packages” implied an unlisted destination for obj42, and “efficiently” added an optimization objective absent from the conjunctive PDDL goal. The replacement states only the 23 listed conjuncts. / “所有包裹”暗示 obj42 还有未列出的目的地，而“高效地”增加了 PDDL 合取目标中不存在的优化目标；替换文本只要求列出的 23 个合取条件。 | `golden_problem.pddl:182-204 (the complete 23-atom goal; no OBJ42 goal atom and no optimization metric)` |

## Material deliberately preserved

- The opening setup and examples for city groups 1 and 2.
- The truck range and ordered location correspondence.
- The complete 23-pair goal enumeration.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 58/58 |
| Init atoms covered | 116/116 |
| Goal atoms covered | 23/23 |
| Ledger rows | 197/197 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Final assertion: every golden object, init atom, and goal atom has unique direct or deterministic-rule evidence in `natural_rewritten.txt`; deterministic rules expand to exactly the golden items, with zero omissions, ambiguity, contradictions, or over-generation.

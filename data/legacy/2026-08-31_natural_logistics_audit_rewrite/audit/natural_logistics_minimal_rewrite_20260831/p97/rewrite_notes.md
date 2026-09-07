# p97 Natural Logistics minimal rewrite audit

Decision: `REWRITE REQUIRED`

The original fully covers all objects, initial placements, location-to-city facts, and goals, but identifies only city1-2 as an airport. A single local addition supplies the two missing airport type facts.

原文完整覆盖所有对象、初始位置、地点到城市事实和目标，但只将 city1-2 标识为机场。一次局部补充即可加入另外两个缺失的机场类型事实。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 26/26 parsed.
- Initial-state atoms: 52/52 parsed, including all unary type facts.
- Goal atoms: 7/7 parsed.
- Total semantic items: 85.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 26/26 |
| Initial atoms covered | 50/52 |
| Goal atoms covered | 7/7 |
| Missing | 2 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

The only uncovered golden items are (AIRPORT CITY2-2) and (AIRPORT CITY3-2); all other semantic items are directly supported.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Each city has distinct locations, with city1 having locations city1-1 and city1-2, city2 having city2-1 and city2-2, and city3 containing city3-1 and city3-2. | Each city has distinct locations, with city1 having locations city1-1 and city1-2, city2 having city2-1 and city2-2, and city3 containing city3-1 and city3-2; city1-2, city2-2, and city3-2 are the airports. | Adds only the two missing airport classifications while retaining the complete city/location enumeration. / 仅补充两个缺失的机场分类，并保留完整的城市/地点枚举。 | `golden_problem.pddl:line 30: (AIRPORT CITY3-2)`<br>`golden_problem.pddl:line 32: (AIRPORT CITY2-2)`<br>`golden_problem.pddl:line 34: (AIRPORT CITY1-2)` |

## Material deliberately preserved

- All package, city, vehicle, and location declarations.
- Every initial vehicle and package placement.
- The complete seven-package goal sentence, verbatim.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 26/26 |
| Initial atoms covered | 52/52 |
| Goal atoms covered | 7/7 |
| Ledger rows | 85/85 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every finite rule was expanded against its complete golden family, and every direct mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有限规则均已对照完整黄金集合展开，每个直接映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

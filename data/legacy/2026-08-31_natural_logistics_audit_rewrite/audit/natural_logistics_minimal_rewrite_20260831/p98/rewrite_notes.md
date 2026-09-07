# p98 Natural Logistics minimal rewrite audit

Decision: `REWRITE REQUIRED`

The original contains every golden object and atom, but “locations such as” implies unspecified extra locations and its final sentence adds an unsupported efficiency objective. Two local repairs remove only those extras.

原文包含全部黄金对象和原子，但“例如这些地点”暗示未指定的额外地点，最后一句还加入未受支持的效率目标。两处局部修复只删除这些额外含义。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 42/42 parsed.
- Initial-state atoms: 84/84 parsed, including all unary type facts.
- Goal atoms: 6/6 parsed.
- Total semantic items: 132.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 42/42 |
| Initial atoms covered | 84/84 |
| Goal atoms covered | 6/6 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 2 |

All golden semantic items are already covered. The two defects are over-generated implications: an open-ended location inventory and an efficiency objective absent from the PDDL.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Each city contains specific locations that may serve as destinations for the packages: locations such as cityX-1, cityX-2 for standard locations, and cityX-3 for airports, where 'X' corresponds to the city number. | Each city contains specific locations that may serve as destinations for the packages: locations cityX-1 and cityX-2, and the airport cityX-3, where 'X' corresponds to the city number. | Removes the open-ended “such as” wording and states the exact three-location suffix schema. / 删除开放式的“例如”措辞，并明确精确的三地点后缀模式。 | `golden_problem.pddl:lines 6-8: exact location objects`<br>`golden_problem.pddl:lines 36-70: location, airport, and in-city atoms` |
| 2 | Our task is to use the available vehicles to achieve these delivery goals efficiently. | All six listed package destinations must hold simultaneously. | Removes the unsupported efficiency objective and explicitly states the six-way goal conjunction. / 删除未受支持的效率目标，并明确六个目标同时成立。 | `golden_problem.pddl:lines 93-98: conjunctive six-atom goal` |

## Material deliberately preserved

- All object and vehicle declarations.
- Every initial airplane, truck, and package mapping.
- The complete six-package goal sentence, verbatim.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 42/42 |
| Initial atoms covered | 84/84 |
| Goal atoms covered | 6/6 |
| Ledger rows | 132/132 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every finite rule was expanded against its complete golden family, and every direct mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有限规则均已对照完整黄金集合展开，每个直接映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

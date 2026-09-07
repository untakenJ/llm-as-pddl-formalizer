# p78 Natural Logistics minimal rewrite audit

Decision: `REWRITE REQUIRED`

The original fully identifies the objects, city structure, airplane placement, and goals, but “carrying” contradicts the golden co-location facts and “Similarly ... with packages” can inherit that containment reading. Two local sentence repairs make both package groups explicitly co-located.

原文完整识别了对象、城市结构、飞机位置和目标，但“承载”与黄金同地点事实矛盾，而“同样……与包裹一起”可能继承该包含关系解读。两处局部句子修复使两组包裹都明确为同地点。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 15/15 parsed.
- Initial-state atoms: 30/30 parsed, including all unary type facts.
- Goal atoms: 6/6 parsed.
- Total semantic items: 51.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 15/15 |
| Initial atoms covered | 24/30 |
| Goal atoms covered | 6/6 |
| Missing | 0 |
| Ambiguous/incomplete | 3 |
| Contradictory | 3 |
| Over-generated | 3 |

The six uncovered init atoms are the package co-location facts: three contradicted by “carrying” and three left ambiguous by “Similarly ... with packages.” The three over-generated items are the implied (IN package tru1) containment atoms.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Truck tru1 is located at pos1 in cit1, carrying packages obj11, obj12, and obj13. | Truck tru1 is located at pos1 in cit1, and packages obj11, obj12, and obj13 are also at pos1. | Replaces “carrying” with explicit co-location; the golden init has AT facts and no IN facts for these packages. / 用明确的同地点表述替换“承载”；黄金初始状态含 AT 事实而不含这些包裹的 IN 事实。 | `golden_problem.pddl:lines 7-8: (AT TRU1 POS1) and package (AT ... POS1) atoms`<br>`golden_domain.pddl:line 14: (in ?obj ?obj) is the containment predicate` |
| 2 | Similarly, truck tru2 is located at pos2 in cit2 with packages obj21, obj22, and obj23. | Similarly, truck tru2 is located at pos2 in cit2, and packages obj21, obj22, and obj23 are also at pos2. | Makes the second truck/package relationship explicitly co-located rather than inheriting the preceding carrying interpretation. / 明确第二组卡车和包裹是同地点关系，避免继承前句的承载含义。 | `golden_problem.pddl:lines 8-9: (AT TRU2 POS2) and package (AT ... POS2) atoms` |

## Material deliberately preserved

- All object/type declarations and both city/location descriptions.
- The correct airplane placement.
- The complete six-package goal sentence, verbatim.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 15/15 |
| Initial atoms covered | 30/30 |
| Goal atoms covered | 6/6 |
| Ledger rows | 51/51 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded and matched against its complete golden sibling family. Every direct and irregular mapping was checked atom by atom, with no extra identifier or relation introduced.

每条有界规则均已完整展开，并与其全部黄金同族项核对；每个直接和不规则映射也已逐原子检查，未引入额外标识符或关系。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

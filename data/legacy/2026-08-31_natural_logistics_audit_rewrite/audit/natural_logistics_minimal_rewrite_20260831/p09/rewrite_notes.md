# p09 audit and rewrite notes

Decision: `REWRITE REQUIRED`

The original gives the wrong package total (“nine”) and uses the unsafe pseudo-range “obj11 through obj43,” whose ordinary integer expansion introduces 21 nonexistent identifiers. Replacing that one span with the correct total and explicit package list is sufficient; all other object, initial-state, and goal evidence is already complete.
原文给出了错误的包裹总数（“九个”），并使用了不安全的伪范围“obj11 through obj43”；按通常的整数范围展开会引入 21 个不存在的标识符。只需将这一处替换为正确总数和完整包裹列表；其他对象、初始状态和目标证据已经完整。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics; 85 lines.
- `golden_problem.pddl`: 29 objects, 58 init atoms, and 10 goal atoms; 97 semantic items total.
- `natural_original.txt`: original one-line English description.

## Before-rewrite coverage and defects

- Objects covered: 29/29.
- Init atoms covered: 58/58.
- Goal atoms covered: 10/10.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 1 false cardinality claim.
- Over-generated: 42 semantic items: the literal 33-name expansion of `obj11` through `obj43` adds 21 nonexistent objects and 21 corresponding package facts.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `nine packages named obj11 through obj43` | `twelve packages named obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, and obj43` | Corrects the false count and replaces an over-generating pseudo-range with the exact finite set. / 更正错误总数，并用精确有限集合替换会过度生成的伪范围。 | Objects: `golden_problem.pddl:3`; package atoms: `golden_problem.pddl:4-6`. |

## Material deliberately preserved

- The introductory framing and sentence order were preserved because they add no conflicting semantics.
- All truck, city, location, airport, airplane, initial-location, city-membership, and goal wording was preserved verbatim because it already expands uniquely to the golden facts.

## Post-rewrite verification

- Objects covered: 29/29.
- Init atoms covered: 58/58.
- Goal atoms covered: 10/10.
- Evidence ledger: 97/97 semantic items.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has direct or uniquely expandable deterministic evidence, and the final description introduces no extra object, atom, or goal.
每个黄金项都有直接证据或可唯一展开的确定性证据，最终描述没有引入额外对象、原子或目标。


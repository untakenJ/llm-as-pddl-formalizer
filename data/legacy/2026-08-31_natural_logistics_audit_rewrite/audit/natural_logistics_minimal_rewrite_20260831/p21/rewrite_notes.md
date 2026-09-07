# p21 audit and rewrite notes

## Decision

`NO REWRITE REQUIRED`

The original description directly enumerates every irregular initial and goal mapping and uses only finite, unambiguous ranges where compression is safe. It matches the golden PDDL without omission, contradiction, ambiguity, or over-generation.

原描述直接列出了每个不规则的初始映射和目标映射，仅在可安全压缩之处使用有限且无歧义的范围。它与黄金 PDDL 完全一致，不存在遗漏、矛盾、歧义或过度生成。

## Source inventory

- `golden_domain.pddl`: logistics predicates and action semantics.
- `golden_problem.pddl`: 37 objects, 74 init atoms, and 15 goal atoms (126 semantic items total).
- `natural_original.txt`: audited original English description.
- `natural_rewritten.txt`: byte-for-byte copy of `natural_original.txt`.

## Before-rewrite coverage and defects

- Objects covered: 37/37
- Init atoms covered: 74/74
- Goal atoms covered: 15/15
- Missing: 0
- Ambiguous: 0
- Contradictory: 0
- Over-generated: 0

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | The original already provides unique evidence for every object, init atom, and conjunctive goal atom. / 原文已为每个对象、初始原子和合取目标原子提供唯一证据。 | Objects: `golden_problem.pddl:3`; init: `golden_problem.pddl:4-19`; goal: `golden_problem.pddl:20-23`. |

## Material deliberately preserved

- The complete original description was preserved verbatim because all package, vehicle, city, location, airport, initial-position, city-membership, and goal statements are complete and mutually consistent.
- The compact range “apt1 through apt5” was preserved because its finite endpoints uniquely expand to exactly the five airport objects and atoms.

## Post-rewrite verification

- Objects covered: 37/37
- Init atoms covered: 74/74
- Goal atoms covered: 15/15
- Evidence ledger rows: 126/126
- Every correspondence is unique; all deterministic ranges were fully expanded and checked.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

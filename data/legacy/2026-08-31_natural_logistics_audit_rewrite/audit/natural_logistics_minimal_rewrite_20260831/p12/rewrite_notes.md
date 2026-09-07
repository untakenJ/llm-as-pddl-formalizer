# p12 audit and rewrite notes

Decision: `REWRITE REQUIRED`

The pronoun “These” grammatically attributes city membership to three packages instead of to pos1, leaving `(in-city pos1 cit1)` unsupported and suggesting three extra relations. The two airports are also never explicitly identified as locations. Changing the pronoun phrase and adding one bounded sentence repairs only those defects.
代词“These”在语法上把城市隶属关系赋给三个包裹，而不是 pos1，因此 `(in-city pos1 cit1)` 缺乏支持并暗示三个额外关系。此外，两个机场从未被明确说明为地点。修改该代词短语并增加一个有界句子即可仅修复这些缺陷。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics; 85 lines.
- `golden_problem.pddl`: 15 objects, 30 init atoms, and 4 goal atoms; 49 semantic items total.
- `natural_original.txt`: original one-line English description.

## Before-rewrite coverage and defects

- Objects covered: 15/15.
- Init atoms covered: 27/30.
- Goal atoms covered: 4/4.
- Missing: 1 (`(in-city pos1 cit1)`).
- Ambiguous/incomplete: 2 (`(location apt1)` and `(location apt2)`).
- Contradictory: 0.
- Over-generated: 3 package–city relations suggested by “These are part of city cit1.”

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `These are part of city cit1.` | `Position pos1 is part of city cit1.` | Replaces the package-referring pronoun with the exact location, supplying the required city relation and removing three extra implications. / 用确切地点替换指向包裹的代词，补充所需城市关系并消除三个额外暗示。 | `golden_problem.pddl:9`: `(in-city pos1 cit1)`. |
| 2 | *(no text; insertion after the airport/airplane sentence)* | `Both airports are locations.` | The immediately preceding sentence defines exactly two airports, apt1 and apt2, so this bounded rule supplies exactly their two location facts. / 紧邻前句明确列出 apt1 和 apt2 两个机场，因此该有界规则恰好补充它们的两个地点事实。 | `golden_problem.pddl:6`: `(location apt1)`, `(location apt2)`. |

## Material deliberately preserved

- All package, truck, airport, airplane, and initial-location wording outside the changed pronoun was preserved verbatim.
- The pos2/cit2 relation and both airport/city relations were preserved because their correspondences are direct and unique.
- The complete four-pair goal and closing sentence were preserved verbatim.

## Post-rewrite verification

- Objects covered: 15/15.
- Init atoms covered: 30/30.
- Goal atoms covered: 4/4.
- Evidence ledger: 49/49 semantic items.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has direct or uniquely expandable deterministic evidence, and the final description introduces no extra object, atom, or goal.
每个黄金项都有直接证据或可唯一展开的确定性证据，最终描述没有引入额外对象、原子或目标。


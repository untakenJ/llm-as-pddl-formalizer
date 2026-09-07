# p53 audit and rewrite notes

## Decision

REWRITE REQUIRED

The original gives all 28 goal atoms correctly, but its package pseudo-range and two continuation phrases do not uniquely recover the exact object family, every initial placement, or every location-to-city atom. Three sentence-level repairs replace only those defective spans with finite same-index construction rules.

原文正确给出了全部 28 个目标原子，但包裹的伪范围写法以及两处延续性措辞无法唯一恢复准确的对象集合、所有初始位置和所有地点到城市的关系。仅对这三个有缺陷的句子作有限同索引构造规则的修复。

## Source inventory and totals

- golden_domain.pddl: logistics predicate and action semantics.
- golden_problem.pddl: 73 objects, 146 init atoms, and 28 goal atoms; 247 semantic items total.
- natural_original.txt: original English description.

## Before-rewrite audit

- Object coverage: 71/73. The goal text directly names 28/30 packages, but obj31 and obj91 depend only on an over-generating pseudo-range or an incomplete continuation.
- Init coverage: 102/146. Forty-four init atoms lack unique evidence: two package type facts, 28 middle-index truck/package placements, and 14 middle-index in-city atoms.
- Goal coverage: 28/28.
- Defects across golden semantic items: missing 0; ambiguous 46; contradictory 0.
- Over-generated items: 63 non-golden package identifiers suggested by treating obj11 through obj103 as an integer range.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Specifically, the packages are labeled from obj11 to obj103, the trucks from tru1 to tru10, the cities from cit1 to cit10, and the locations which include positional areas and airports from pos1 to pos10 and apt1 to apt10, respectively. | Specifically, for each index i from 1 through 10, the three package labels are formed by writing obj, then i, then 1, 2, or 3; the trucks are labeled from tru1 to tru10, the cities from cit1 to cit10, and the locations which include positional areas and airports from pos1 to pos10 and apt1 to apt10, respectively. | The original package pseudo-range can generate 63 nonexistent labels; the bounded construction yields exactly 30. / 原包裹伪范围会生成 63 个不存在的标签；有限构造恰好生成 30 个。 | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47,52-54,59-61,66-68,74-76 (exact OBJ declarations); 79-108 ((PACKAGE ...)). |
| 2 | Each city contains a position and an airport: pos1 and apt1 in cit1, pos2 and apt2 in cit2, and so forth up to pos10 and apt10 in cit10. | Each city contains a position and an airport: for every index i from 1 through 10, pos followed by i and apt followed by i are in cit followed by the same i. | And so forth does not define the middle mappings; the replacement gives a finite same-index rule. / “依此类推”没有定义中间映射；修订给出有限的同索引规则。 | golden_problem.pddl:205-224 ((IN-CITY POSi CITi) and (IN-CITY APTi CITi), i=1..10). |
| 3 | For example, tru1 along with obj11, obj12, and obj13 is at pos1, tru2 with obj21, obj22, and obj23 is at pos2, and this pattern continues until tru10 at pos10 with obj101, obj102, and obj103. | For every index i from 1 through 10, tru followed by i and the three package labels formed by writing obj, then i, then 1, 2, or 3 are all at pos followed by the same i. | Endpoint examples plus “this pattern continues” do not uniquely state indices 3-9; the replacement expands to exactly four AT atoms per index. / 端点示例加“模式延续”不能唯一陈述索引 3 至 9；修订恰好展开为每个索引四个 AT 原子。 | golden_problem.pddl:165-204 ((AT TRUi POSi) and three same-index package placements, i=1..10). |

## Deliberately preserved

- The opening, airplane identities and ordered initial airport mapping, all 28 explicit goals, and the closing sentence remain verbatim because they already match the golden problem. / 开头、飞机身份及其有序初始机场映射、全部 28 个明确目标和结尾句均逐字保留，因为它们已与黄金问题一致。
- The original paragraph structure and first-person tone remain unchanged. / 原段落结构和第一人称语气保持不变。

## Post-rewrite verification

- Object coverage: 73/73.
- Init coverage: 146/146.
- Goal coverage: 28/28.
- Atomic ledger: 247/247 rows covered with unique evidence.
- Missing 0; ambiguous 0; contradictory 0; over-generated 0.

Final assertion: every golden item is uniquely recoverable from the revised English description, and no non-golden item is generated.

最终断言：修订后的英文描述可唯一恢复每个黄金语义项，且不会生成任何非黄金语义项。

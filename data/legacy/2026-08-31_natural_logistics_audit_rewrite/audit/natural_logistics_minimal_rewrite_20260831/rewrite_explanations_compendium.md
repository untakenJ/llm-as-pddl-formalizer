# Natural Logistics Rewrite Explanations Compendium

This document consolidates the complete audit decision, change table, reasons, and golden PDDL evidence for every problem. The per-case files remain authoritative if any rendering difference occurs.

本文档汇总每道题的完整审计结论、改写点、原因和 golden PDDL 证据。如汇编呈现与逐题文件存在差异，以逐题文件为准。

## p01

Case artifacts: [p01/](p01/)


## Decision

`NO REWRITE REQUIRED`

The original description already identifies every golden object, type fact, initial-state relation, and goal relation without ambiguity or contradiction. Its finite lists expand to exactly the golden PDDL, so changing the prose would be stylistic rather than corrective.

原始描述已经无歧义地标明了黄金文件中的每个对象、类型事实、初始状态关系和目标关系，也不存在矛盾。文中的有限列表恰好展开为黄金 PDDL 的内容，因此改写只会是文风调整，而不是必要修正。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 15 objects on line 3; 30 init atoms on lines 4–10; 4 goal atoms on line 11.
- `natural_original.txt`: one complete English description; preserved byte-for-byte in `natural_rewritten.txt`.
- Exact totals: objects 15; init 30; goal 4; semantic items 49.

## Before-rewrite coverage

- Objects: 15/15 covered.
- Init atoms: 30/30 covered.
- Goal atoms: 4/4 covered.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte identical to the original. | The original already passes full atomic coverage and uniqueness checks. / 原文已经通过完整的逐项覆盖与唯一对应检查。 | `golden_problem.pddl:3–11` contains exactly the objects, init atoms, and goals stated in the description. |

## Material deliberately preserved

- The package groupings at `pos1` and `pos2`, because both lists exactly match the six package-location init atoms.
- The compact city/location/airport sentence, because it uniquely states all four `in-city` atoms and all location/airport identities.
- The combined goal sentence, because its two coordinated mappings enumerate exactly the four goal atoms.
- All wording and paragraph structure, because no semantic repair was needed.

## Post-rewrite verification

- Objects: 15/15 covered.
- Init atoms: 30/30 covered.
- Goal atoms: 4/4 covered.
- Evidence-ledger rows: 49/49 semantic items.
- Every correspondence is unique; deterministic expansion introduces no extra item.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p02

Case artifacts: [p02/](p02/)


## Decision

`NO REWRITE REQUIRED`

The original description directly and completely identifies the golden object inventory, all initial types and relations, and all six conjunctive package goals. Its coordinated lists have one unique reading and introduce no extra fact, so no corrective rewrite is justified.

原始描述直接且完整地标明了黄金文件中的对象清单、全部初始类型与关系，以及全部六个合取包裹目标。其并列列表只有一种明确解读，也没有引入额外事实，因此没有必要进行修正式改写。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 15 objects on line 3; 30 init atoms on lines 4–10; 6 goal atoms on lines 11–12.
- `natural_original.txt`: one complete English description; preserved byte-for-byte in `natural_rewritten.txt`.
- Exact totals: objects 15; init 30; goal 6; semantic items 51.

## Before-rewrite coverage

- Objects: 15/15 covered.
- Init atoms: 30/30 covered.
- Goal atoms: 6/6 covered.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte identical to the original. | The original already passes full atomic coverage and uniqueness checks. / 原文已经通过完整的逐项覆盖与唯一对应检查。 | `golden_problem.pddl:3–12` contains exactly the objects, init atoms, and goals stated in the description. |

## Material deliberately preserved

- The two package-location lists and the truck-location list, because they exactly cover the initial `at` atoms.
- The two city inventory sentences, because together they uniquely identify all locations, airports, and `in-city` pairs.
- The single objective sentence, because its coordinated clauses explicitly cover all six goal atoms, including the two packages whose goal locations equal their initial locations.
- All wording and paragraph structure, because no semantic repair was needed.

## Post-rewrite verification

- Objects: 15/15 covered.
- Init atoms: 30/30 covered.
- Goal atoms: 6/6 covered.
- Evidence-ledger rows: 51/51 semantic items.
- Every correspondence is unique; finite list expansion introduces no extra item.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p03

Case artifacts: [p03/](p03/)


## Decision

`NO REWRITE REQUIRED`

The original description exhaustively names the three-city object inventory, assigns every vehicle and package its exact initial location, and states all seven package goals. The city/location and grouped package clauses are finite explicit lists with unique mappings, so the description is already atomically complete.

原始描述完整列出了三城场景中的对象清单，为每辆运输工具和每个包裹指定了准确的初始地点，并陈述了全部七个包裹目标。城市—地点条款和分组包裹条款都是具有唯一对应关系的有限显式列表，因此该描述已经达到逐项语义完整。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 22 objects on line 3; 44 init atoms on lines 4–13; 7 goal atoms on lines 14–15.
- `natural_original.txt`: one complete English description; preserved byte-for-byte in `natural_rewritten.txt`.
- Exact totals: objects 22; init 44; goal 7; semantic items 73.

## Before-rewrite coverage

- Objects: 22/22 covered.
- Init atoms: 44/44 covered.
- Goal atoms: 7/7 covered.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte identical to the original. | The original already passes full atomic coverage and uniqueness checks. / 原文已经通过完整的逐项覆盖与唯一对应检查。 | `golden_problem.pddl:3–15` contains exactly the objects, init atoms, and goals stated in the description. |

## Material deliberately preserved

- The explicit nine-package, three-truck, and three-city inventories, because they cover all object and unary type items exactly.
- The paired city/location sentence, because each city is uniquely assigned its `posN` and `aptN` locations and no pair is over-generated.
- The three grouped initial-location clauses, because each names one truck and exactly three packages at the matching position.
- The seven-item goal sentence, because every irregular package-destination pair is stated explicitly.
- All wording and paragraph structure, because no semantic repair was needed.

## Post-rewrite verification

- Objects: 22/22 covered.
- Init atoms: 44/44 covered.
- Goal atoms: 7/7 covered.
- Evidence-ledger rows: 73/73 semantic items.
- Every correspondence is unique; finite list expansion introduces no extra item.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p04

Case artifacts: [p04/](p04/)


## Decision

`NO REWRITE REQUIRED`

The original description uniquely enumerates the nine packages, three position/airport pairs and their cities, all vehicles and initial locations, and all seven irregular goal mappings. “Initial positions” and the named airports are unambiguous natural-language locations, so every golden location type fact is directly recoverable without an added convention.

原始描述唯一地列出了九个包裹、三组位置/机场及其所属城市、全部运输工具及其初始地点，以及全部七个不规则目标映射。“初始位置”和文中点名的机场在自然语言中都是无歧义的地点，因此无需补充约定即可直接恢复黄金文件中的每个地点类型事实。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 22 objects on line 3; 44 init atoms on lines 4–13; 7 goal atoms on lines 14–15.
- `natural_original.txt`: one complete English description; preserved byte-for-byte in `natural_rewritten.txt`.
- Exact totals: objects 22; init 44; goal 7; semantic items 73.

## Before-rewrite coverage

- Objects: 22/22 covered.
- Init atoms: 44/44 covered.
- Goal atoms: 7/7 covered.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte identical to the original. | The original already passes full atomic coverage and uniqueness checks. / 原文已经通过完整的逐项覆盖与唯一对应检查。 | `golden_problem.pddl:3–15` contains exactly the objects, init atoms, and goals stated in the description. |

## Material deliberately preserved

- “Three packages at each of three initial positions” and the following explicit lists, because together they identify exactly nine package objects and their initial locations.
- The truck list, because it uniquely states all three truck objects and their initial positions.
- The airport/city sentence, because it explicitly pairs each airport with one city and locates the sole airplane.
- The seven-item objective sentence, because every irregular package-destination pair is stated explicitly.
- All wording and paragraph structure, because no semantic repair was needed.

## Post-rewrite verification

- Objects: 22/22 covered.
- Init atoms: 44/44 covered.
- Goal atoms: 7/7 covered.
- Evidence-ledger rows: 73/73 semantic items.
- Every correspondence is unique; finite list expansion introduces no extra item.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p05

Case artifacts: [p05/](p05/)


## Decision

`NO REWRITE REQUIRED`

The original description directly and uniquely covers every golden object, all 44 initial-state atoms, and all eight conjunctive goal atoms. It neither contradicts the golden PDDL nor introduces any extra object, relation, or goal, so preserving it verbatim is the required minimal action.

原始描述直接且唯一地覆盖了黄金 PDDL 中的每个对象、全部 44 个初始状态原子以及全部八个合取目标原子。它既不与黄金 PDDL 矛盾，也未引入额外对象、关系或目标，因此逐字保留原文是所要求的最小操作。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, 16 lines.
- `natural_original.txt`: source description, 1,159 bytes.
- Exact totals: 22 objects; 44 init atoms; 8 goal atoms; 74 semantic items.

## Before-rewrite audit

- Object coverage: 22/22.
- Init coverage: 44/44.
- Goal coverage: 8/8.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`. | Every semantic item already has direct, unique evidence; a rewrite would be stylistic rather than corrective. / 每个语义项已有直接且唯一的证据；改写只会是风格调整，而非修正。 | Objects: `golden_problem.pddl:3`; init: `golden_problem.pddl:4-13`; goal: `golden_problem.pddl:14-15`. |

## Material text deliberately preserved

- The complete object inventory and city/location mapping were preserved because they explicitly identify all objects, types, and six `in-city` atoms.
- All initial co-location sentences were preserved because they uniquely cover the airplane, three trucks, and nine packages.
- The complete goal wording was preserved because all eight destination pairs are explicit and simultaneous.

## Post-decision verification

- Object coverage: 22/22.
- Init coverage: 44/44.
- Goal coverage: 8/8.
- Evidence-ledger coverage: 74/74.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: the unchanged final description has zero missing, ambiguous, contradictory, and over-generated items.

## p06

Case artifacts: [p06/](p06/)


## Decision

`REWRITE REQUIRED`

The original identifies every golden item, but two local spans fail the audit: the pseudo-range “from obj11 to obj33” can imply 14 non-golden package labels, and “obj33 remains at apt3” contradicts the explicit initial state that places obj33 at pos3. Replacing only those spans makes the description exact.

原文能够识别每个黄金语义项，但有两个局部片段未通过审核：“from obj11 to obj33”这一伪范围可能暗示 14 个非黄金包裹标签，而“obj33 remains at apt3”与明确将 obj33 初始放在 pos3 的状态相矛盾。仅替换这两个片段即可使描述精确。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, 16 lines.
- `natural_original.txt`: source description, 918 bytes.
- Exact totals: 22 objects; 44 init atoms; 8 goal atoms; 74 semantic items.

## Before-rewrite audit

- Object coverage: 22/22; all nine golden packages are also named later in the initial-state sentences.
- Init coverage: 44/44.
- Goal coverage: 8/8; the intended destination for obj33 is stated, but the persistence word adds a contradictory initial-state implication.
- Missing: 0.
- Ambiguous: 1 defective span.
- Contradictory: 1 defective span.
- Over-generated: 14 possible non-golden labels (`obj14`–`obj20` and `obj24`–`obj30`) under the ordinary inclusive reading of the pseudo-range.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `nine packages labeled from obj11 to obj33` | `nine packages labeled obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, and obj33` | The original pseudo-range does not uniquely construct the nine labels and can over-generate 14 labels; the replacement explicitly enumerates exactly the golden set. / 原伪范围无法唯一构造九个标签，并可能多生成 14 个标签；替换文本明确枚举且仅枚举黄金集合。 | `golden_problem.pddl:3: (:objects ... obj33 obj32 obj31 obj23 obj22 obj21 obj13 obj12 obj11)`; `golden_problem.pddl:4-5: (package obj11) ... (package obj33)`. |
| 2 | `obj33 remains at apt3` | `obj33 is moved to apt3` | “Remains” falsely implies that obj33 starts at apt3; the golden init places it at pos3 while the goal requires apt3. / “remains”错误暗示 obj33 初始位于 apt3；黄金初始状态将其置于 pos3，而目标要求 apt3。 | `golden_problem.pddl:11: (at obj33 pos3)`; `golden_problem.pddl:14-15: (at obj33 apt3)`. |

## Material text deliberately preserved

- The original sentence order, tone, punctuation, city/location mappings, vehicle inventory, and all unaffected wording were preserved.
- The three explicit initial co-location groups were preserved because they uniquely cover all truck and package positions.
- The seven unaffected goal mappings were preserved verbatim.

## Post-rewrite verification

- Object coverage: 22/22.
- Init coverage: 44/44.
- Goal coverage: 8/8.
- Evidence-ledger coverage: 74/74.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: after the two minimal span replacements, missing, ambiguous, contradictory, and over-generated counts are all zero.

## p07

Case artifacts: [p07/](p07/)


## Decision

`NO REWRITE REQUIRED`

The original description explicitly enumerates all objects and types, uniquely states every initial relation, and gives all nine goal destinations. Its finite lists and mappings introduce no omissions, contradictions, ambiguity, or extra facts, so no rewrite is justified.

原始描述明确枚举了所有对象及类型，唯一地陈述了每个初始关系，并给出了全部九个目标目的地。其有限列表和映射没有造成遗漏、矛盾、歧义或额外事实，因此没有理由改写。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, 17 lines.
- `natural_original.txt`: source description, 1,082 bytes.
- Exact totals: 22 objects; 44 init atoms; 9 goal atoms; 75 semantic items.

## Before-rewrite audit

- Object coverage: 22/22.
- Init coverage: 44/44.
- Goal coverage: 9/9.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`. | Every object and atom already has direct and unique support, so the highest-priority preservation rule applies. / 每个对象和原子已有直接且唯一的支持，因此适用最高优先级的原文保留规则。 | Objects: `golden_problem.pddl:3`; init: `golden_problem.pddl:4-13`; goal: `golden_problem.pddl:14-16`. |

## Material text deliberately preserved

- The explicit nine-package, three-truck, three-city, and six-location inventories were preserved.
- The airport classification, airplane position, three co-location groups, and complete city mapping were preserved because each is exact.
- The full nine-item goal list was preserved because every destination is explicit and consistent with the initial-state wording.

## Post-decision verification

- Object coverage: 22/22.
- Init coverage: 44/44.
- Goal coverage: 9/9.
- Evidence-ledger coverage: 75/75.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: the unchanged final description has zero missing, ambiguous, contradictory, and over-generated items.

## p08

Case artifacts: [p08/](p08/)


## Decision

`NO REWRITE REQUIRED`

The original description names exactly the nine packages, three trucks, three cities, six places, and one airplane; its “at” and “in city” phrases uniquely recover every golden initial atom, and it enumerates all nine goals. It has no defect requiring a rewrite.

原始描述准确列出了九个包裹、三辆卡车、三座城市、六个地点和一架飞机；其中“位于”和“在城市中”的表述能够唯一恢复每个黄金初始原子，并且它枚举了全部九个目标。不存在需要改写的缺陷。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, 17 lines.
- `natural_original.txt`: source description, 720 bytes.
- Exact totals: 22 objects; 44 init atoms; 9 goal atoms; 75 semantic items.

## Before-rewrite audit

- Object coverage: 22/22.
- Init coverage: 44/44.
- Goal coverage: 9/9.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`. | The grouped package-position and city-membership statements are explicit finite enumerations, and every other item is directly stated. / 分组的包裹位置与城市隶属陈述是明确的有限枚举，其他各项也均被直接陈述。 | Objects: `golden_problem.pddl:3`; init: `golden_problem.pddl:4-13`; goal: `golden_problem.pddl:14-16`. |

## Material text deliberately preserved

- The three explicit package/location/city groups were preserved because they jointly support package types, positions, place objects, city objects, and the three position-to-city relations.
- The truck list and airport/airplane sentence were preserved because they uniquely fix all vehicle, airport, and remaining city facts.
- The complete goal list was preserved because every package-destination pair is explicit and non-conflicting.

## Post-decision verification

- Object coverage: 22/22.
- Init coverage: 44/44.
- Goal coverage: 9/9.
- Evidence-ledger coverage: 75/75.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: the unchanged final description has zero missing, ambiguous, contradictory, and over-generated items.

## p09

Case artifacts: [p09/](p09/)


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

## p10

Case artifacts: [p10/](p10/)


Decision: `REWRITE REQUIRED`

The original uniquely identifies all objects and all golden relations except `(airport apt3)`: apt3 is named as a location and goal destination but never identified as an airport. One inserted finite rule supplies that missing type fact while also making the already implied airport set explicit.
原文唯一确定了所有对象和其他黄金关系，但没有唯一确定 `(airport apt3)`：apt3 被称为地点和目标目的地，却从未被说明为机场。插入一条有限规则即可补充该缺失类型事实，同时明确原文已经暗示的机场集合。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics; 85 lines.
- `golden_problem.pddl`: 29 objects, 58 init atoms, and 10 goal atoms; 97 semantic items total.
- `natural_original.txt`: original one-line English description.

## Before-rewrite coverage and defects

- Objects covered: 29/29.
- Init atoms covered: 57/58.
- Goal atoms covered: 10/10.
- Missing: 1 (`(airport apt3)`).
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | *(no text; insertion after the city/location mapping)* | `The locations apt1 through apt4 are airports.` | Supplies the missing airport type by a bounded four-item rule without changing existing prose. / 通过有界的四项规则补充缺失的机场类型，不改动现有文字。 | `golden_problem.pddl:9-10`: `(airport apt1)`, `(airport apt2)`, `(airport apt3)`, `(airport apt4)`; `golden_problem.pddl:8-9`: matching location atoms. |

## Material deliberately preserved

- The object enumerations, vehicle and city descriptions, and all initial-location statements were preserved verbatim.
- The entire irregular goal mapping was preserved verbatim because every package–destination pair already matches the golden goal.

## Post-rewrite verification

- Objects covered: 29/29.
- Init atoms covered: 58/58.
- Goal atoms covered: 10/10.
- Evidence ledger: 97/97 semantic items.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has direct or uniquely expandable deterministic evidence, and the final description introduces no extra object, atom, or goal.
每个黄金项都有直接证据或可唯一展开的确定性证据，最终描述没有引入额外对象、原子或目标。

## p11

Case artifacts: [p11/](p11/)


Decision: `REWRITE REQUIRED`

The original names the relevant positions and apt locations, but its generic opening does not map each apt identifier to the airport type, and it never states that the apt identifiers have the separate location type required by the golden problem. One inserted bounded sentence resolves all seven unsupported type facts.
原文列出了相关位置和 apt 地点，但其笼统开头没有将每个 apt 标识符映射到机场类型，也从未说明这些 apt 标识符还具有黄金问题要求的独立地点类型。插入一个有界句子即可解决全部七个缺乏支持的类型事实。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics; 85 lines.
- `golden_problem.pddl`: 29 objects, 58 init atoms, and 11 goal atoms; 98 semantic items total.
- `natural_original.txt`: original one-line English description.

## Before-rewrite coverage and defects

- Objects covered: 29/29.
- Init atoms covered: 51/58.
- Goal atoms covered: 11/11.
- Missing: 0.
- Ambiguous/incomplete: 7: `(location apt1)` through `(location apt4)`, plus `(airport apt1)`, `(airport apt2)`, and `(airport apt4)`.
- Contradictory: 0.
- Over-generated: 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | *(no text; insertion after the city-membership mapping)* | `The positions pos1 through pos4 and the airports apt1 through apt4 are all locations.` | Explicitly types every apt object as an airport and every pos/apt object as a location using two exact four-item ranges. / 用两个精确的四项范围，明确将每个 apt 对象标为机场，并将每个 pos/apt 对象标为地点。 | Location atoms: `golden_problem.pddl:8-9`; airport atoms: `golden_problem.pddl:9-10`. |

## Material deliberately preserved

- All package and truck type/location statements and the complete city-membership mapping were preserved verbatim.
- The airplane statement and all eleven irregular goal pairs were preserved verbatim because they already match the golden problem exactly.

## Post-rewrite verification

- Objects covered: 29/29.
- Init atoms covered: 58/58.
- Goal atoms covered: 11/11.
- Evidence ledger: 98/98 semantic items.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has direct or uniquely expandable deterministic evidence, and the final description introduces no extra object, atom, or goal.
每个黄金项都有直接证据或可唯一展开的确定性证据，最终描述没有引入额外对象、原子或目标。

## p12

Case artifacts: [p12/](p12/)


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

## p13

Case artifacts: [p13/](p13/)


## Decision

`NO REWRITE REQUIRED`

The original description explicitly identifies all packages, vehicles, cities, locations, airport classifications, initial placements, city memberships, and all eleven goal atoms. Every list and mapping is finite and unique, so the preservation rule applies.

原始描述明确给出了全部包裹、运输工具、城市、地点、机场分类、初始位置、城市隶属关系以及全部十一个目标原子。每个列表和映射都是有限且唯一的，因此适用原文保留规则。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines.
- `golden_problem.pddl`: authoritative objects, initial state, and goal.
- `natural_original.txt`: source natural-language description.
- Exact totals: 29 objects; 58 init atoms; 11 goal atoms; 98 semantic items.

## Before-rewrite audit

- Object coverage: 29/29.
- Init coverage: 58/58.
- Goal coverage: 11/11.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`. | Every golden object and atom already has direct evidence or an exact finite deterministic expansion, so the highest-priority preservation rule applies. / 每个黄金对象和原子已有直接证据或精确的有限确定性展开，因此适用最高优先级的原文保留规则。 | Objects: `golden_problem.pddl:3` (`:objects` declaration); init: `golden_problem.pddl:4-15` (all listed init atoms); goal: `golden_problem.pddl:16-18` (all conjuncts). |

## Material text deliberately preserved

- The complete object and unary-type inventories were preserved because every identifier is recoverable without a pseudo-range.
- The initial vehicle/package placements and city-location mappings were preserved because their finite clauses have unique expansions.
- The full goal sentence was preserved because it states every golden goal pair and no extra goal.
- The original tone, sentence order, punctuation, and spacing were preserved byte-for-byte.

## Post-decision verification

- Object coverage: 29/29.
- Init coverage: 58/58.
- Goal coverage: 11/11.
- Evidence-ledger coverage: 98/98.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: the unchanged final description has zero missing, ambiguous, contradictory, and over-generated items.

## p14

Case artifacts: [p14/](p14/)


## Decision

`NO REWRITE REQUIRED`

The original description provides complete finite inventories, uniquely locates every vehicle and package at its initial position, explicitly maps both locations of each city, and lists all twelve goals. It has no semantic defect that justifies rewriting.

原始描述提供了完整的有限对象清单，唯一地给出了每辆运输工具和每个包裹的初始位置，明确映射了每座城市的两个地点，并列出全部十二个目标。不存在足以证明需要改写的语义缺陷。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines.
- `golden_problem.pddl`: authoritative objects, initial state, and goal.
- `natural_original.txt`: source natural-language description.
- Exact totals: 29 objects; 58 init atoms; 12 goal atoms; 99 semantic items.

## Before-rewrite audit

- Object coverage: 29/29.
- Init coverage: 58/58.
- Goal coverage: 12/12.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`. | Every golden object and atom already has direct evidence or an exact finite deterministic expansion, so the highest-priority preservation rule applies. / 每个黄金对象和原子已有直接证据或精确的有限确定性展开，因此适用最高优先级的原文保留规则。 | Objects: `golden_problem.pddl:3` (`:objects` declaration); init: `golden_problem.pddl:4-15` (all listed init atoms); goal: `golden_problem.pddl:16-18` (all conjuncts). |

## Material text deliberately preserved

- The complete object and unary-type inventories were preserved because every identifier is recoverable without a pseudo-range.
- The initial vehicle/package placements and city-location mappings were preserved because their finite clauses have unique expansions.
- The full goal sentence was preserved because it states every golden goal pair and no extra goal.
- The original tone, sentence order, punctuation, and spacing were preserved byte-for-byte.

## Post-decision verification

- Object coverage: 29/29.
- Init coverage: 58/58.
- Goal coverage: 12/12.
- Evidence-ledger coverage: 99/99.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: the unchanged final description has zero missing, ambiguous, contradictory, and over-generated items.

## p15

Case artifacts: [p15/](p15/)


## Decision

`NO REWRITE REQUIRED`

The original description completely enumerates the objects, initial co-location groups, and twelve goals. Its four-city rule is uniquely recoverable: the start clause maps each posi to citi, while the ordered 'paired ... respectively' clause maps each apti to posi. The expansion yields exactly the eight golden in-city atoms.

原始描述完整枚举了对象、初始同位置分组和十二个目标。其四城市规则可以唯一还原：初始位置子句把每个 posi 映射到 citi，而按顺序使用“分别配对”的子句把每个 apti 映射到 posi。展开后恰好得到八个黄金 in-city 原子。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines.
- `golden_problem.pddl`: authoritative objects, initial state, and goal.
- `natural_original.txt`: source natural-language description.
- Exact totals: 29 objects; 58 init atoms; 12 goal atoms; 99 semantic items.

## Before-rewrite audit

- Object coverage: 29/29.
- Init coverage: 58/58.
- Goal coverage: 12/12.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`. | Every golden object and atom already has direct evidence or an exact finite deterministic expansion, so the highest-priority preservation rule applies. / 每个黄金对象和原子已有直接证据或精确的有限确定性展开，因此适用最高优先级的原文保留规则。 | Objects: `golden_problem.pddl:3` (`:objects` declaration); init: `golden_problem.pddl:4-15` (all listed init atoms); goal: `golden_problem.pddl:16-18` (all conjuncts). |

## Material text deliberately preserved

- The complete object and unary-type inventories were preserved because every identifier is recoverable without a pseudo-range.
- The initial vehicle/package placements and city-location mappings were preserved because their finite clauses have unique expansions.
- The full goal sentence was preserved because it states every golden goal pair and no extra goal.
- The original tone, sentence order, punctuation, and spacing were preserved byte-for-byte.

## Post-decision verification

- Object coverage: 29/29.
- Init coverage: 58/58.
- Goal coverage: 12/12.
- Evidence-ledger coverage: 99/99.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: the unchanged final description has zero missing, ambiguous, contradictory, and over-generated items.

## p16

Case artifacts: [p16/](p16/)


## Decision

`REWRITE REQUIRED`

The original is complete except for two local semantic defects. “Holding packages” expresses truck containment instead of the golden package-at-location atoms, and “within a specific city” lists cities without defining the location-to-city correspondence. Two phrase-level substitutions make both relations unique while preserving every unaffected word.

除两处局部语义缺陷外，原始描述是完整的。“holding packages”表达包裹在卡车内，而不是黄金文件中的包裹位于地点原子；“within a specific city”虽然列出了城市，却未定义地点与城市的对应关系。两处短语级替换使这两类关系都变得唯一，同时保留所有未受影响的文字。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics, 85 lines; `(at ?obj ?loc)` and `(in ?obj ?obj)` are distinct predicates at lines 13-14.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, 24 lines.
- `natural_original.txt`: source natural-language description.
- Exact totals: 37 objects; 74 init atoms; 13 goal atoms; 124 semantic items.

## Before-rewrite audit

- Object coverage: 37/37.
- Init coverage: 61/74.
- Goal coverage: 13/13.
- Missing: 0.
- Ambiguous: 10 (the ten golden `in-city` atoms lack a stated city-index correspondence).
- Contradictory: 3 (the three obj3* package placements are described as truck containment rather than package-at-pos3 facts).
- Over-generated: 3 (the phrase “holding packages” implies three absent initial `(in obj3* tru3)` atoms).

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `holding packages obj31, obj32, and obj33` | `along with packages obj31, obj32, and obj33` | Replaces containment wording with unambiguous co-location wording. / 用明确的同位置措辞替换表示装载关系的措辞。 | `golden_problem.pddl:14`: `(at obj31 pos3)`, `(at obj32 pos3)`, `(at obj33 pos3)`; `golden_domain.pddl:13-14`: `at` and `in` are distinct predicates. |
| 2 | `within a specific city (cit1, cit2, cit3, cit4, cit5)` | `within its same-numbered city (cit1, cit2, cit3, cit4, cit5)` | Adds the missing finite index correspondence: for each i from 1 through 5, posi and apti are in citi. / 补充缺失的有限索引对应关系：对 1 至 5 的每个 i，posi 和 apti 都在 citi 中。 | `golden_problem.pddl:16-19`: `(in-city pos1 cit1)`, `(in-city apt1 cit1)`, `(in-city pos2 cit2)`, `(in-city apt2 cit2)`, `(in-city pos3 cit3)`, `(in-city apt3 cit3)`, `(in-city pos4 cit4)`, `(in-city apt4 cit4)`, `(in-city pos5 cit5)`, `(in-city apt5 cit5)`. |

## Material text deliberately preserved

- All object inventories and unary-type wording were preserved.
- Both airplane placements and the other four truck/package co-location clauses were preserved.
- The order, identifiers, and grouping in the city sentence were preserved; only the correspondence phrase changed.
- The complete thirteen-item goal sentence was preserved verbatim.

## Post-rewrite verification

- Object coverage: 37/37.
- Init coverage: 74/74.
- Goal coverage: 13/13.
- Evidence-ledger coverage: 124/124.
- Missing: 0.
- Ambiguous: 0.
- Contradictory: 0.
- Over-generated: 0.

Final assertion: after the two phrase-level repairs, missing, ambiguous, contradictory, and over-generated counts are all zero.

## p17

Case artifacts: [p17/](p17/)


Decision: `NO REWRITE REQUIRED`

The original description directly and uniquely covers all golden objects, all initial facts, and all goal facts. Its city-by-city clauses give the five position memberships and ground placements; its airport clause gives the five airport memberships; and its final clause enumerates every goal placement. No contradiction, omission, ambiguity, or extra fact was found, so the final English description is preserved byte-for-byte.

原描述直接且唯一地覆盖了黄金 PDDL 中的全部对象、全部初始事实和全部目标事实。逐城市的分句给出了五个普通位置的城市归属和地面初始位置，机场分句给出了五个机场的城市归属，最后的分句逐项列出了每个目标位置。未发现矛盾、遗漏、歧义或额外事实，因此最终英文描述按字节原样保留。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics.
- `golden_problem.pddl`: 37 objects on line 3; 74 init atoms on lines 4–19; 13 goal atoms on lines 20–23.
- `natural_original.txt`: one-line original description.
- Exact semantic-item total: 37 + 74 + 13 = 124.

## Before-rewrite coverage

- Objects: 37/37.
- Init atoms: 74/74.
- Goal atoms: 13/13.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of the original. | The original already passes complete atomic coverage and uniqueness checks. / 原文已通过完整的逐原子覆盖与唯一性检查。 | Objects: line 3; init: lines 4–19; goal: lines 20–23. |

## Material deliberately preserved

- The city-by-city organization was preserved because it directly identifies every package/truck position and every `posN`–`citN` relation.
- The compact airport mapping was preserved because its five correspondences are explicit and exhaustive.
- The enumerated goal sentence was preserved because it matches all 13 irregular goal atoms exactly.

## Post-rewrite verification

- Objects: 37/37; init atoms: 74/74; goal atoms: 13/13.
- Atomic ledger: 124/124 semantic items, one row per item.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Final assertion: every golden object and atom has unique natural-language evidence, and all four defect counts are zero.

## p18

Case artifacts: [p18/](p18/)


Decision: `REWRITE REQUIRED`

The original names only `apn1` and `apn2` but calls them three airplanes, uses an imprecise city/location inventory whose “each containing … such as” scope can be read as non-golden cross-city membership, and says the three `obj5*` packages are being carried by `tru5` instead of locating them at `pos5`. Three local phrase substitutions remove those defects without changing the organization, mappings, or goals.

原文只列出 `apn1` 和 `apn2`，却称其为三架飞机；城市/地点清单中“each containing … such as”的作用域不精确，可能被解读为黄金 PDDL 中不存在的跨城市归属；原文还称三个 `obj5*` 包裹由 `tru5` 装载，而不是明确将它们置于 `pos5`。三处局部短语替换消除了这些缺陷，同时保留了原有组织、映射和目标。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics; `(in ?obj ?obj)` on line 14 distinguishes loaded cargo from co-location represented by `(at ...)`.
- `golden_problem.pddl`: 37 objects on line 3; 74 init atoms on lines 4–19; 14 goal atoms on lines 20–23.
- `natural_original.txt`: four-paragraph original description.
- Exact semantic-item total: 37 + 74 + 14 = 125.

## Before-rewrite coverage

- Objects: 37/37.
- Init atoms: 71/74; the three golden `(at obj51 pos5)`, `(at obj52 pos5)`, and `(at obj53 pos5)` atoms were not uniquely stated by “carrying.”
- Goal atoms: 14/14.
- Missing: 0; ambiguous: 4 (the city/location scope plus three package placements); contradictory: 1 (three airplanes versus the two golden airplanes); over-generated: 4 (one unnamed extra airplane and three implied loaded-cargo relations).

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `three airplanes named apn1 and apn2` | `two airplanes named apn1 and apn2` | Repairs the numerical contradiction while preserving the named objects. / 修复数量矛盾并保留原有对象名称。 | Object list: line 3 (`apn2 apn1`); airplane type facts: lines 11–12 (`(airplane apn1)`, `(airplane apn2)`). |
| 2 | `each containing locations such as` | `along with locations` | Converts an ambiguous per-city example construction into a neutral exact inventory; the next paragraph retains the explicit one-to-one city mapping. / 将含糊的逐城市举例结构改为中性的精确清单，下一段仍保留明确的一一城市映射。 | Location types: lines 8–10; exact `in-city` pairs: lines 16–19. |
| 3 | `carrying obj51, obj52, and obj53` | `with packages obj51, obj52, and obj53` | States co-location at `pos5` and avoids inventing `(in obj5* tru5)` cargo atoms. / 明确包裹与卡车同处 `pos5`，避免虚构 `(in obj5* tru5)` 装载原子。 | Lines 15–16: `(at tru5 pos5)`, `(at obj51 pos5)`, `(at obj52 pos5)`, `(at obj53 pos5)`; no `(in ...)` init atoms occur. |

## Material deliberately preserved

- All object names and the four-paragraph structure were preserved.
- Both airplane placements at `apt2` and all five exact city mappings were preserved.
- The complete 14-item goal description was preserved verbatim.

## Post-rewrite verification

- Objects: 37/37; init atoms: 74/74; goal atoms: 14/14.
- Atomic ledger: 125/125 semantic items, one row per item.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Final assertion: after the three minimal substitutions, every golden object and atom has unique natural-language evidence and all four defect counts are zero.

## p19

Case artifacts: [p19/](p19/)


Decision: `REWRITE REQUIRED`

The original description uniquely states all objects, types, vehicle/package placements, airplane placements, and goals, but it never links `pos1` to `cit1` or airports `apt2`, `apt3`, and `apt4` to their cities. One bounded index rule supplies exactly those missing facts while also making the already described regular family explicit. All original sentences remain verbatim.

原描述唯一地说明了全部对象、类型、运输工具/包裹位置、飞机位置和目标，但没有将 `pos1` 归入 `cit1`，也没有将机场 `apt2`、`apt3`、`apt4` 分别归入其城市。新增的一条有界索引规则恰好补足这些缺失事实，并把原本已部分描述的规则族明确化。所有原句均逐字保留。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics.
- `golden_problem.pddl`: 37 objects on line 3; 74 init atoms on lines 4–19; 14 goal atoms on lines 20–23.
- `natural_original.txt`: one-line original description.
- Exact semantic-item total: 37 + 74 + 14 = 125.

## Before-rewrite coverage

- Objects: 37/37.
- Init atoms: 70/74.
- Goal atoms: 14/14.
- Missing: 4 — `(in-city pos1 cit1)`, `(in-city apt2 cit2)`, `(in-city apt3 cit3)`, and `(in-city apt4 cit4)`.
- Ambiguous: 0; contradictory: 0; over-generated: 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | No sentence between `...with truck tru5.` and `We also have two airplanes...` | `For each index i from 1 through 5, position posi and airport apti are locations in city citi, where i is replaced by that index in all three identifiers.` | Adds one finite deterministic rule. Expanding `i = 1, 2, 3, 4, 5` generates exactly the ten golden `in-city` pairs, as well as the stated location/airport/city types, with no extra identifier or relation. / 新增一条有限确定规则；展开 `i = 1, 2, 3, 4, 5` 后恰好生成十个黄金 `in-city` 对，同时给出地点/机场/城市类型，不产生额外标识符或关系。 | Objects: line 3; types: lines 8–11; exact `in-city` family: lines 16–19. |

## Material deliberately preserved

- Every original sentence and the single-paragraph tone were preserved verbatim.
- All five ground co-location clauses and both airplane placements were preserved.
- The complete 14-item goal clause and closing sentence were preserved.

## Post-rewrite verification

- Objects: 37/37; init atoms: 74/74; goal atoms: 14/14.
- Rule expansion: `i=1..5` yields `pos1..pos5`, `apt1..apt5`, `cit1..cit5`, and exactly the ten golden position/airport city-membership atoms.
- Atomic ledger: 125/125 semantic items, one row per item.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Final assertion: after the single bounded-rule insertion, every golden object and atom has unique natural-language evidence and all four defect counts are zero.

## p20

Case artifacts: [p20/](p20/)


Decision: `NO REWRITE REQUIRED`

The original description explicitly inventories every package, truck, airplane, and city; gives an exhaustive position/airport-to-city mapping; uniquely states all 22 vehicle/package placements; and enumerates all 15 goal atoms. The correspondence sentence refers back to an already explicit mapping and does not require guessing. No rewrite is needed, so the final English text is preserved byte-for-byte.

原描述明确列出了每个包裹、卡车、飞机和城市，给出了完整的位置/机场到城市映射，唯一地说明了全部 22 个运输工具/包裹初始位置，并逐项列出了全部 15 个目标原子。“corresponding cities”句明确回指前一句已经给出的映射，无需猜测。因此无需改写，最终英文文本按字节原样保留。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics.
- `golden_problem.pddl`: 37 objects on line 3; 74 init atoms on lines 4–19; 15 goal atoms on lines 20–23.
- `natural_original.txt`: one-line original description.
- Exact semantic-item total: 37 + 74 + 15 = 126.

## Before-rewrite coverage

- Objects: 37/37.
- Init atoms: 74/74.
- Goal atoms: 15/15.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of the original. | The exact inventories, mappings, placements, and goals already satisfy the atomic audit. / 精确的清单、映射、初始位置和目标已经满足逐原子审计。 | Objects: line 3; init: lines 4–19; goal: lines 20–23. |

## Material deliberately preserved

- The explicit inventories of 15 packages, five trucks, two airplanes, and five cities were preserved.
- The five exact `posN`/`aptN`–`citN` mappings and grouped initial placements were preserved.
- The complete 15-item goal list was preserved verbatim.

## Post-rewrite verification

- Objects: 37/37; init atoms: 74/74; goal atoms: 15/15.
- Atomic ledger: 126/126 semantic items, one row per item.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Final assertion: every golden object and atom has unique natural-language evidence, and all four defect counts are zero.

## p21

Case artifacts: [p21/](p21/)


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

## p22

Case artifacts: [p22/](p22/)


## Decision

`REWRITE REQUIRED`

The original contains malformed `city]-1` and `city]-2` placeholders, so the complete location, airport, city-membership, and truck-location families cannot be uniquely expanded. It also says that the packages are in “different places,” although package3 and package4 are both initially at city1-1. Three sentence-local repairs remove these defects while preserving every unaffected sentence.

原文包含格式错误的 `city]-1` 和 `city]-2` 占位符，因此无法唯一展开完整的地点、机场、城市隶属关系和卡车位置系列。原文还称包裹位于“不同地点”，但 package3 与 package4 初始时都位于 city1-1。三处句内局部修订消除了这些缺陷，并保留了所有未受影响的句子。

## Source inventory

- `golden_domain.pddl`: logistics predicates and action semantics.
- `golden_problem.pddl`: 32 objects, 64 init atoms, and 6 goal atoms (102 semantic items total).
- `natural_original.txt`: audited original English description.
- `natural_rewritten.txt`: minimally repaired English description.

## Before-rewrite coverage and defects

- Objects covered: 28/32
- Init atoms covered: 32/64
- Goal atoms covered: 6/6
- Missing: 6 (the six `(location cityN-2)` type facts were not stated)
- Ambiguous: 30 (four location objects and 26 init atoms depended on malformed or non-unique correspondence wording)
- Contradictory: 1 (the “different places” claim conflicts with the co-location of package3 and package4)
- Over-generated: 0

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | There are six packages, named package1 through package6, and each is located in different places across six cities, labeled city1 through city6. | There are six packages, named package1 through package6, and six cities, labeled city1 through city6. | Removes the unsupported implication that the six packages occupy different places while preserving the package and city inventories. / 删除六个包裹位于不同地点这一无依据的含义，同时保留包裹和城市清单。 | `golden_problem.pddl:68: (at package4 city1-1)`; `golden_problem.pddl:69: (at package3 city1-1)`. |
| 2 | Each city has a distinct location labeled city]-1 and an airport labeled city]-2 (for example, city1-1 and city1-2 for city1). | For each N from 1 through 6, cityN has a distinct location cityN-1 and an airport location cityN-2 (for example, city1-1 and city1-2 for city1). | Replaces malformed placeholders with a bounded index rule and states that every airport is also a location. / 用有界索引规则替换错误占位符，并明确每个机场同时也是地点。 | Objects: `golden_problem.pddl:3-7`; `(location city6-1)` through `(location city1-1)`: lines 28-33; `(airport city6-2)` and `(location city6-2)` through the city1 counterparts: lines 34-45; all `(in-city ...)` atoms: lines 46-57. |
| 3 | The trucks are initially located at their corresponding city]-1 locations, and both airplanes are initially stationed at city4-2. | For each N from 1 through 6, truckN is initially located at cityN-1, and both airplanes are initially stationed at city4-2. | Makes the finite truck-to-location correspondence explicit and uniquely expandable. / 明确有限的卡车到地点对应关系，使其可唯一展开。 | `golden_problem.pddl:60: (at truck6 city6-1)` through `golden_problem.pddl:65: (at truck1 city1-1)`. |

## Material deliberately preserved

- The opening setup phrase, package/truck/airplane naming style, and overall single-paragraph organization were retained.
- The exact airplane initial locations, all six package initial locations, and all six goal mappings were preserved verbatim because they already match `golden_problem.pddl:58-59,66-77`.
- The city1 example was preserved as an illustration after the complete bounded rule; it no longer substitutes for missing evidence.

## Post-rewrite verification

- Objects covered: 32/32
- Init atoms covered: 64/64
- Goal atoms covered: 6/6
- Evidence ledger rows: 102/102
- Expanding each `N = 1, 2, 3, 4, 5, 6` rule yields exactly the golden location, airport, city-membership, and truck-location items and no others.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p23

Case artifacts: [p23/](p23/)


## Decision

`NO REWRITE REQUIRED`

The original description names every object, states every type and initial-state fact, and explicitly lists all four goal atoms. Its city-membership statements also establish that both airports are locations. No repair is necessary.

原描述列出了每个对象，说明了每个类型与初始状态事实，并明确列出全部四个目标原子。城市隶属关系语句也确认两个机场都是地点。无需修订。

## Source inventory

- `golden_domain.pddl`: logistics predicates and action semantics.
- `golden_problem.pddl`: 15 objects, 30 init atoms, and 4 goal atoms (49 semantic items total).
- `natural_original.txt`: audited original English description.
- `natural_rewritten.txt`: byte-for-byte copy of `natural_original.txt`.

## Before-rewrite coverage and defects

- Objects covered: 15/15
- Init atoms covered: 30/30
- Goal atoms covered: 4/4
- Missing: 0
- Ambiguous: 0
- Contradictory: 0
- Over-generated: 0

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | The original already provides unique evidence for every object, init atom, and goal atom. / 原文已为每个对象、初始原子和目标原子提供唯一证据。 | Objects: `golden_problem.pddl:3`; init: `golden_problem.pddl:4-10`; goal: `golden_problem.pddl:11`. |

## Material deliberately preserved

- The complete original text was preserved verbatim, including its explicit package and vehicle groupings, city/location descriptions, initial co-locations, and four goal conditions.
- The repeated city-membership sentence was retained because it directly supports the four `in-city` atoms and the generic location status of apt1 and apt2.

## Post-rewrite verification

- Objects covered: 15/15
- Init atoms covered: 30/30
- Goal atoms covered: 4/4
- Evidence ledger rows: 49/49
- Every correspondence is direct and unique.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p24

Case artifacts: [p24/](p24/)


## Decision

`NO REWRITE REQUIRED`

The original description explicitly enumerates the complete object inventory, every unary type fact, every initial location and city-membership atom, and all five goal atoms. It exactly matches the golden PDDL and requires no rewrite.

原描述明确列出了完整对象清单、每个一元类型事实、每个初始位置与城市隶属关系原子，以及全部五个目标原子。它与黄金 PDDL 完全一致，无需改写。

## Source inventory

- `golden_domain.pddl`: logistics predicates and action semantics.
- `golden_problem.pddl`: 49 objects, 98 init atoms, and 5 goal atoms (152 semantic items total).
- `natural_original.txt`: audited original English description.
- `natural_rewritten.txt`: byte-for-byte copy of `natural_original.txt`.

## Before-rewrite coverage and defects

- Objects covered: 49/49
- Init atoms covered: 98/98
- Goal atoms covered: 5/5
- Missing: 0
- Ambiguous: 0
- Contradictory: 0
- Over-generated: 0

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | Every golden item already has an exact natural-language counterpart. / 每个黄金条目都已具有精确的自然语言对应项。 | Objects: `golden_problem.pddl:3-9`; init: `golden_problem.pddl:10-107`; goal: `golden_problem.pddl:108-112`. |

## Material deliberately preserved

- The complete original text was preserved verbatim.
- The explicit descending-order inventories and mappings were retained because they directly mirror the golden object, init, and goal sets without ambiguity or extra facts.

## Post-rewrite verification

- Objects covered: 49/49
- Init atoms covered: 98/98
- Goal atoms covered: 5/5
- Evidence ledger rows: 152/152
- Every correspondence is direct and unique.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p25

Case artifacts: [p25/](p25/)


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

## p26

Case artifacts: [p26/](p26/)


## Decision

`REWRITE REQUIRED`

The original names the packages, cities, trucks, and planes, but it never defines the 52 location identifiers or their exact city/airport roles, gives only examples or vague cities for every initial placement, and leaves every goal destination identifier unresolved. Four contiguous repairs add one bounded city-layout rule and exact vehicle, package, and goal mappings while preserving the surrounding inventory and tone.

原描述列出了包裹、城市、卡车和飞机，但没有定义 52 个地点标识符及其准确的城市/机场角色；所有初始位置都只用示例或模糊城市说明，所有目标地点标识符也都无法确定。四处连续修订增加一条有界城市布局规则，以及精确的车辆、包裹和目标映射，同时保留周围的清单与语气。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 100 objects on lines 3–16; 200 init atoms on lines 17–216; 7 goal atoms on lines 217–223.
- `natural_original.txt`: audited original English description.
- Exact totals: objects 100; init 200; goal 7; semantic items 307.

## Before-rewrite coverage and defects

- Objects covered: 48/100
- Init atoms covered: 48/200
- Goal atoms covered: 0/7
- Missing: 0
- Ambiguous/incomplete: 211 (52 location objects, 152 init atoms, and 7 goal atoms)
- Contradictory: 1 (the vehicle sentence says “different locations,” but three truck pairs are co-located)
- Over-generated: 0

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Each city has several locations and some also have airports. | For each N from 1 through 13, cityN has locations cityN-1, cityN-2, and cityN-3, plus the airport location cityN-4; all four locations are part of cityN. | Replaces vague quantities with a complete bounded identifier, type, airport, and city-membership rule. / 用完整的有界标识符、类型、机场和城市归属规则替换模糊数量。 | Location objects: `golden_problem.pddl:9–16`; location/airport types: lines 65–129; all 52 `(in-city ...)` atoms: lines 130–181. |
| 2 | For the initial setup, planes and trucks are stationed in different locations within their respective cities. For example, plane1 is currently located at the airport in city2, while truck23 is at a location in city13. | For the initial setup, the planes and trucks are stationed as follows. Plane5 is at city12-4, plane4 at city8-4, plane3 at city6-4, plane2 at city13-4, and plane1 at city2-4. Truck23 is at city13-2, truck22 at city12-3, truck21 at city11-3, truck20 at city10-1, truck19 at city9-1, truck18 at city8-2, truck17 at city7-3, truck16 at city6-3, truck15 at city5-2, truck14 at city4-1, truck13 at city3-3, truck12 at city2-1, truck11 at city1-1, truck10 at city10-3, truck9 at city8-1, truck8 at city2-2, truck7 at city9-4, truck6 at city9-2, truck5 at city8-2, truck4 at city7-3, truck3 at city7-1, truck2 at city8-1, and truck1 at city5-4. | Examples cannot recover the irregular five-plane and 23-truck mapping; “different locations” also conflicts with three golden truck co-locations. The replacement enumerates every golden pair. / 示例无法恢复不规则的五架飞机和 23 辆卡车映射；“不同地点”还与三组黄金卡车共址事实冲突。修订后枚举每个黄金对应对。 | Plane atoms: `golden_problem.pddl:182–186`; truck atoms: lines 187–209, including truck18/truck5 at `city8-2`, truck17/truck4 at `city7-3`, and truck9/truck2 at `city8-1`. |
| 3 | The packages are distributed as follows: package7 is at the airport in city1, package6 is at a location in city2, package5 is at the same location as truck20 in city10, package4 is at the airport in city5, package3 is at a location in city11, package2 is at the same location as truck21 in city11, and package1 is at a location in city4. | The packages are distributed as follows: package7 is at city1-4, package6 is at city2-3, package5 is at city10-1, package4 is at city5-4, package3 is at city11-1, package2 is at city11-3, and package1 is at city4-2. | Replaces city-only or relational descriptions with the seven exact initial identifiers. / 用七个精确初始标识符替换仅说明城市或依赖关系的描述。 | `golden_problem.pddl:210–216`: the seven package `(at ...)` atoms. |
| 4 | My goal is to move these packages to specific destinations: package7 needs to reach a location in city12, package6 has to be delivered to a location in city9, package5 should be transported to the same location as package7 in city12, package4 is to be sent to the airport in city8, package3 needs to arrive at the airport in city13, package2 is to be delivered to a location in city7, and finally, package1 has to reach a location in city13. | My goal is to move these packages to specific destinations: package7 needs to reach city12-3, package6 has to be delivered to city9-3, package5 should be transported to city12-3, package4 is to be sent to city8-4, package3 needs to arrive at city13-4, package2 is to be delivered to city7-1, and finally, package1 has to reach city13-1. | Makes every conjunctive goal destination explicit; the irregular mapping cannot be inferred from city names alone. / 明确每个合取目标的目的地；不规则映射不能仅凭城市名称推断。 | `golden_problem.pddl:217–223`: all seven goal atoms. |

## Material deliberately preserved

- The opening package/city counts and the exact package, city, truck, and airplane ranges.
- The availability sentence, list ordering, first-person tone, and single-paragraph organization.
- Every phrase that did not obscure an identifier or mapping.

## Post-rewrite verification

- Objects covered: 100/100
- Init atoms covered: 200/200
- Goal atoms covered: 7/7
- Evidence ledger rows: 307/307
- Substitution of each `N = 1, ..., 13` yields exactly 52 location objects, 52 location atoms, 13 airport atoms, and 52 city-membership atoms; all irregular placements are explicitly enumerated.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p27

Case artifacts: [p27/](p27/)


## Decision

`REWRITE REQUIRED`

The original falsely says that each city has six packages and uses the pseudo-range `obj11` to `obj63`, which can generate 35 non-golden identifiers. It also never types `apt1`, `apt3`, `apt5`, or `apt6` as airports. One sentence replacement and one short bounded type rule repair those defects; all placements, city mappings, and goals remain verbatim.

原描述错误地声称每座城市有六个包裹，并使用从 `obj11` 到 `obj63` 的伪范围，可能生成 35 个非黄金标识符。此外，原文从未把 `apt1`、`apt3`、`apt5` 或 `apt6` 标为机场。替换一个句子并增加一条简短的有界类型规则即可修复这些缺陷；所有位置、城市映射和目标均保持原样。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 44 objects on lines 4–47; 88 init atoms on lines 50–137; 16 goal atoms on lines 140–155.
- `natural_original.txt`: audited original English description.
- Exact totals: objects 44; init 88; goal 16; semantic items 148.

## Before-rewrite coverage and defects

- Objects covered: 44/44
- Init atoms covered: 84/88
- Goal atoms covered: 16/16
- Missing: 4 (`(airport apt1)`, `(airport apt3)`, `(airport apt5)`, and `(airport apt6)`)
- Ambiguous: 0
- Contradictory: 1
- Over-generated: 35 non-golden package identifiers under the pseudo-range reading

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Initially, we have six packages in each city, numbered from obj11 to obj63. | Initially, we have 18 packages labeled obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, and obj63. | Corrects the false per-city count and replaces the pseudo-range with exactly the 18 golden package identifiers. / 更正错误的每城数量，并用恰好 18 个黄金包裹标识符替换伪范围。 | Package objects: `golden_problem.pddl:8–10,16–18,23–25,30–32,37–39,45–47`; package type atoms: lines 50–67. |
| 2 | No sentence after the six-city location mapping. | The locations apt1 through apt6 are airports. | Adds the four missing airport type facts through a bounded range that expands to exactly all six golden airport atoms; apt2 and apt4 were already directly typed. / 通过恰好展开为六个黄金机场原子的有界范围补充四个缺失类型事实；apt2 和 apt4 原本已有直接类型证据。 | `golden_problem.pddl:92–97`: `(airport apt1)` through `(airport apt6)`. |

## Material deliberately preserved

- The six exact truck/package co-location clauses and both airplane placements.
- The explicit city-to-`pos`/`apt` mapping and all 16 irregular goal pairs.
- The single-paragraph organization and all unaffected wording.

## Post-rewrite verification

- Objects covered: 44/44
- Init atoms covered: 88/88
- Goal atoms covered: 16/16
- Evidence ledger rows: 148/148
- The package list contains exactly 18 names; `apt1` through `apt6` expands to exactly the six golden airports.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p28

Case artifacts: [p28/](p28/)


## Decision

`REWRITE REQUIRED`

The original package pseudo-range can generate 35 identifiers absent from the golden problem, and its parallel city/position/airport ranges do not state which airport belongs to which city. Replacing the package range with the exact 18-name list and adding “same-numbered” twice resolves both defects without changing any placement or goal clause.

原描述中的包裹伪范围可能生成黄金问题中不存在的 35 个标识符，并且并列的城市、位置和机场范围没有说明每座机场属于哪座城市。把包裹范围替换为精确的 18 项名称列表，并两次加入“同编号”，即可消除两类缺陷，且不改动任何位置或目标子句。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 44 objects on lines 4–47; 88 init atoms on lines 50–137; 16 goal atoms on lines 140–155.
- `natural_original.txt`: audited original English description.
- Exact totals: objects 44; init 88; goal 16; semantic items 148.

## Before-rewrite coverage and defects

- Objects covered: 44/44
- Init atoms covered: 82/88
- Goal atoms covered: 16/16
- Missing: 0
- Ambiguous: 7 (one package pseudo-range and six airport-to-city correspondences)
- Contradictory: 0
- Over-generated: 35 non-golden package identifiers under the pseudo-range reading

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | There are packages labeled obj11 through obj63 and trucks labeled tru1 through tru6. | There are packages labeled obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, and obj63, and trucks labeled tru1 through tru6. | Replaces a pseudo-range that can imply every integer label from 11 through 63 with the exact golden package set. / 用精确的黄金包裹集合替换可能暗示 11 到 63 之间每个整数标签的伪范围。 | Package objects: `golden_problem.pddl:8–10,16–18,23–25,30–32,37–39,45–47`; package atoms: lines 50–67. |
| 2 | Each city, cit1 through cit6, has a position (pos1 through pos6) and an airport (apt1 through apt6). | Each city, cit1 through cit6, has its same-numbered position (pos1 through pos6) and its same-numbered airport (apt1 through apt6). | Adds the missing unique index correspondence; the bounded rule now yields exactly `posi` and `apti` in `citi` for `i = 1, ..., 6`. / 补充缺失的唯一索引对应关系；有界规则现在对 `i = 1, ..., 6` 恰好生成 `posi` 和 `apti` 属于 `citi`。 | Objects and types: `golden_problem.pddl:4–47,74–97`; city-membership atoms: lines 126–137. |

## Material deliberately preserved

- The opening inventory frame, truck range, both airplane placements, and original sentence order.
- All six truck/package co-location groups and all 16 explicit goals.
- Every word outside the package inventory and the two inserted correspondence modifiers.

## Post-rewrite verification

- Objects covered: 44/44
- Init atoms covered: 88/88
- Goal atoms covered: 16/16
- Evidence ledger rows: 148/148
- The same-number rule expands to exactly 12 city-membership pairs, and the package enumeration introduces no extra identifier.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p29

Case artifacts: [p29/](p29/)


## Decision

`NO REWRITE REQUIRED`

The original description already gives a direct statement or uniquely expandable finite rule for every golden object, type fact, initial-state atom, and goal atom. It contains no contradiction or extra semantic item, so the text is preserved verbatim.

原描述已经为每个金标对象、类型事实、初始状态原子和目标原子提供直接陈述或可唯一展开的有限规则；其中没有矛盾或额外语义项，因此逐字保留原文。

## Source inventory and semantic totals

| Source | Inventory |
|---|---|
| `golden_domain.pddl` | Golden Logistics predicate and action semantics; 85 lines. |
| `golden_problem.pddl` | Golden objects, initial state, and conjunctive goal; 159 lines. |
| `natural_original.txt` | Original English description audited before any decision. |

| Section | Total |
|---|---:|
| Objects | 44 |
| Init atoms, including unary type facts | 88 |
| Goal atoms | 17 |
| Semantic items | 149 |

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 17/17 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every listed item has direct or deterministic-rule evidence in the original text.

原文为每个列出的项目提供了直接证据或确定性规则证据。

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | The original already passes the atomic audit; stylistic rewriting is prohibited. / 原文已通过逐项审计，故不作风格性改写。 | `golden_problem.pddl` lines 3–156. |

## Material deliberately preserved

- The full English description is deliberately preserved byte-for-byte, including its original sentence order and compressed finite mappings, because all correspondences are complete and unique.
- 英文描述全文按字节保留，包括原句序及有限映射的压缩表达，因为全部对应关系完整且唯一。

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 17/17 |
| Ledger rows | 149/149 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

The renewed atomic audit confirms that every correspondence is unique and that all deterministic rules expand to exactly the golden siblings with no unstated exception.

重新进行的逐项审计确认：每项对应关系都是唯一的，所有确定性规则都仅展开为金标同组项目，且没有未说明的例外。

**Final assertion:** missing, ambiguous, contradictory, and over-generated counts are all zero.

**最终断言：** 缺失、歧义、矛盾和过度生成计数均为零。

## p30

Case artifacts: [p30/](p30/)


## Decision

`NO REWRITE REQUIRED`

The original description already gives a direct statement or uniquely expandable finite rule for every golden object, type fact, initial-state atom, and goal atom. It contains no contradiction or extra semantic item, so the text is preserved verbatim.

原描述已经为每个金标对象、类型事实、初始状态原子和目标原子提供直接陈述或可唯一展开的有限规则；其中没有矛盾或额外语义项，因此逐字保留原文。

## Source inventory and semantic totals

| Source | Inventory |
|---|---|
| `golden_domain.pddl` | Golden Logistics predicate and action semantics; 85 lines. |
| `golden_problem.pddl` | Golden objects, initial state, and conjunctive goal; 159 lines. |
| `natural_original.txt` | Original English description audited before any decision. |

| Section | Total |
|---|---:|
| Objects | 44 |
| Init atoms, including unary type facts | 88 |
| Goal atoms | 17 |
| Semantic items | 149 |

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 17/17 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every listed item has direct or deterministic-rule evidence in the original text.

原文为每个列出的项目提供了直接证据或确定性规则证据。

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | The original already passes the atomic audit; stylistic rewriting is prohibited. / 原文已通过逐项审计，故不作风格性改写。 | `golden_problem.pddl` lines 3–156. |

## Material deliberately preserved

- The full English description is deliberately preserved byte-for-byte, including its original sentence order and compressed finite mappings, because all correspondences are complete and unique.
- 英文描述全文按字节保留，包括原句序及有限映射的压缩表达，因为全部对应关系完整且唯一。

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 17/17 |
| Ledger rows | 149/149 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

The renewed atomic audit confirms that every correspondence is unique and that all deterministic rules expand to exactly the golden siblings with no unstated exception.

重新进行的逐项审计确认：每项对应关系都是唯一的，所有确定性规则都仅展开为金标同组项目，且没有未说明的例外。

**Final assertion:** missing, ambiguous, contradictory, and over-generated counts are all zero.

**最终断言：** 缺失、歧义、矛盾和过度生成计数均为零。

## p31

Case artifacts: [p31/](p31/)


## Decision

`REWRITE REQUIRED`

The original description covers every golden object, initial atom, and goal atom, but the package phrase `obj11 to obj63` is a pseudo-range that can imply 35 nonexistent identifiers. Replacing only that span with the exact 18-name list removes the ambiguity and over-generation.

原描述覆盖了全部金标对象、初始原子和目标原子，但包裹表述 `obj11 to obj63` 是伪范围，可能暗示 35 个不存在的标识符。仅将该片段替换为准确的 18 个名称即可消除歧义和过度生成。

## Source inventory and semantic totals

| Source | Inventory |
|---|---|
| `golden_domain.pddl` | Golden Logistics predicate and action semantics; 85 lines. |
| `golden_problem.pddl` | Golden objects, initial state, and conjunctive goal; 160 lines. |
| `natural_original.txt` | Original English description audited before any decision. |

| Section | Total |
|---|---:|
| Objects | 44 |
| Init atoms, including unary type facts | 88 |
| Goal atoms | 18 |
| Semantic items | 150 |

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 18/18 |
| Missing | 0 |
| Ambiguous | 1 |
| Contradictory | 0 |
| Over-generated | 35 |

Coverage counts reflect that every golden item is mentioned; the defect is the original phrase’s additional non-golden readings.

覆盖计数表明全部金标项均被提及；缺陷在于原短语还允许额外的非金标解读。

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `obj11 to obj63` | `obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, and obj63` | The pseudo-range can be read as every integer label from 11 through 63; the explicit list is exact. / 伪范围可能被理解为 11 至 63 的所有整数标签；显式列表与金标完全一致。 | Objects: lines 8–10, 16–18, 23–25, 30–32, 37–39, 45–47; package atoms: lines 50–67. |

## Material deliberately preserved

- The opening, location ranges, airplane placement, all initial placements, all city connections, and the complete goal mapping remain verbatim because each is already semantically correct.
- 除包裹伪范围外，开头、地点范围、飞机位置、所有初始位置、城市连接及完整目标映射均逐字保留，因为这些内容已在语义上正确。

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 18/18 |
| Ledger rows | 150/150 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

The renewed atomic audit confirms that every correspondence is unique and that all deterministic rules expand to exactly the golden siblings with no unstated exception.

重新进行的逐项审计确认：每项对应关系都是唯一的，所有确定性规则都仅展开为金标同组项目，且没有未说明的例外。

**Final assertion:** missing, ambiguous, contradictory, and over-generated counts are all zero.

**最终断言：** 缺失、歧义、矛盾和过度生成计数均为零。

## p32

Case artifacts: [p32/](p32/)


## Decision

`NO REWRITE REQUIRED`

The original description already gives a direct statement or uniquely expandable finite rule for every golden object, type fact, initial-state atom, and goal atom. It contains no contradiction or extra semantic item, so the text is preserved verbatim.

原描述已经为每个金标对象、类型事实、初始状态原子和目标原子提供直接陈述或可唯一展开的有限规则；其中没有矛盾或额外语义项，因此逐字保留原文。

## Source inventory and semantic totals

| Source | Inventory |
|---|---|
| `golden_domain.pddl` | Golden Logistics predicate and action semantics; 85 lines. |
| `golden_problem.pddl` | Golden objects, initial state, and conjunctive goal; 160 lines. |
| `natural_original.txt` | Original English description audited before any decision. |

| Section | Total |
|---|---:|
| Objects | 44 |
| Init atoms, including unary type facts | 88 |
| Goal atoms | 18 |
| Semantic items | 150 |

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 18/18 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every listed item has direct or deterministic-rule evidence in the original text.

原文为每个列出的项目提供了直接证据或确定性规则证据。

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | The original already passes the atomic audit; stylistic rewriting is prohibited. / 原文已通过逐项审计，故不作风格性改写。 | `golden_problem.pddl` lines 3–157. |

## Material deliberately preserved

- The full English description is deliberately preserved byte-for-byte, including its original sentence order and compressed finite mappings, because all correspondences are complete and unique.
- 英文描述全文按字节保留，包括原句序及有限映射的压缩表达，因为全部对应关系完整且唯一。

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 44/44 |
| Init atoms covered | 88/88 |
| Goal atoms covered | 18/18 |
| Ledger rows | 150/150 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

The renewed atomic audit confirms that every correspondence is unique and that all deterministic rules expand to exactly the golden siblings with no unstated exception.

重新进行的逐项审计确认：每项对应关系都是唯一的，所有确定性规则都仅展开为金标同组项目，且没有未说明的例外。

**Final assertion:** missing, ambiguous, contradictory, and over-generated counts are all zero.

**最终断言：** 缺失、歧义、矛盾和过度生成计数均为零。

## p33

Case artifacts: [p33/](p33/)


Decision: REWRITE REQUIRED

A rewrite is required only for the incorrect package-count span. The localized replacement removes the confirmed defect while preserving every unaffected sentence verbatim.

仅错误的包裹数量片段需要改写。局部替换消除了已确认缺陷，同时逐字保留所有未受影响的句子。

## Source inventory and totals / 来源清单与总数

- golden_domain.pddl: authoritative predicate and action semantics; retained unchanged.
- golden_problem.pddl: authoritative objects, init, and goal; retained unchanged.
- natural_original.txt: audited source description; retained unchanged.
- Exact totals: objects 51/51; init atoms 102/102; goal atoms 19/19; semantic items 172/172.
- 精确总数：对象 51/51；初始原子 102/102；目标原子 19/19；语义项 172/172。

## Before-rewrite audit / 改写前审计

- Coverage: objects 51/51; init 102/102; goal 19/19.
- Defects: missing 0; ambiguous 1; contradictory 1; over-generated 42.
- 覆盖：对象 51/51；初始状态 102/102；目标 19/19。
- 缺陷：缺失 0；歧义 1；冲突 1；过生成 42。

The ordinary inclusive reading of obj11 to obj73 suggests 63 integer labels; only 21 are golden, so 42 unsupported labels are counted as over-generated, in addition to one ambiguous range and one contradictory count.

按 obj11 到 obj73 的普通闭区间理解会得到 63 个整数标签；黄金对象仅有 21 个，因此计入 42 个过生成标签，另有 1 个歧义范围和 1 个冲突数量。

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | We have seven packages labeled from obj11 to obj73. | We have twenty-one packages: obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, obj63, obj71, obj72, and obj73. | The original count contradicts the 21 golden package objects, and the endpoint range can suggest 42 unsupported integer labels. Explicit enumeration is the smallest safe repair.<br>原文的数量与黄金 PDDL 中的 21 个包裹对象冲突，而且端点范围可能暗示 42 个不受支持的整数标签。显式列举是最小且安全的修复。 | golden_problem.pddl:8-10,15-17,23-25,30-32,37-39,44-46,52-54: package objects<br>golden_problem.pddl:57-77: (PACKAGE OBJ11) through (PACKAGE OBJ73) |

## Material deliberately preserved / 有意保留的重要文本

- All seven truck/package initial-location sentences were retained verbatim.
  - 七个卡车/包裹初始位置句均逐字保留。
- The complete indexed city membership rule was retained verbatim.
  - 完整的索引化城市隶属规则逐字保留。
- The complete irregular goal mapping was retained verbatim.
  - 完整的不规则目标映射逐字保留。

## Post-rewrite verification / 改写后验证

- Coverage: objects 51/51; init 102/102; goal 19/19; ledger rows 172/172.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.
- 覆盖：对象 51/51；初始状态 102/102；目标 19/19；证据账本行数 172/172。
- 缺陷：缺失 0；歧义 0；冲突 0；过生成 0。

Final assertion: every golden item has direct or uniquely expandable evidence, and all missing, ambiguous, contradictory, and over-generated counts are zero.

最终断言：每个黄金项都有直接证据或可唯一展开的证据，且缺失、歧义、冲突和过生成计数均为零。

## p34

Case artifacts: [p34/](p34/)


Decision: NO REWRITE REQUIRED

The original description already provides direct, uniquely recoverable evidence for every golden object, initial-state atom, and goal atom; no contradiction or extra fact was found. It is therefore preserved byte-for-byte.

原始描述已为每个黄金对象、初始状态原子和目标原子提供直接且可唯一恢复的证据；未发现冲突或额外事实。因此原文按字节原样保留。

## Source inventory and totals / 来源清单与总数

- golden_domain.pddl: authoritative predicate and action semantics; retained unchanged.
- golden_problem.pddl: authoritative objects, init, and goal; retained unchanged.
- natural_original.txt: audited source description; retained unchanged.
- Exact totals: objects 15/15; init atoms 30/30; goal atoms 5/5; semantic items 50/50.
- 精确总数：对象 15/15；初始原子 30/30；目标原子 5/5；语义项 50/50。

## Before-rewrite audit / 改写前审计

- Coverage: objects 15/15; init 30/30; goal 5/5.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.
- 覆盖：对象 15/15；初始状态 30/30；目标 5/5。
- 缺陷：缺失 0；歧义 0；冲突 0；过生成 0。

No missing, ambiguous, contradictory, or over-generated evidence was found in the original.

原文中未发现缺失、歧义、冲突或过生成证据。

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | The original already passes the atomic audit. / 原文已通过逐项原子审计。 | golden_problem.pddl:3 objects; 4-10 init; 11-12 goal |

## Material deliberately preserved / 有意保留的重要文本

- The complete original description was preserved byte-for-byte because it already covers every golden object, init atom, and goal atom uniquely.
  - 完整原文按字节保留，因为它已唯一覆盖每个黄金对象、初始原子和目标原子。

## Post-rewrite verification / 改写后验证

- Coverage: objects 15/15; init 30/30; goal 5/5; ledger rows 50/50.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.
- 覆盖：对象 15/15；初始状态 30/30；目标 5/5；证据账本行数 50/50。
- 缺陷：缺失 0；歧义 0；冲突 0；过生成 0。

Final assertion: every golden item has direct or uniquely expandable evidence, and all missing, ambiguous, contradictory, and over-generated counts are zero.

最终断言：每个黄金项都有直接证据或可唯一展开的证据，且缺失、歧义、冲突和过生成计数均为零。

## p35

Case artifacts: [p35/](p35/)


Decision: REWRITE REQUIRED

A rewrite is required only for the incorrect package-count span. The localized replacement removes the confirmed defect while preserving every unaffected sentence verbatim.

仅错误的包裹数量片段需要改写。局部替换消除了已确认缺陷，同时逐字保留所有未受影响的句子。

## Source inventory and totals / 来源清单与总数

- golden_domain.pddl: authoritative predicate and action semantics; retained unchanged.
- golden_problem.pddl: authoritative objects, init, and goal; retained unchanged.
- natural_original.txt: audited source description; retained unchanged.
- Exact totals: objects 51/51; init atoms 102/102; goal atoms 19/19; semantic items 172/172.
- 精确总数：对象 51/51；初始原子 102/102；目标原子 19/19；语义项 172/172。

## Before-rewrite audit / 改写前审计

- Coverage: objects 51/51; init 102/102; goal 19/19.
- Defects: missing 0; ambiguous 0; contradictory 1; over-generated 0.
- 覆盖：对象 51/51；初始状态 102/102；目标 19/19。
- 缺陷：缺失 0；歧义 0；冲突 1；过生成 0。

The exact inventory covers every golden package, but its stated count of seven contradicts the 21 enumerated and golden packages.

精确清单覆盖了所有黄金包裹，但所述数量七与列出的 21 个黄金包裹冲突。

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | There are seven packages to manage: | There are twenty-one packages to manage: | The sentence explicitly lists 21 golden package objects, so changing only the incorrect count removes the contradiction.<br>该句明确列出了黄金 PDDL 中的 21 个包裹对象，因此只修改错误数量即可消除冲突。 | golden_problem.pddl:8-10,15-17,23-25,30-32,37-39,44-46,52-54: package objects<br>golden_problem.pddl:57-77: (PACKAGE OBJ11) through (PACKAGE OBJ73) |

## Material deliberately preserved / 有意保留的重要文本

- The exact package inventory after the corrected count was retained verbatim.
  - 修正数量后的精确包裹清单逐字保留。
- All vehicle and package initial placements and all fourteen city memberships were retained verbatim.
  - 所有车辆和包裹初始位置以及全部十四个城市隶属关系均逐字保留。
- The complete irregular goal mapping was retained verbatim.
  - 完整的不规则目标映射逐字保留。

## Post-rewrite verification / 改写后验证

- Coverage: objects 51/51; init 102/102; goal 19/19; ledger rows 172/172.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.
- 覆盖：对象 51/51；初始状态 102/102；目标 19/19；证据账本行数 172/172。
- 缺陷：缺失 0；歧义 0；冲突 0；过生成 0。

Final assertion: every golden item has direct or uniquely expandable evidence, and all missing, ambiguous, contradictory, and over-generated counts are zero.

最终断言：每个黄金项都有直接证据或可唯一展开的证据，且缺失、歧义、冲突和过生成计数均为零。

## p36

Case artifacts: [p36/](p36/)


Decision: NO REWRITE REQUIRED

The original description already provides direct, uniquely recoverable evidence for every golden object, initial-state atom, and goal atom; no contradiction or extra fact was found. It is therefore preserved byte-for-byte.

原始描述已为每个黄金对象、初始状态原子和目标原子提供直接且可唯一恢复的证据；未发现冲突或额外事实。因此原文按字节原样保留。

## Source inventory and totals / 来源清单与总数

- golden_domain.pddl: authoritative predicate and action semantics; retained unchanged.
- golden_problem.pddl: authoritative objects, init, and goal; retained unchanged.
- natural_original.txt: audited source description; retained unchanged.
- Exact totals: objects 51/51; init atoms 102/102; goal atoms 20/20; semantic items 173/173.
- 精确总数：对象 51/51；初始原子 102/102；目标原子 20/20；语义项 173/173。

## Before-rewrite audit / 改写前审计

- Coverage: objects 51/51; init 102/102; goal 20/20.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.
- 覆盖：对象 51/51；初始状态 102/102；目标 20/20。
- 缺陷：缺失 0；歧义 0；冲突 0；过生成 0。

No missing, ambiguous, contradictory, or over-generated evidence was found in the original.

原文中未发现缺失、歧义、冲突或过生成证据。

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | The original already passes the atomic audit. / 原文已通过逐项原子审计。 | golden_problem.pddl:3-55 objects; 56-159 init; 160-180 goal |

## Material deliberately preserved / 有意保留的重要文本

- The complete original description was preserved byte-for-byte because its explicit inventories, initial mappings, city memberships, and goal mappings already match the golden problem.
  - 完整原文按字节保留，因为其显式清单、初始映射、城市隶属关系和目标映射已与黄金问题一致。

## Post-rewrite verification / 改写后验证

- Coverage: objects 51/51; init 102/102; goal 20/20; ledger rows 173/173.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.
- 覆盖：对象 51/51；初始状态 102/102；目标 20/20；证据账本行数 173/173。
- 缺陷：缺失 0；歧义 0；冲突 0；过生成 0。

Final assertion: every golden item has direct or uniquely expandable evidence, and all missing, ambiguous, contradictory, and over-generated counts are zero.

最终断言：每个黄金项都有直接证据或可唯一展开的证据，且缺失、歧义、冲突和过生成计数均为零。

## p37

Case artifacts: [p37/](p37/)


## Decision

`REWRITE REQUIRED`

The original is complete except that “a location and an airport” does not state that each airport also has the golden `LOCATION` type. Replacing that phrase with “two locations, a position and an airport” is the smallest sufficient repair.

原文除一处外均完整：“一个地点和一个机场”没有说明每个机场同时具有黄金 PDDL 中的 `LOCATION` 类型。将其改为“两个地点，即一个位置和一个机场”是最小且充分的修复。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics.
- `golden_problem.pddl`: 51 objects (lines 3–55), 102 init atoms (lines 56–159), and 20 goal atoms (lines 160–181).
- `natural_original.txt`: original one-paragraph English description.
- Semantic total: **173** items.

## Before-rewrite coverage and defects

- Objects: **51/51** covered.
- Init: **95/102** covered; the seven `(LOCATION APT1)` through `(LOCATION APT7)` atoms were ambiguous.
- Goal: **20/20** covered.
- Missing: **0**; ambiguous: **7**; contradictory: **0**; over-generated: **0**.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `each containing a location and an airport` | `each containing two locations, a position and an airport` | Makes the airport members explicitly locations while preserving the sentence and all enumerated pairings. / 明确机场成员也属于地点，同时保留原句及全部列举关系。 | `golden_problem.pddl:92–105: (LOCATION POS1)…(LOCATION APT7)` and `golden_problem.pddl:106–112: (AIRPORT APT1)…(AIRPORT APT7)` |

## Material deliberately preserved

- The package, truck, city, airplane, initial-location, and goal enumerations were preserved verbatim because they already map directly and uniquely to the golden atoms.
- The original one-paragraph organization and logistics-game tone were preserved.

## Post-rewrite verification

- Objects: **51/51**; init: **102/102**; goal: **20/20**.
- Atomic evidence ledger: **173/173** rows covered, with one row per semantic item.
- Missing: **0**; ambiguous: **0**; contradictory: **0**; over-generated: **0**.

Final assertion: the repaired description uniquely supports every golden object, init atom, and goal atom and introduces no extra item.

## p38

Case artifacts: [p38/](p38/)


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

## p39

Case artifacts: [p39/](p39/)


## Decision

`REWRITE REQUIRED`

The package declaration both miscounts the 21 packages as seven and uses the over-generating pseudo-range `obj11` to `obj73`. The initial placement relies on “similarly” without an identifier mapping, seven airport-to-city facts are absent, and only six of 21 irregular goals are stated. A bounded inventory, one complete index rule, and a full goal list repair those defects; the unsupported efficiency implication is removed.

包裹声明把 21 个包裹误计为七个，并使用会过度生成标识符的伪范围 `obj11` 到 `obj73`。初始位置依赖没有标识符映射的“类似”表述，缺少七个机场到城市的事实，而且 21 个不规则目标中仅明确陈述了六个。用有界清单、一条完整索引规则和完整目标列表即可修复；同时删除无 PDDL 支持的效率暗示。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics.
- `golden_problem.pddl`: 51 objects (lines 3–55), 102 init atoms (lines 56–159), and 21 goal atoms (lines 160–182).
- `natural_original.txt`: original one-paragraph English description.
- Semantic total: **174** items.

## Before-rewrite coverage and defects

- Objects: **38/51** covered; 13 package identifiers lacked direct, non-over-generating evidence.
- Init: **46/102** covered; 42 unary/placement facts were ambiguous and seven airport-to-city facts were missing.
- Goal: **6/21** covered; 15 goal atoms were missing.
- Missing: **22**; ambiguous: **55**; contradictory: **1** (seven packages versus 21); over-generated: **42** pseudo-range labels.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `There are seven packages labeled from obj11 to obj73, seven trucks named tru1 to tru7, seven cities named cit1 to cit7, and seven airports, apt1 through apt7, which also serve as locations.` | `There are 21 packages: obj11, …, and obj73; seven trucks named tru1 to tru7; seven cities named cit1 to cit7; and seven airports, apt1 through apt7, which also serve as locations.` | Corrects the package count and replaces a pseudo-range with the exact 21-object inventory while retaining the valid vehicle/city/airport wording. / 修正包裹数量并用精确清单替换伪范围，同时保留正确的车辆、城市和机场表述。 | `golden_problem.pddl:4–54` (object inventory) and `golden_problem.pddl:57–77` (21 package atoms) |
| 2 | `Trucks are stationed at positions pos1 through pos7, each in their respective cities cit1 to cit7, along with three packages per position.` | `For every integer i from 1 through 7, position posi and airport apti are locations in city citi, truck trui is initially at posi, and packages obji1, obji2, and obji3 are initially at posi; in these identifiers, i is the same integer appended to pos, apt, cit, and tru and placed between obj and the package suffix 1, 2, or 3.` | Supplies complete, same-index construction for location types, all 14 city memberships, and all 28 truck/package placements. / 为地点类型、全部 14 个城市隶属关系及全部 28 个卡车/包裹位置提供完整同索引构造。 | `golden_problem.pddl:92–112`, `golden_problem.pddl:117–158` |
| 3 | `Similarly, the positions pos2 to pos7 in cities cit2 to cit7 are each associated with one truck and three packages.` | `The preceding complete rule covers indices 2 through 7 as well.` | Removes vague standalone evidence and makes clear that the finite rule—not an inferred analogy—covers the remaining indices. / 删除模糊的独立证据，并明确由有限规则覆盖其余索引。 | `golden_problem.pddl:121–158` |
| 4 | `These targets include … several other packages … For example, obj13 … obj32 … obj11 …` | `These targets are obj61 reaching apt5, …, and obj51 remaining at pos5.` | Replaces examples and a vague placeholder with all 21 irregular goal pairs. / 用全部 21 个不规则目标对替换示例和模糊占位语。 | `golden_problem.pddl:161–181` (complete goal conjunction) |
| 5 | `to meet the specified destinations efficiently` | `to meet the specified destinations` | Removes an optimization implication absent from the golden goal and domain. / 删除黄金目标与领域中不存在的优化含义。 | `golden_problem.pddl:160–182` contains only the destination conjunction; no `:metric` is present |

## Material deliberately preserved

- The opening, valid truck/city/airport ranges, explicit index-1 example, ordered airplane starts, goal introduction, and planning-oriented close were preserved.
- The original one-paragraph tone and organization were retained wherever they did not create semantic defects.

## Post-rewrite verification

- Objects: **51/51**; init: **102/102**; goal: **21/21**.
- Atomic evidence ledger: **174/174** rows covered. Expanding the rule for exactly `i = 1…7` yields 14 location names, 14 city-membership atoms, and 28 initial truck/package `AT` atoms, with no extras.
- Missing: **0**; ambiguous: **0**; contradictory: **0**; over-generated: **0**.

Final assertion: all golden items have unique direct or deterministic-rule evidence and no extra object, fact, or goal is implied.

## p40

Case artifacts: [p40/](p40/)


## Decision

`NO REWRITE REQUIRED`

The original explicitly enumerates every object, unary type, initial location, city membership, and goal destination. It contains no vague continuation, contradiction, or extra semantic item, so the proposed English description is byte-for-byte identical to the original.

原文明确列举了每个对象、一元类型、初始位置、城市隶属关系和目标目的地，不含模糊续写、矛盾或额外语义项，因此建议英文描述与原文逐字节一致。

## Source inventory

- `golden_domain.pddl`: predicate meanings and action semantics.
- `golden_problem.pddl`: 58 objects (lines 3–62), 116 init atoms (lines 63–180), and 22 goal atoms (lines 181–204).
- `natural_original.txt`: original one-paragraph English description.
- Semantic total: **196** items.

## Before-rewrite coverage and defects

- Objects: **58/58**; init: **116/116**; goal: **22/22**.
- Missing: **0**; ambiguous: **0**; contradictory: **0**; over-generated: **0**.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of `natural_original.txt`. | The original already directly and uniquely covers every golden item. / 原文已经直接且唯一地覆盖全部黄金项。 | `golden_problem.pddl:3–204` |

## Material deliberately preserved

- The complete original description was deliberately preserved because every inventory, initial-state statement, city mapping, and goal statement is exact.

## Post-rewrite verification

- Objects: **58/58**; init: **116/116**; goal: **22/22**.
- Atomic evidence ledger: **196/196** rows covered, all by direct statements.
- `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`.
- Missing: **0**; ambiguous: **0**; contradictory: **0**; over-generated: **0**.

Final assertion: all golden items are uniquely covered and all four defect counts are zero.

## p41

Case artifacts: [p41/](p41/)


## Decision

`NO REWRITE REQUIRED`

## Finding / 结论

The original description directly and uniquely covers every golden object, initial-state atom, and goal atom. It contains no contradiction or extra fact, so rewriting would be stylistic rather than corrective.

原始描述直接且唯一地覆盖了每个黄金对象、初始状态原子和目标原子，也没有矛盾或额外事实，因此改写只会是文体变化而非必要修复。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics.
- `golden_problem.pddl`: 58 objects, 116 init atoms, and 22 goal atoms.
- `natural_original.txt`: original English description audited before the decision.
- Semantic-item total: 196.

## Before-rewrite coverage

| Measure | Count |
|---|---:|
| Objects covered | 58/58 |
| Init atoms covered | 116/116 |
| Goal atoms covered | 22/22 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed | No text changed | The original already passes the complete atomic audit; byte-for-byte preservation is required. / 原文已通过完整逐项审计，必须逐字节保留。 | `golden_problem.pddl:3-61` objects; `64-179` init; `182-203` goal |

## Material deliberately preserved

- The complete original English description, including every explicit object/type list, all initial placements and city memberships, and all 22 goal pairs.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 58/58 |
| Init atoms covered | 116/116 |
| Goal atoms covered | 22/22 |
| Ledger rows | 196/196 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Final assertion: every golden object, init atom, and goal atom has unique direct or deterministic-rule evidence in `natural_rewritten.txt`; deterministic rules expand to exactly the golden items, with zero omissions, ambiguity, contradictions, or over-generation.

## p42

Case artifacts: [p42/](p42/)


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

## p43

Case artifacts: [p43/](p43/)


## Decision

`REWRITE REQUIRED`

## Finding / 结论

The original description covered the inventories, placements, and complete goal, but it did not directly state that apt1–apt8 satisfy the independent location type and used “scattered across” instead of a unique airport-to-city mapping. Two local phrase replacements repair those defects.

原始描述覆盖了清单、位置和完整目标，但没有直接说明 apt1–apt8 满足独立的地点类型事实，并以“散布在”代替唯一的机场到城市映射。两处局部短语替换修复了这些问题。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics.
- `golden_problem.pddl`: 58 objects, 116 init atoms, and 23 goal atoms.
- `natural_original.txt`: original English description audited before the decision.
- Semantic-item total: 197.

## Before-rewrite coverage

| Measure | Count |
|---|---:|
| Objects covered | 58/58 |
| Init atoms covered | 100/116 |
| Goal atoms covered | 23/23 |
| Missing | 0 |
| Ambiguous | 16 |
| Contradictory | 0 |
| Over-generated | 0 |

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | an airport (apt1 through apt8) | an airport location (apt1 through apt8) | Adding “location” directly supports the independent LOCATION facts for apt1–apt8 while preserving their airport type. / 添加“地点”一词，可直接支持 apt1–apt8 各自独立的 LOCATION 事实，同时保留其机场类型。 | `golden_problem.pddl:105,107,109,111,113,115,117,119 ((LOCATION APT1) through (LOCATION APT8))`<br>`golden_problem.pddl:120-127 ((AIRPORT APT1) through (AIRPORT APT8))` |
| 2 | Airports apt1 through apt8 are scattered across cities cit1 to cit8. | Airports apt1 through apt8 are in cities cit1 through cit8, respectively. | “Scattered across” did not uniquely map each airport to a city. Ordered ranges plus “respectively” uniquely map aptN to citN. / “散布在”无法唯一确定每个机场所属的城市；有序范围加“分别”可唯一确定 aptN 到 citN 的映射。 | `golden_problem.pddl:165,167,169,171,173,175,177,179 ((IN-CITY APT1 CIT1) through (IN-CITY APT8 CIT8))` |

## Material deliberately preserved

- The complete package inventory, vehicle inventory, airplane placements, truck/package placements, position-to-city rule, and 23-pair goal enumeration.
- The original sentence structure and wording outside the two defective spans.

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

## p44

Case artifacts: [p44/](p44/)


## Decision

`NO REWRITE REQUIRED`

## Finding / 结论

The original description directly and uniquely covers every golden object, initial-state atom, and goal atom. It contains no contradiction or extra fact, so rewriting would be stylistic rather than corrective.

原始描述直接且唯一地覆盖了每个黄金对象、初始状态原子和目标原子，也没有矛盾或额外事实，因此改写只会是文体变化而非必要修复。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics.
- `golden_problem.pddl`: 58 objects, 116 init atoms, and 24 goal atoms.
- `natural_original.txt`: original English description audited before the decision.
- Semantic-item total: 198.

## Before-rewrite coverage

| Measure | Count |
|---|---:|
| Objects covered | 58/58 |
| Init atoms covered | 116/116 |
| Goal atoms covered | 24/24 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed | No text changed | The original already passes the complete atomic audit; byte-for-byte preservation is required. / 原文已通过完整逐项审计，必须逐字节保留。 | `golden_problem.pddl:3-61` objects; `64-179` init; `182-205` goal |

## Material deliberately preserved

- The complete original English description, including every explicit object/type list, all initial placements and city memberships, and all 24 goal pairs.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 58/58 |
| Init atoms covered | 116/116 |
| Goal atoms covered | 24/24 |
| Ledger rows | 198/198 |
| Missing | 0 |
| Ambiguous | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Final assertion: every golden object, init atom, and goal atom has unique direct or deterministic-rule evidence in `natural_rewritten.txt`; deterministic rules expand to exactly the golden items, with zero omissions, ambiguity, contradictions, or over-generation.

## p45

Case artifacts: [p45/](p45/)


## Decision

`NO REWRITE REQUIRED`

The original description already gives a direct, unique counterpart for every object, type fact, initial-state atom, and goal atom; it contains no contradiction or over-generation, so it is preserved byte-for-byte.  
原描述已经为每个对象、类型事实、初始状态原子和目标原子提供了直接且唯一的对应表述；不存在矛盾或过度生成，因此逐字节保留原文。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 15 objects, 30 init atoms, and 5 goal atoms (50 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 15/15; init 30/30; goal 5/5.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of the original. | Every semantic item was already explicit and uniquely recoverable. / 每个语义项均已明确且可唯一恢复。 | Objects: line 3; init: lines 4–10; goal: lines 11–12. |

## Material deliberately preserved

- The complete package, truck, city, location, airport, and airplane inventory was preserved because it matches the golden objects and unary facts.
- Both initial-location sentences and the complete goal sentence were preserved because each mapping is direct and exact.
- The original tone and single-paragraph organization were preserved because no semantic repair was needed.

## Post-decision verification

- Coverage: objects 15/15; init 30/30; goal 5/5; ledger 50/50 rows.
- Every direct mapping was re-checked against `golden_problem.pddl` lines 3–12.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## p46

Case artifacts: [p46/](p46/)


## Decision

`NO REWRITE REQUIRED`

The original description exhaustively enumerates the object inventory, every initial fact, and every irregular goal pair. All correspondences are direct and unique, so no rewrite is justified.  
原描述完整枚举了对象清单、每个初始事实以及每个不规则目标对应关系。所有对应关系都直接且唯一，因此无需改写。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics (85 lines).
- `golden_problem.pddl`: 58 objects, 116 init atoms, and 24 goal atoms (198 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 58/58; init 116/116; goal 24/24.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of the original. | Exhaustive direct enumeration already passes the atomic audit. / 完整的直接枚举已通过原子级审计。 | Objects: lines 3–62; init: lines 63–180; goal: lines 181–206. |

## Material deliberately preserved

- All inventory sentences were preserved because their lists exactly match the golden objects and unary facts.
- All airplane, truck, package, and location-to-city initial mappings were preserved because they are exhaustive and exact.
- The full goal list and original prose organization were preserved because the irregular mapping is already complete.

## Post-decision verification

- Coverage: objects 58/58; init 116/116; goal 24/24; ledger 198/198 rows.
- Every item was re-checked against `golden_problem.pddl` lines 3–206.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## p47

Case artifacts: [p47/](p47/)


## Decision

`REWRITE REQUIRED`

The object lists and relational mappings are complete, but the opening sentence says there are only nine packages and only nine locations. The golden problem has 27 packages and 18 location-typed objects (nine positions plus the nine airports). Two local count repairs remove the contradictions and directly support every location type fact; all other wording remains unchanged.  
对象列表和关系映射均完整，但开头句称只有九个包裹和九个地点。黄金问题实际包含 27 个包裹和 18 个具有地点类型的对象（九个普通位置加九个机场）。两处局部数量修正消除了矛盾，并直接支持每个地点类型事实；其余文字均保持不变。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics (85 lines).
- `golden_problem.pddl`: 66 objects, 132 init atoms, and 25 goal atoms (223 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 66/66; init 123/132; goal 25/25.
- Defects: missing 0; ambiguous 9 (the nine `(location aptX)` facts were not directly recoverable from the stated nine-location count); contradictory 2 (package count and location count); over-generated 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| 1 | `nine packages` | `twenty-seven packages` | Correct the contradicted package count while preserving the explicit package list. / 修正与黄金问题矛盾的包裹数量，同时保留明确清单。 | Package objects: lines 9–11, 16–18, 23–25, 30–32, 38–40, 45–47, 52–54, 59–61, 67–69; `(PACKAGE ...)`: lines 72–98. |
| 2 | `nine locations, nine airports` | `eighteen locations (the nine positions and nine airports)` | State that all nine airports are also among the 18 location-typed objects. / 明确九个机场也属于 18 个地点类型对象。 | Position and airport objects: lines 5–6, 12–13, 19–20, 26–27, 34–35, 41–42, 48–49, 55–56, 63–64; `(LOCATION ...)`: lines 117–134; `(AIRPORT ...)`: lines 135–143. |

## Material deliberately preserved

- The exhaustive package list and bounded truck/city/location identifiers were preserved because they already match all golden objects.
- The airplane mapping, every truck/package initial-location mapping, and the `posX`/`aptX` to `citX` rule were preserved because each is complete and unique.
- The complete irregular goal sentence and all surrounding prose were preserved verbatim.

## Post-rewrite verification

- Coverage: objects 66/66; init 132/132; goal 25/25; ledger 223/223 rows.
- The ranges were expanded for X=1 through X=9: 9 trucks, 9 cities, 18 locations, 9 airports, and exactly 18 `in-city` atoms, with no extra identifier or relation.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## p48

Case artifacts: [p48/](p48/)


## Decision

`REWRITE REQUIRED`

The goal and airplane locations are complete, but the original phrase “corresponding vehicles and packages” neither names the full package/truck inventory nor defines their initial-location correspondence. It also leaves most location-to-city mappings non-unique. Replacing that one sentence with a finite X=1..9 construction supplies exactly the missing object, type, initial-location, and city-membership evidence.  
目标和飞机位置已经完整，但原文“对应的车辆和包裹”既未给出完整的包裹/卡车清单，也未定义其初始位置对应关系，并且使大多数地点到城市的映射不唯一。仅用一个有限的 X=1..9 构造规则替换该句，即可精确补足缺失的对象、类型、初始位置和城市隶属证据。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics (85 lines).
- `golden_problem.pddl`: 66 objects, 132 init atoms, and 25 goal atoms (223 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 57/66; init 79/132; goal 25/25.
- Defects: missing 18 (9 unnamed objects and their 9 unary type facts); ambiguous 44 (28 unspecified truck/package initial positions and 16 non-unique location-to-city facts); contradictory 0; over-generated 0.
- The six explicitly named packages, tru1/tru2, all goal pairs, and all three airplane locations were credited; the vague word “corresponding” was not expanded by guesswork.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| 1 | `Each city from cit1 to cit9 has a position and an airport location (apt1 to apt9) with corresponding vehicles and packages.` | `For each integer X from 1 through 9, citX is a city, posX and aptX are locations in citX, aptX is an airport, truX is a truck, and objX1, objX2, and objX3 are packages; initially, truX and those three packages are at posX.` | Replace an undefined correspondence with one bounded construction whose substitutions are explicit. / 用一个替换范围和对应关系均明确的有限构造替代未定义的“对应”。 | Object families: lines 4–69; unary facts: lines 72–146; truck/package positions: lines 150–185; city memberships: lines 186–203. |

## Material deliberately preserved

- The introductory sentence and the explicit cit1/cit2 examples were preserved because they are compatible with and illustrate the repaired rule.
- The airplane sentence was preserved because its ordered `respectively` mapping exactly matches lines 147–149.
- All six goal sentences were preserved verbatim because together they enumerate exactly the 25 goal atoms at lines 206–230.

## Post-rewrite verification

- Coverage: objects 66/66; init 132/132; goal 25/25; ledger 223/223 rows.
- Expanding X=1 through X=9 yields exactly 9 cities, 18 locations, 9 airports, 9 trucks, 27 packages, 18 `in-city` atoms, 9 truck-position atoms, and 27 package-position atoms. The airplane sentence adds exactly 3 airplanes and 3 airplane-position atoms.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## p49

Case artifacts: [p49/](p49/)


## Decision

`NO REWRITE REQUIRED`

The original description directly and exhaustively enumerates every object, unary type fact, initial-state atom, and irregular goal pair. All correspondences are unique, and no statement contradicts or over-generates the golden PDDL, so the original is preserved byte-for-byte.  
原描述直接且完整地枚举了每个对象、一元类型事实、初始状态原子以及不规则目标对应关系。所有对应关系均唯一，也没有任何陈述与黄金 PDDL 矛盾或产生额外事实，因此逐字节保留原文。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 66 objects, 132 init atoms, and 26 goal atoms (224 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 66/66; init 132/132; goal 26/26.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of the original. | Every semantic item was already explicit and uniquely recoverable. / 每个语义项均已明确且可唯一恢复。 | Objects: lines 4–69; init: lines 72–203; goal: lines 206–231. |

## Material deliberately preserved

- The exhaustive package, truck, airplane, city, location, and airport inventory was preserved because it exactly matches the golden objects and unary facts.
- Every airplane, truck, package, and location-to-city initial mapping was preserved because each is directly and completely enumerated.
- The full irregular goal sentence and the original one-paragraph organization were preserved because all 26 goal pairs are exact.

## Post-decision verification

- Coverage: objects 66/66; init 132/132; goal 26/26; ledger 224/224 rows.
- Every item was independently re-checked against `golden_problem.pddl` lines 4–231; the direct lists introduce no identifier or atom absent from the golden problem.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## p50

Case artifacts: [p50/](p50/)


## Decision

`NO REWRITE REQUIRED`

The original description directly and exhaustively enumerates every object, unary type fact, initial-state atom, and irregular goal pair. All correspondences are unique, and no statement contradicts or over-generates the golden PDDL, so the original is preserved byte-for-byte.  
原描述直接且完整地枚举了每个对象、一元类型事实、初始状态原子以及不规则目标对应关系。所有对应关系均唯一，也没有任何陈述与黄金 PDDL 矛盾或产生额外事实，因此逐字节保留原文。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 66 objects, 132 init atoms, and 26 goal atoms (224 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 66/66; init 132/132; goal 26/26.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of the original. | Every semantic item was already explicit and uniquely recoverable. / 每个语义项均已明确且可唯一恢复。 | Objects: lines 4–69; init: lines 72–203; goal: lines 206–231. |

## Material deliberately preserved

- The exhaustive package, truck, airplane, city, location, and airport inventory was preserved because it exactly matches the golden objects and unary facts.
- Every airplane, truck, package, and location-to-city initial mapping was preserved because each is directly and completely enumerated.
- The full irregular goal sentence and the original one-paragraph organization were preserved because all 26 goal pairs are exact.

## Post-decision verification

- Coverage: objects 66/66; init 132/132; goal 26/26; ledger 224/224 rows.
- Every item was independently re-checked against `golden_problem.pddl` lines 4–231; the direct lists introduce no identifier or atom absent from the golden problem.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## p51

Case artifacts: [p51/](p51/)


## Decision

`REWRITE REQUIRED`

The original package pseudo-range can denote 56 nonexistent integer labels, the weakening word “various” does not establish all nine trucks, and “and so forth” leaves six truck positions and 21 package positions without a unique expansion. It also fails to state unambiguously that every airport is a location and describes the last three packages as contained in tru9. Replacing only the three defective sentences with bounded X=1..9 rules repairs those families while preserving every correct airplane, city-membership, and goal statement.  
原文中的包裹伪范围可能表示 56 个不存在的整数标签；弱化词“various”不能确定全部九辆卡车；“and so forth”也无法唯一展开六辆卡车和 21 个包裹的初始位置。此外，原文没有明确说明每个机场也是地点，并把最后三个包裹描述为装在 tru9 中。仅将这三处有缺陷的句子替换为 X=1..9 的有限规则，即可修复这些事实族，同时保留所有正确的飞机位置、城市隶属关系和目标陈述。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics (85 lines; predicate `(in ?obj ?obj)` at line 14 distinguishes containment from `(at ?obj ?loc)` at line 13).
- `golden_problem.pddl`: 66 objects, 132 init atoms, and 27 goal atoms (225 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 60/66; init 90/132; goal 27/27.
- Defects: missing 0; ambiguous 48; contradictory 0; over-generated 115.
- The 48 non-unique golden items are six truck objects, six truck type facts, nine airport `LOCATION` facts, six truck-position atoms, and 21 package-position atoms. The pseudo-range `obj11` to `obj93` suggests 56 extra object labels and 56 extra `PACKAGE` atoms; “tru9 ... containing” additionally suggests three non-golden `IN` atoms.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| 1 | `Packages are labeled from obj11 to obj93, with various trucks from tru1 to tru9, and cities from cit1 to cit9.` | `Packages are labeled objX1, objX2, and objX3 for each integer X from 1 through 9, with trucks tru1 through tru9 and cities cit1 through cit9.` | Replace the over-generating package pseudo-range and weakened truck inventory with exact bounded constructions; keep the correct city range. / 用精确的有限构造替换会过度生成的包裹伪范围和被弱化的卡车清单，并保留正确的城市范围。 | Package objects: lines 9–11, 16–18, 23–25, 30–32, 38–40, 45–47, 52–54, 59–61, 67–69; truck/city objects: lines 7–8, 14–15, 21–22, 28–29, 36–37, 43–44, 50–51, 57–58, 65–66; `(PACKAGE ...)`: lines 72–98; `(TRUCK ...)`: lines 99–107; `(CITY ...)`: lines 108–116. |
| 2 | `Each city contains specific locations, named as pos1 to pos9, and airports apt1 to apt9, with apt1 to apt9 designated as airports containing airplanes apn1 to apn3.` | `The locations are pos1 through pos9 and apt1 through apt9, with apt1 through apt9 designated as airports and apn1 through apn3 designated as airplanes.` | State the two exact location families and their types without implying that the airplanes are contained in the airports. / 明确两个地点族及其类型，且不再暗示飞机被装在机场中。 | Location/airport/airplane objects: lines 4–6, 12–13, 19–20, 26–27, 33–35, 41–42, 48–49, 55–56, 62–64; `(LOCATION ...)`: lines 117–134; `(AIRPORT ...)`: lines 135–143; `(AIRPLANE ...)`: lines 144–146. |
| 3 | `Trucks and packages are placed at the corresponding positions: tru1 is at pos1 with packages obj11, obj12, and obj13; tru2 is at pos2 with obj21, obj22, and obj23, and so forth up to tru9 at pos9 containing obj91, obj92, and obj93.` | `Trucks and packages are placed at the corresponding positions: for each integer X from 1 through 9, truX and packages objX1, objX2, and objX3 are at posX.` | Replace the prohibited vague continuation and containment wording with one finite same-index rule for all trucks and packages. / 用一个覆盖全部卡车和包裹的有限同索引规则替换被禁止的模糊续写和包含关系措辞。 | Truck/package initial positions: lines 150–185, exactly `(AT TRU1 POS1)` through `(AT TRU9 POS9)` and the three same-prefix package atoms at each position. |

## Material deliberately preserved

- The opening sentence was preserved because its broad inventory categories are compatible with the exact repaired inventories.
- The airplane-location sentence was preserved verbatim because it exactly supplies `(AT APN1 APT9)`, `(AT APN2 APT4)`, and `(AT APN3 APT9)` at lines 147–149.
- The bounded `respectively` city-membership sentence was preserved because it expands to exactly the 18 `(IN-CITY ...)` atoms at lines 186–203.
- The complete irregular goal sentence was preserved verbatim because it directly enumerates all 27 goal atoms at lines 206–232.

## Post-rewrite verification

- Coverage: objects 66/66; init 132/132; goal 27/27; ledger 225/225 rows.
- Expanding X=1 through X=9 yields exactly 27 packages, nine trucks, nine cities, 18 locations, nine airports, nine truck-position atoms, and 27 package-position atoms. The separate airplane and `respectively` sentences yield exactly three airplane positions and 18 city-membership atoms.
- The renewed item-by-item ledger check found no unstated exception, alternative correspondence, extra identifier, or extra relation.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## p52

Case artifacts: [p52/](p52/)


## Decision

`NO REWRITE REQUIRED`

The original description directly and exhaustively enumerates every object, unary type fact, initial-state atom, and irregular goal pair. All correspondences are unique, and no statement contradicts or over-generates the golden PDDL, so the original is preserved byte-for-byte.  
原描述直接且完整地枚举了每个对象、一元类型事实、初始状态原子以及不规则目标对应关系。所有对应关系均唯一，也没有任何陈述与黄金 PDDL 矛盾或产生额外事实，因此逐字节保留原文。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 66 objects, 132 init atoms, and 27 goal atoms (225 semantic items total).
- `natural_original.txt`: one-paragraph original description.

## Before-rewrite audit

- Coverage: objects 66/66; init 132/132; goal 27/27.
- Defects: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## Change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of the original. | Every semantic item was already explicit and uniquely recoverable. / 每个语义项均已明确且可唯一恢复。 | Objects: lines 4–69; init: lines 72–203; goal: lines 206–232. |

## Material deliberately preserved

- The exhaustive package, truck, airplane, city, location, and airport inventory was preserved because it exactly matches the golden objects and unary facts.
- Every airplane, truck, package, and location-to-city initial mapping was preserved because each is directly and completely enumerated.
- The full irregular goal sentence and the original one-paragraph organization were preserved because all 27 goal pairs are exact.

## Post-decision verification

- Coverage: objects 66/66; init 132/132; goal 27/27; ledger 225/225 rows.
- Every item was independently re-checked against `golden_problem.pddl` lines 4–232; the direct lists introduce no identifier or atom absent from the golden problem.
- Final assertion: missing 0; ambiguous 0; contradictory 0; over-generated 0.

## p53

Case artifacts: [p53/](p53/)


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

## p54

Case artifacts: [p54/](p54/)


## Decision

REWRITE REQUIRED

The original goal list and airplane placements are correct, but the package pseudo-range over-generates identifiers, all truck/package initial locations are unspecified, seven airport type facts are absent, and the location-to-city correspondence is vague. Four local edits supply exact finite rules and repair the single spaced identifier apt 10.

原文的目标列表和飞机位置正确，但包裹伪范围会多生成标识符，所有卡车和包裹的初始位置均未指定，缺少七个机场类型事实，而且地点到城市的对应关系含糊。四处局部修改补充了精确的有限规则，并修正了带空格的标识符 apt 10。

## Source inventory and totals

- golden_domain.pddl: logistics predicate and action semantics.
- golden_problem.pddl: 73 objects, 146 init atoms, and 28 goal atoms; 247 semantic items total.
- natural_original.txt: original English description.

## Before-rewrite audit

- Object coverage: 71/73. Obj62 and obj81 occur only inside the over-generating pseudo-range.
- Init coverage: 77/146. Sixty-two init atoms are ambiguous (two package type facts, 40 truck/package placements, and 20 in-city atoms), and seven airport type facts are missing.
- Goal coverage: 28/28; apt 10 is uniquely intended as apt10 but is repaired to preserve the exact identifier.
- Defects across golden semantic items: missing 7; ambiguous 64; contradictory 0.
- Over-generated items: 63 non-golden package identifiers suggested by treating obj11 through obj103 as an integer range.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | In the Logistics game, we start with the following initial conditions: We have several packages including obj11 through obj103, and trucks tru1 through tru10. | In the Logistics game, we start with the following initial conditions: for every index i from 1 through 10, the three package labels are formed by writing obj, then i, then 1, 2, or 3, and the trucks are tru1 through tru10. | The pseudo-range is not the exact 30-object family; the bounded construction is exact. / 伪范围并非准确的 30 个对象集合；有限构造恰好匹配。 | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47,52-54,59-61,66-68,74-76 (OBJ declarations); 79-118 (PACKAGE and TRUCK type facts). |
| 2 | Each package and truck is located in a specific position or city. | Initially, for every index i from 1 through 10, tru followed by i and the three package labels formed by writing obj, then i, then 1, 2, or 3 are all at pos followed by the same i. | The original asserts locations without giving any object-location correspondence; the rule expands to exactly 40 AT atoms. / 原句声称存在位置却没有给出对象到地点的对应；该规则恰好展开为 40 个 AT 原子。 | golden_problem.pddl:165-204 (all truck and package (AT ...) atoms). |
| 3 | apt 10 | apt10 | The space breaks the exact golden identifier; the local edit makes the goal pair literal and unique. / 空格破坏了黄金标识符的精确形式；局部修改使目标对直接且唯一。 | golden_problem.pddl:241: (AT OBJ61 APT10). |
| 4 | Each location including pos1 through pos10 and apt1 through apt10, is situated in various cities, from cit1 to cit10. | Each location, including pos1 through pos10 and apt1 through apt10, is situated in a city from cit1 through cit10: for every index i from 1 through 10, pos followed by i and apt followed by i are both in cit followed by the same i, and each of apt1 through apt10 is an airport. | Various cities gives no correspondence and only apt1, apt6, and apt9 were called airports; the finite same-index rule and airport range supply exactly the missing facts. / “若干城市”没有给出对应关系，且原文只称 apt1、apt6 和 apt9 为机场；有限同索引规则和机场范围恰好补齐事实。 | golden_problem.pddl:119-158 (CITY, LOCATION, AIRPORT facts); 205-224 (all IN-CITY atoms). |

## Deliberately preserved

- The airplane sentence remains verbatim because it identifies all three airplanes, their airport type evidence, and their ordered initial positions correctly. / 飞机句逐字保留，因为它正确给出了三架飞机、相关机场类型证据和有序初始位置。
- The complete 28-pair goal sentence is preserved apart from removing the internal space in apt10. / 完整的 28 对目标句除删除 apt10 内部空格外均予保留。
- The closing constraint sentence and single-paragraph organization remain unchanged. / 结尾约束句和单段结构保持不变。

## Post-rewrite verification

- Object coverage: 73/73.
- Init coverage: 146/146.
- Goal coverage: 28/28.
- Atomic ledger: 247/247 rows covered with unique evidence.
- Missing 0; ambiguous 0; contradictory 0; over-generated 0.

Final assertion: every golden item is uniquely recoverable from the revised English description, and no non-golden item is generated.

最终断言：修订后的英文描述可唯一恢复每个黄金语义项，且不会生成任何非黄金语义项。

## p55

Case artifacts: [p55/](p55/)


## Decision

NO REWRITE REQUIRED

The original description explicitly and exactly identifies every object, type fact, initial location, location-to-city relation, and all 29 goal atoms. It contains no ambiguity, contradiction, or over-generation, so natural_rewritten.txt is byte-for-byte identical to natural_original.txt.

原描述明确且准确地给出了每个对象、类型事实、初始位置、地点到城市的关系以及全部 29 个目标原子。文本不存在歧义、矛盾或过度生成，因此 natural_rewritten.txt 与 natural_original.txt 逐字节相同。

## Source inventory and totals

- golden_domain.pddl: logistics predicate and action semantics.
- golden_problem.pddl: 73 objects, 146 init atoms, and 29 goal atoms; 248 semantic items total.
- natural_original.txt: original and final English description.

## Before-rewrite audit

- Object coverage: 73/73.
- Init coverage: 146/146.
- Goal coverage: 29/29.
- Missing 0; ambiguous 0; contradictory 0; over-generated 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | The original already passes the complete atomic audit. / 原文已通过完整的逐项原子审计。 | golden_problem.pddl:4-76 (73 objects); 79-224 (146 init atoms); 227-255 (29 goal atoms). |

## Deliberately preserved

- The complete English description is preserved verbatim because every list and mapping is direct, finite, exhaustive, and golden-consistent. / 完整英文描述逐字保留，因为每个列表和映射都直接、有限、穷尽且与黄金文件一致。

## Post-rewrite verification

- Object coverage: 73/73.
- Init coverage: 146/146.
- Goal coverage: 29/29.
- Atomic ledger: 248/248 rows covered with unique evidence.
- Missing 0; ambiguous 0; contradictory 0; over-generated 0.

Final assertion: every golden item is uniquely recoverable from the unchanged English description, and no non-golden item is generated.

最终断言：未改动的英文描述可唯一恢复每个黄金语义项，且不会生成任何非黄金语义项。

## p56

Case artifacts: [p56/](p56/)


## Decision

NO REWRITE REQUIRED

The original description directly names all 15 objects, states every one of the 30 init atoms, and gives all five conjunctive goal atoms. The finite lists make each correspondence unique, so natural_rewritten.txt is byte-for-byte identical to natural_original.txt.

原描述直接列出全部 15 个对象，陈述全部 30 个初始原子，并给出五个合取目标原子。有限列表使每个对应关系均唯一，因此 natural_rewritten.txt 与 natural_original.txt 逐字节相同。

## Source inventory and totals

- golden_domain.pddl: logistics predicate and action semantics.
- golden_problem.pddl: 15 objects, 30 init atoms, and 5 goal atoms; 50 semantic items total.
- natural_original.txt: original and final English description.

## Before-rewrite audit

- Object coverage: 15/15.
- Init coverage: 30/30.
- Goal coverage: 5/5.
- Missing 0; ambiguous 0; contradictory 0; over-generated 0.

## Changes

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | No text changed. | The original already passes the complete atomic audit. / 原文已通过完整的逐项原子审计。 | golden_problem.pddl:3 (15 objects); 4-10 (30 init atoms); 11-12 (5 goal atoms). |

## Deliberately preserved

- The complete English description is preserved verbatim because its short finite lists directly cover every type, placement, city membership, airport designation, and goal. / 完整英文描述逐字保留，因为其简短有限列表直接涵盖每个类型、位置、城市归属、机场指定和目标。

## Post-rewrite verification

- Object coverage: 15/15.
- Init coverage: 30/30.
- Goal coverage: 5/5.
- Atomic ledger: 50/50 rows covered with unique evidence.
- Missing 0; ambiguous 0; contradictory 0; over-generated 0.

Final assertion: every golden item is uniquely recoverable from the unchanged English description, and no non-golden item is generated.

最终断言：未改动的英文描述可唯一恢复每个黄金语义项，且不会生成任何非黄金语义项。

## p57

Case artifacts: [p57/](p57/)


## Decision

`REWRITE REQUIRED`

The original uses the over-generating pseudo-range `obj11` through `obj103`, leaves the regular package placements and indexed city memberships non-unique, and states only six of 29 irregular goals. It also suggests city-valued package targets and an efficiency objective that do not occur in the golden PDDL. Exact finite construction rules repair the regular families, while the complete goal conjunction is enumerated.

原描述使用会过度生成标识符的伪范围 `obj11` 到 `obj103`，没有唯一确定规则性的包裹初始位置与按索引对应的城市隶属关系，并且 29 个不规则目标中只明确陈述了 6 个。原文还暗示黄金 PDDL 中不存在的以城市为包裹目标以及效率优化目标。精确的有限构造规则修复规则性事实，完整目标合取则逐项列出。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 73 objects on lines 4–76; 146 init atoms on lines 79–224; 29 goal atoms on lines 227–255.
- `natural_original.txt`: original three-paragraph English description.
- Exact totals: objects 73; init 146; goal 29; semantic items 248.

## Before-rewrite coverage and defects

- Objects covered: 72/73; `obj82` had no direct, non-over-generating occurrence.
- Init atoms covered: 98/146; 27 non-example package placements, 20 indexed city-membership atoms, and the `obj82` package typing lacked unique evidence.
- Goal atoms covered: 6/29; only the six named examples had exact destinations.
- Missing: 23 goal atoms.
- Ambiguous: 49 semantic items (one object, 28 package type/placement items, and 20 city memberships).
- Contradictory: 2 unsupported claims (city-valued package targets and efficiency optimization).
- Over-generated: 63 non-golden package identifiers under the literal integer-range reading of `obj11` through `obj103`.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `Initially, I have packages labeled obj11 through obj103 distributed in various positions.` | `For each integer i from 1 through 10, I have exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3; for example, i=1 gives obj11, obj12, and obj13, while i=10 gives obj101, obj102, and obj103.` | Replaces the pseudo-range with a bounded identifier construction that expands to exactly 30 package objects and package types. / 用有界标识符构造替换伪范围，恰好展开为 30 个包裹对象及其包裹类型。 | Package objects: `golden_problem.pddl:8–10,16–18,23–25,30–32,37–39,45–47,52–54,59–61,66–68,74–76`; `(PACKAGE ...)`: lines 79–108. |
| 2 | `I've got specific locations like pos1 to pos10 and airports from apt1 to apt10, with their corresponding city affiliations as cit1 through cit10.` | `For each integer i from 1 through 10, pos{i} and apt{i} are locations in cit{i}, and apt{i} is an airport, where every {i} is replaced by the same decimal integer.` | Removes `like` and defines every location type, airport type, and same-index city membership without guessing. / 删除 `like`，并无须猜测地定义全部地点类型、机场类型与同索引城市隶属关系。 | `(LOCATION ...)`: `golden_problem.pddl:129–148`; `(AIRPORT ...)`: lines 149–158; `(IN-CITY ...)`: lines 205–224. |
| 3 | `For the trucks, tru1 through tru10 are at pos1 through pos10 respectively, each with a few packages.` | `For each integer i from 1 through 10, tru{i} is at pos{i}, and the three packages obj{i}1, obj{i}2, and obj{i}3 are at pos{i}, where every {i} is replaced by the same decimal integer.` | Retains the valid truck mapping and supplies the previously unstated complete package mapping. / 保留正确的卡车映射并补充原先未说明的完整包裹映射。 | Truck/package placements: `golden_problem.pddl:165–204`. |
| 4 | `specific items are relocated to other designated positions` | `specific items are at their designated locations` | Avoids implying that every package moves or that airport goals are not locations. / 避免暗示每个包裹都必须移动或机场目标不是地点。 | Goal conjunction includes unchanged initial locations at lines 227, 235, and 253 and airport targets throughout lines 228–255. |
| 5 | `For instance, I want obj63 to remain at pos6, obj93 to move to apt2, and obj72 to relocate to pos8. Some packages need to change airports or positions, such as obj12 to apt10, obj92 to apt10, and obj41 to apt4. Other packages need adjustments similarly, with clear targets of either city, airport, or position outlined.` | `The complete goal is that all of the following package locations hold simultaneously: obj63 at pos6; obj93 at apt2; obj72 at pos8; obj92 at apt10; obj41 at apt4; obj73 at pos9; obj12 at apt10; obj43 at apt5; obj53 at pos5; obj11 at pos4; obj101 at pos7; obj52 at pos10; obj91 at apt4; obj81 at apt8; obj13 at pos10; obj71 at apt1; obj61 at apt2; obj33 at apt9; obj42 at pos6; obj103 at apt4; obj83 at pos2; obj23 at pos3; obj31 at apt6; obj21 at pos6; obj102 at pos6; obj22 at apt2; obj51 at pos5; obj62 at pos4; and obj32 at apt2.` | Replaces examples, vague continuation, and the unsupported city-target suggestion with all 29 irregular goal pairs as a simultaneous conjunction. / 用全部 29 个须同时成立的不规则目标对替换示例、模糊续写和无支持的城市目标暗示。 | Complete goal conjunction: `golden_problem.pddl:226–256`, with atoms on lines 227–255. |
| 6 | `meet the problem’s requirements efficiently` | `meet the problem’s requirements` | Removes an optimization implication absent from the goal and domain. / 删除目标与领域中不存在的优化含义。 | `golden_problem.pddl:226–256` contains only a conjunction and no `:metric`; `golden_domain.pddl:4–85` defines no optimization criterion. |

## Material deliberately preserved

- The opening, first-person voice, three-paragraph organization, valid truck/airplane/city ranges, and exact airplane placements.
- The correct `tru1`/`obj11`–`obj13` example and the non-semantic planning-oriented close apart from `efficiently`.
- All unaffected wording was retained verbatim.

## Post-rewrite verification

- Objects covered: 73/73.
- Init atoms covered: 146/146.
- Goal atoms covered: 29/29.
- Evidence ledger rows: 248/248.
- Expanding each rule for exactly `i = 1…10` yields 30 package names, 20 location names, 20 city memberships, 10 truck placements, and 30 package placements, with no extras.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p58

Case artifacts: [p58/](p58/)


## Decision

`REWRITE REQUIRED`

The original uses the over-generating pseudo-range `obj11` to `obj103`; its package-placement and city-membership wording does not define a complete, unique index construction; and it states only seven of 30 irregular goals. Bounded construction rules and a complete goal enumeration repair those defects while preserving the one-paragraph style and all correct airplane facts.

原描述使用会过度生成标识符的伪范围 `obj11` 到 `obj103`；包裹位置与城市隶属表述没有定义完整且唯一的索引构造；30 个不规则目标中也只明确陈述了 7 个。采用有界构造规则并完整列出目标即可修复这些缺陷，同时保留单段落风格和全部正确的飞机事实。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 73 objects on lines 4–76; 146 init atoms on lines 79–224; 30 goal atoms on lines 227–256.
- `natural_original.txt`: original one-paragraph English description.
- Exact totals: objects 73; init 146; goal 30; semantic items 249.

## Before-rewrite coverage and defects

- Objects covered: 52/73; 21 package identifiers had no direct, non-over-generating occurrence.
- Init atoms covered: 80/146; 21 package type facts, 27 non-example package placements, and 18 non-example city memberships lacked unique evidence.
- Goal atoms covered: 7/30; 23 goal atoms were hidden behind `and so forth` and broad examples.
- Missing: 23 goal atoms.
- Ambiguous: 87 semantic items (21 objects plus 66 init items).
- Contradictory: 0.
- Over-generated: 63 non-golden package identifiers under the literal integer-range reading of `obj11` to `obj103`.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `There are packages labeled from obj11 to obj103 and trucks labeled from tru1 to tru10.` | `For each integer i from 1 through 10, there are exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3; for example, i=1 gives obj11, obj12, and obj13, while i=10 gives obj101, obj102, and obj103. The trucks are labeled from tru1 to tru10.` | Replaces the package pseudo-range with the exact 30-name construction while retaining the valid truck range. / 用恰好生成 30 个名称的构造替换包裹伪范围，同时保留正确的卡车范围。 | Package objects: `golden_problem.pddl:8–10,16–18,23–25,30–32,37–39,45–47,52–54,59–61,66–68,74–76`; `(PACKAGE ...)`: lines 79–108. |
| 2 | `Additionally, there are airplanes labeled apn1 to apn3, and cities labeled cit1 to cit10, each with a designated location: pos1 to pos10 and airports apt1 to apt10.` | `Additionally, there are airplanes labeled apn1 to apn3 and cities labeled cit1 to cit10. For each integer i from 1 through 10, pos{i} and apt{i} are locations, and apt{i} is an airport, where every {i} is replaced by the same decimal integer.` | Makes every location and airport type explicit through one finite rule while retaining the airplane and city ranges. / 用一条有限规则明确全部地点与机场类型，同时保留飞机和城市范围。 | Objects: `golden_problem.pddl:4–76`; `(LOCATION ...)`: lines 129–148; `(AIRPORT ...)`: lines 149–158. |
| 3 | `Each truck is starting at a position corresponding to the number, for instance, tru1 is at pos1, and each position contains packages with the same initial numbers as trucks and positions.` | `For each integer i from 1 through 10, tru{i} is initially at pos{i}, and obj{i}1, obj{i}2, and obj{i}3 are initially at pos{i}, where every {i} is replaced by the same decimal integer.` | Defines the bounds, identifier construction, and same-index placement for every truck and package. / 定义全部卡车与包裹的边界、标识符构造和同索引位置映射。 | Truck/package placements: `golden_problem.pddl:165–204`. |
| 4 | `Moreover, specific locations correspond to their respective cities; for example, pos1 and apt1 are located within cit1.` | `Moreover, for each integer i from 1 through 10, pos{i} and apt{i} are located within cit{i}, where every {i} is replaced by the same decimal integer; for example, pos1 and apt1 are located within cit1.` | Converts one example and an undefined correspondence into the complete 20-atom city-membership rule. / 将一个示例和未定义的对应关系转换为完整的 20 原子城市隶属规则。 | `(IN-CITY ...)`: `golden_problem.pddl:205–224`. |
| 5 | `Our goal is to rearrange these packages to new designated locations: obj51 should be moved to pos2, obj43 to pos10, obj82 to apt6, obj33 should remain at pos3, and so forth. This involves packages being transported across different cities and locations, such as obj12 needing to move to pos7 and obj93 ending up at apt7.` | `The complete goal is that all of the following package locations hold simultaneously: obj51 at pos2; obj43 at pos10; obj82 at apt6; obj33 at pos3; obj61 at apt2; obj22 at pos6; obj103 at pos5; obj32 at apt7; obj12 at pos7; obj91 at apt6; obj31 at pos7; obj52 at apt5; obj83 at pos10; obj73 at apt2; obj23 at apt8; obj42 at apt8; obj62 at pos3; obj102 at apt8; obj53 at pos5; obj81 at pos6; obj93 at apt7; obj13 at pos4; obj72 at apt8; obj101 at pos1; obj71 at pos5; obj92 at pos2; obj63 at pos2; obj41 at pos8; obj11 at pos3; and obj21 at pos5.` | Replaces examples and `and so forth` with all 30 irregular destinations as a simultaneous conjunction. / 用全部 30 个须同时成立的不规则目的地替换示例与 `and so forth`。 | Complete goal conjunction: `golden_problem.pddl:226–257`, with atoms on lines 227–256. |

## Material deliberately preserved

- The opening and closing sentences, one-paragraph organization, and correct airplane placements.
- The exact `obj11`–`obj13`/`tru1` example and the accurate `apt1`/`cit1` example.
- All unaffected wording was retained verbatim.

## Post-rewrite verification

- Objects covered: 73/73.
- Init atoms covered: 146/146.
- Goal atoms covered: 30/30.
- Evidence ledger rows: 249/249.
- Expanding each rule for exactly `i = 1…10` yields 30 package names, 20 locations, 20 city memberships, 10 truck placements, and 30 package placements, with no extras.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p59

Case artifacts: [p59/](p59/)


## Decision

`NO REWRITE REQUIRED`

The original directly enumerates every golden object and unary type, every airplane/truck/package initial location, all 20 location-to-city relations, and all 30 irregular goal pairs. It contains no contradiction, vague continuation, or extra object/fact/goal, so `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`.

原描述直接列出了每个黄金对象及一元类型、每架飞机/每辆卡车/每个包裹的初始位置、全部 20 个地点到城市的关系以及全部 30 个不规则目标对。原文不含矛盾、模糊续写或额外对象/事实/目标，因此 `natural_rewritten.txt` 与 `natural_original.txt` 逐字节一致。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 73 objects on lines 4–76; 146 init atoms on lines 79–224; 30 goal atoms on lines 227–256.
- `natural_original.txt`: complete original one-paragraph English description.
- Exact totals: objects 73; init 146; goal 30; semantic items 249.

## Before-rewrite coverage and defects

- Objects covered: 73/73.
- Init atoms covered: 146/146.
- Goal atoms covered: 30/30.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | `natural_rewritten.txt` is an exact copy of `natural_original.txt`. | The original already provides direct, unique evidence for all 249 semantic items and implies no extras. / 原文已经为全部 249 个语义项提供直接且唯一的证据，也未暗示任何额外项。 | Objects: `golden_problem.pddl:4–76`; init: lines 79–224; goal: lines 227–256. |

## Material deliberately preserved

- The complete object/type inventories and all initial airplane, truck, and package placements.
- The explicit 20-pair location-to-city mapping and all 30 irregular goal destinations.
- The entire English description, including its one-paragraph organization and wording.

## Post-rewrite verification

- Objects covered: 73/73.
- Init atoms covered: 146/146.
- Goal atoms covered: 30/30.
- Evidence ledger rows: 249/249.
- Byte comparison of `natural_original.txt` and `natural_rewritten.txt`: identical.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p60

Case artifacts: [p60/](p60/)


## Decision

`NO REWRITE REQUIRED`

The original directly enumerates every golden object and unary type, every airplane/truck/package initial location, all 22 location-to-city relations, and all 31 irregular goal pairs. It contains no contradiction, vague continuation, or extra object/fact/goal, so `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`.

原描述直接列出了每个黄金对象及一元类型、每架飞机/每辆卡车/每个包裹的初始位置、全部 22 个地点到城市的关系以及全部 31 个不规则目标对。原文不含矛盾、模糊续写或额外对象/事实/目标，因此 `natural_rewritten.txt` 与 `natural_original.txt` 逐字节一致。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 80 objects on lines 4–83; 160 init atoms on lines 86–245; 31 goal atoms on lines 248–278.
- `natural_original.txt`: complete original one-paragraph English description.
- Exact totals: objects 80; init 160; goal 31; semantic items 271.

## Before-rewrite coverage and defects

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 31/31.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | `natural_rewritten.txt` is an exact copy of `natural_original.txt`. | The original already provides direct, unique evidence for all 271 semantic items and implies no extras. / 原文已经为全部 271 个语义项提供直接且唯一的证据，也未暗示任何额外项。 | Objects: `golden_problem.pddl:4–83`; init: lines 86–245; goal: lines 248–278. |

## Material deliberately preserved

- The complete object/type inventories and all initial airplane, truck, and package placements.
- The explicit 22-pair location-to-city mapping and all 31 irregular goal destinations.
- The entire English description, including its one-paragraph organization and wording.

## Post-rewrite verification

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 31/31.
- Evidence ledger rows: 271/271.
- Byte comparison of `natural_original.txt` and `natural_rewritten.txt`: identical.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p61

Case artifacts: [p61/](p61/)


## Decision

`REWRITE REQUIRED`

The original directly supplies all 80 golden objects, all 160 initial atoms, and all 31 goal atoms, but its package-label pseudo-range `obj11` to `obj113` also denotes 70 non-golden integer labels under a literal range reading. Replacing only that clause with a bounded concatenation rule removes the over-generation; all other wording remains verbatim.

原描述直接提供了全部 80 个黄金对象、160 个初始原子和 31 个目标原子，但若按字面整数范围理解，包裹标签伪范围 `obj11` 到 `obj113` 还会表示 70 个非黄金标签。仅将该分句替换为有界连接规则即可消除过度生成；其余文字均逐字保留。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 80 objects on lines 4–83; 160 init atoms on lines 86–245; 31 goal atoms on lines 248–278.
- `natural_original.txt`: original one-paragraph English description.
- Exact totals: objects 80; init 160; goal 31; semantic items 271.

## Before-rewrite coverage and defects

- Objects covered: 80/80; every golden package is also named in the complete initial-placement list.
- Init atoms covered: 160/160.
- Goal atoms covered: 31/31.
- Missing: 0; ambiguous: 0; contradictory: 0.
- Over-generated: 70 non-golden package identifiers under the literal integer-range reading of `obj11` through `obj113`.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `Initially, we have packages labeled from obj11 to obj113, eleven trucks from tru1 to tru11, and cities from cit1 to cit11.` | `Initially, for each integer i from 1 through 11, we have exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3; we also have eleven trucks from tru1 to tru11 and cities from cit1 to cit11.` | Replaces only the over-generating package pseudo-range with a finite rule that expands to exactly the 33 golden package labels. / 仅以有限规则替换会过度生成的包裹伪范围，恰好展开为 33 个黄金包裹标签。 | Package objects: `golden_problem.pddl:8–10,15–17,23–25,30–32,37–39,44–46,52–54,59–61,66–68,73–75,81–83`; `(PACKAGE ...)`: lines 86–118. |

## Material deliberately preserved

- The opening, one-paragraph organization, valid truck/city/location/airport/airplane inventories, and exact airplane placements.
- The complete truck/package initial-location enumeration and all 22 location-to-city relations.
- All 31 irregular goal destinations and every word outside the single defective object-range sentence.

## Post-rewrite verification

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 31/31.
- Evidence ledger rows: 271/271.
- Expanding the package rule for exactly `i = 1…11` and final digits `1`, `2`, and `3` yields exactly 33 package names and no extra name.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p62

Case artifacts: [p62/](p62/)


## Decision

`NO REWRITE REQUIRED`

The original directly enumerates every golden object and unary type, every airplane/truck/package initial location, all 22 location-to-city relations, and all 32 irregular goal pairs. It contains no contradiction, vague continuation, or extra object/fact/goal, so `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`.

原描述直接列出了每个黄金对象及一元类型、每架飞机/每辆卡车/每个包裹的初始位置、全部 22 个地点到城市的关系以及全部 32 个不规则目标对。原文不含矛盾、模糊续写或额外对象、事实或目标，因此 `natural_rewritten.txt` 与 `natural_original.txt` 逐字节一致。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 80 objects on lines 4–83; 160 init atoms on lines 86–245; 32 goal atoms on lines 248–279.
- `natural_original.txt`: complete original one-paragraph English description.
- Exact totals: objects 80; init 160; goal 32; semantic items 272.

## Before-rewrite coverage and defects

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 32/32.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | `natural_rewritten.txt` is an exact copy of `natural_original.txt`. | The original already provides direct, unique evidence for all 272 semantic items and implies no extras. / 原文已为全部 272 个语义项提供直接且唯一的证据，也未暗示任何额外项。 | Objects: `golden_problem.pddl:4–83`; init: lines 86–245; goal: lines 248–279. |

## Material deliberately preserved

- The complete object/type inventories and all initial airplane, truck, and package placements.
- The explicit 22-pair location-to-city mapping and all 32 irregular goal destinations.
- The entire English description, including its one-paragraph organization and wording.

## Post-rewrite verification

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 32/32.
- Evidence ledger rows: 272/272.
- Byte comparison of `natural_original.txt` and `natural_rewritten.txt`: identical.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p63

Case artifacts: [p63/](p63/)


## Decision

`NO REWRITE REQUIRED`

The original directly enumerates every golden object and unary type, every airplane/truck/package initial location, all 22 location-to-city relations, and all 32 irregular goal pairs. It contains no contradiction, vague continuation, or extra object/fact/goal, so `natural_rewritten.txt` is byte-for-byte identical to `natural_original.txt`.

原描述直接列出了每个黄金对象及一元类型、每架飞机/每辆卡车/每个包裹的初始位置、全部 22 个地点到城市的关系以及全部 32 个不规则目标对。原文不含矛盾、模糊续写或额外对象、事实或目标，因此 `natural_rewritten.txt` 与 `natural_original.txt` 逐字节一致。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines).
- `golden_problem.pddl`: 80 objects on lines 4–83; 160 init atoms on lines 86–245; 32 goal atoms on lines 248–279.
- `natural_original.txt`: complete original one-paragraph English description.
- Exact totals: objects 80; init 160; goal 32; semantic items 272.

## Before-rewrite coverage and defects

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 32/32.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | `natural_rewritten.txt` is an exact copy of `natural_original.txt`. | The original already provides direct, unique evidence for all 272 semantic items and implies no extras. / 原文已为全部 272 个语义项提供直接且唯一的证据，也未暗示任何额外项。 | Objects: `golden_problem.pddl:4–83`; init: lines 86–245; goal: lines 248–279. |

## Material deliberately preserved

- The complete object/type inventories and all initial airplane, truck, and package placements.
- The explicit 22-pair location-to-city mapping and all 32 irregular goal destinations.
- The entire English description, including its one-paragraph organization and wording.

## Post-rewrite verification

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 32/32.
- Evidence ledger rows: 272/272.
- Byte comparison of `natural_original.txt` and `natural_rewritten.txt`: identical.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p64

Case artifacts: [p64/](p64/)


## Decision

`REWRITE REQUIRED`

The original names all golden objects and goals, but its package pseudo-range over-generates identifiers; its city, airport, truck, and package patterns do not uniquely define 54 initial atoms; and several phrases imply non-golden facts. Seven local sentence or phrase repairs supply exact finite rules, state co-location rather than containment in a truck, and remove the false `remain`/`stay` implications while preserving the complete goal list and overall format.

原描述提到了全部黄金对象和目标，但包裹伪范围会过度生成标识符；城市、机场、卡车和包裹的模式没有唯一确定 54 个初始原子；另有若干短语暗示非黄金事实。七处局部句子或短语修订补充精确有限规则，明确包裹与卡车同处地点而非装在卡车中，并删除错误的 `remain`/`stay` 含义，同时保留完整目标列表和整体格式。

## Source inventory

- `golden_domain.pddl`: Logistics predicates and action semantics (85 lines), including distinct `at` and `in` predicates on lines 13–14.
- `golden_problem.pddl`: 80 objects on lines 4–83; 160 init atoms on lines 86–245; 33 goal atoms on lines 248–280.
- `natural_original.txt`: original multi-paragraph, bulleted English description.
- Exact totals: objects 80; init 160; goal 33; semantic items 273.

## Before-rewrite coverage and defects

- Objects covered: 80/80; all 33 actual package labels also occur in the complete goal list.
- Init atoms covered: 106/160.
- Goal atoms covered: 33/33; the two false continuity words still identify their intended goal locations.
- Missing: 0.
- Ambiguous: 51 init atoms: 32 middle-group package/truck placements and 19 unstated same-index city memberships.
- Contradictory: 7 defects: the three `obj2*` package placements are described as truck containment rather than package-at-`pos2` facts, plus the one-airplane-per-city claim, unspecified airport proximity, `obj83` already remaining at `pos3`, and `obj82` already staying at `apt4`.
- Over-generated: 73 items: 70 non-golden package identifiers under the literal integer-range reading of `obj11` through `obj113`, plus three absent initial `(in obj2* tru2)` atoms implied by `holds packages`.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `Initially, we have packages labeled obj11 through obj113, a total of 33 packages.` | `Initially, for each integer i from 1 through 11, we have exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3, for a total of 33 packages.` | Replaces the pseudo-range with a bounded construction that yields exactly 33 labels. / 用恰好生成 33 个标签的有界构造替换伪范围。 | Package objects: `golden_problem.pddl:8–10,15–17,23–25,30–32,37–39,44–46,52–54,59–61,66–68,73–75,81–83`; package types: lines 86–118. |
| 2 | `Each city has an airport location, apt1 through apt11, and contains one airplane: apn1 is at apt3, apn2 is at apt2, and apn3 is at apt11.` | `For each integer i from 1 through 11, the city labeled by concatenating cit and i contains the two locations labeled by concatenating pos and i and by concatenating apt and i, and the apt location is an airport; the three airplanes are apn1 at apt3, apn2 at apt2, and apn3 at apt11.` | Defines the same-index city/location mapping and airport types, and corrects the one-airplane-per-city implication while preserving all three placements. / 定义同索引城市地点映射和机场类型，并纠正每城一架飞机的暗示，同时保留三架飞机的位置。 | Cities/locations/airplanes: `golden_problem.pddl:4–83`; `(LOCATION ...)`: lines 141–162; `(AIRPORT ...)`: lines 163–173; `(AIRPLANE ...)` and airplane placements: lines 174–179; `(IN-CITY ...)`: lines 224–245. |
| 3 | `- In city cit1, located at pos1, we have truck tru1 with packages obj11, obj12, and obj13.` | `- In city cit1, truck tru1 and packages obj11, obj12, and obj13 are initially at pos1.` | Makes all four co-location atoms direct without implying containment. / 直接表述四个同地点原子，不暗示装载关系。 | `(AT TRU1 POS1)` and `(AT OBJ11/OBJ12/OBJ13 POS1)`: `golden_problem.pddl:180–183`. |
| 4 | `- In city cit2, at pos2, truck tru2 holds packages obj21, obj22, and obj23.` | `- In city cit2, truck tru2 and packages obj21, obj22, and obj23 are initially at pos2.` | Replaces non-golden in-truck containment with the four golden `at` atoms. / 用四个黄金 `at` 原子替换非黄金的车内装载关系。 | `(AT TRU2 POS2)` and `(AT OBJ21/OBJ22/OBJ23 POS2)`: `golden_problem.pddl:184–187`; `golden_domain.pddl:13–14` distinguishes `at` from `in`. |
| 5 | `- Similarly, the pattern continues across the cities up to city cit11 where truck tru11 is at pos11 with packages obj111, obj112, and obj113. Each city's airport is nearby, but initially, our focus is on the packages at different positions.` | `- For each integer i from 3 through 11, the truck labeled by concatenating tru and i and the three packages labeled by concatenating obj, i, and one of 1, 2, or 3 are initially at the position labeled by concatenating pos and i.` | Replaces an undefined continuation and unsupported proximity relation with the exact remaining 36 placements. / 用精确的其余 36 个位置关系替换未定义的续写和无支持的邻近关系。 | Truck/package placements for indices 3–11: `golden_problem.pddl:188–223`. |
| 6 | `obj83 should remain at pos3 along with obj33` | `obj83 should be at pos3 along with obj33` | Removes the false implication that `obj83` initially occupies its goal; `obj33` genuinely does. / 删除 `obj83` 初始即在目标位置的错误暗示；`obj33` 的确如此。 | Initial `(AT OBJ83 POS8)`: `golden_problem.pddl:211`; goals `(AT OBJ83 POS3)` and `(AT OBJ33 POS3)`: lines 267–268. |
| 7 | `obj82 should stay at apt4` | `obj82 should be at apt4` | Removes the false implication that `obj82` initially occupies `apt4`. / 删除 `obj82` 初始即在 `apt4` 的错误暗示。 | Initial `(AT OBJ82 POS8)`: `golden_problem.pddl:210`; goal `(AT OBJ82 APT4)`: line 275. |

## Material deliberately preserved

- The first-person voice, multi-paragraph bullet layout, opening and closing, and valid truck/city/location ranges.
- Every correct airplane placement and every one of the 33 explicitly stated goal destinations.
- All goal wording except the two continuity words that contradicted the golden initial state.

## Post-rewrite verification

- Objects covered: 80/80.
- Init atoms covered: 160/160.
- Goal atoms covered: 33/33.
- Evidence ledger rows: 273/273.
- The package rule yields 33 names; the city/location rule yields 22 memberships and 11 airport types; the placement rules yield all 44 truck/package `at` atoms, with no extras.

Final assertion: missing = 0, ambiguous = 0, contradictory = 0, and over-generated = 0.

## p65

Case artifacts: [p65/](p65/)


## Decision

`NO REWRITE REQUIRED`

The original directly enumerates all 80 objects and their unary types, every initial airplane/truck/package location, all 22 location-to-city relations, and all 33 irregular goal pairs. It contains no ambiguity, contradiction, or extra object, fact, or goal, so the final English description is byte-for-byte identical to the original.
原描述直接列出了全部 80 个对象及其一元类型、每架飞机/每辆卡车/每个包裹的初始位置、全部 22 个地点到城市的关系以及全部 33 个不规则目标对。原文不含歧义、矛盾或额外对象、事实或目标，因此最终英文描述与原文逐字节一致。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics; 85 lines.
- `golden_problem.pddl`: 80 objects on lines 4–83; 160 init atoms on lines 86–245; 33 goal atoms on lines 248–280.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 273 semantic items.

## Before-rewrite coverage and defects

- Objects: 80/80; init: 160/160; goal: 33/33.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | `natural_rewritten.txt` is an exact copy of `natural_original.txt`. | Every semantic item already has direct, unique evidence, and no extra item is implied. / 每个语义项都已有直接且唯一的证据，也未暗示任何额外项。 | Objects: `golden_problem.pddl:4–83`; init: lines 86–245; goal: lines 248–280. |

## Material deliberately preserved

- The complete object/type inventories and every initial airplane, truck, and package placement.
- The explicit 22-pair location-to-city mapping and complete 33-pair irregular goal.
- The entire one-paragraph wording and organization.

## Post-rewrite verification

- Objects: 80/80; init: 160/160; goal: 33/33; ledger: 273/273 rows.
- Byte comparison of original and final English: identical.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has unique direct evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据，最终描述没有引入任何额外项。

## p66

Case artifacts: [p66/](p66/)


## Decision

`REWRITE REQUIRED`

The object inventories, airplane locations, city mappings, and all 34 goals are complete. The single sentence saying that trucks and their “corresponding packages” occupy `pos1` through `pos12` does not define which three package identifiers correspond to each truck or position. Replacing only that sentence with a bounded same-index rule makes all 48 truck/package initial placements uniquely recoverable.
对象清单、飞机位置、城市映射和全部 34 个目标均完整。唯一的问题是，称卡车及其“对应包裹”位于 `pos1` 至 `pos12` 的句子没有定义每辆卡车或每个位置对应哪三个包裹标识符。仅将该句替换为有界的同索引规则，即可唯一恢复全部 48 个卡车/包裹初始位置。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics; 85 lines.
- `golden_problem.pddl`: 87 objects on lines 4–90; 174 init atoms on lines 93–266; 34 goal atoms on lines 269–302.
- `natural_original.txt`: original two-paragraph English description.
- Exact total: 295 semantic items.

## Before-rewrite coverage and defects

- Objects: 87/87; init: 126/174; goal: 34/34.
- Ambiguous: 48 initial `AT` atoms (12 truck placements and 36 package placements).
- Missing: 0; contradictory: 0; over-generated: 0.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `The trucks (tru1 through tru12) and their corresponding packages are positioned at locations pos1 through pos12.` | `For every integer X from 1 through 12, truck truX and packages objX1, objX2, and objX3 are positioned at posX initially, where X is replaced by the same decimal numeral in every identifier (so X = 10 yields tru10, obj101, obj102, obj103, and pos10).` | Defines the complete finite correspondence and the multi-digit identifier construction. / 定义完整的有限对应关系以及多位数标识符构造。 | `golden_problem.pddl:195–242`: all 48 truck/package initial `AT` atoms. |

## Material deliberately preserved

- All object and type wording, including the exact package inventory and bounded truck/city/location/airport sets.
- The ordered airplane locations and existing `posX`/`aptX` to `citX` mapping.
- The full 34-pair irregular goal and the two-paragraph organization.

## Post-rewrite verification

- Objects: 87/87; init: 174/174; goal: 34/34; ledger: 295/295 rows.
- Expanding X over exactly 1 through 12 yields 12 truck placements and 36 package placements, including the correct multi-digit identifiers for X = 10, 11, and 12, and no extras.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has unique direct or deterministic-rule evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据或确定性规则证据，最终描述没有引入任何额外项。

## p67

Case artifacts: [p67/](p67/)


## Decision

`NO REWRITE REQUIRED`

The original explicitly identifies all 15 objects and 30 initial atoms: it names every type, both city memberships for each city, and every vehicle/package initial location. Its final sentence also states all six goal atoms as a single objective. No wording requires an unstated pattern or implies an extra item, so the final English description is byte-for-byte identical to the original.
原文明确给出了全部 15 个对象和 30 个初始原子：它说明了每个类型、每座城市中的两个地点关系，以及每辆交通工具和每个包裹的初始位置。最后一句还把全部六个目标原子作为同一目标陈述。任何表述都不依赖未说明的模式，也未暗示额外项，因此最终英文描述与原文逐字节一致。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics; 85 lines.
- `golden_problem.pddl`: 15 objects on line 3; 30 init atoms on lines 4–10; 6 goal atoms on lines 11–12.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 51 semantic items.

## Before-rewrite coverage and defects

- Objects: 15/15; init: 30/30; goal: 6/6.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | `natural_rewritten.txt` is an exact copy of `natural_original.txt`. | All 51 semantic items already have direct, unique evidence and no extra item is implied. / 全部 51 个语义项都已有直接且唯一的证据，也未暗示任何额外项。 | Objects: `golden_problem.pddl:3`; init: lines 4–10; goal: lines 11–12. |

## Material deliberately preserved

- Every object/type sentence, initial location, and city membership.
- The complete six-pair goal sentence and all original wording and organization.

## Post-rewrite verification

- Objects: 15/15; init: 30/30; goal: 6/6; ledger: 51/51 rows.
- Byte comparison of original and final English: identical.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has unique direct evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据，最终描述没有引入任何额外项。

## p68

Case artifacts: [p68/](p68/)


## Decision

`REWRITE REQUIRED`

The original package pseudo-range over-generates identifiers, the initial placements rely on “similarly,” and the city mapping uses examples plus a continuation phrase instead of a complete rule. Only seven of 34 irregular goal pairs are stated, while the closing sentence adds an unsupported efficiency objective. Six localized replacements provide bounded identifier and mapping rules, enumerate the complete goal, and remove only the optimization phrase.
原文的包裹伪范围会过度生成标识符，初始位置依赖“类似地”的表述，城市映射也使用示例和续写短语，而非完整规则。34 个不规则目标对中仅陈述了七个，结尾还增加了无 PDDL 支持的效率目标。六处局部替换给出有界的标识符和映射规则、列出完整目标，并且只删除优化含义短语。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics predicate and action semantics; 85 lines.
- `golden_problem.pddl`: 87 objects on lines 4–90; 174 init atoms on lines 93–266; 34 goal atoms on lines 269–302.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 295 semantic items.

## Before-rewrite coverage and defects

- Objects: 62/87. Eleven package identifiers are explicit in examples or stated goals; the other 25 are not uniquely established by the pseudo-range. All 51 non-package objects are recoverable.
- Init: 89/174. The remaining 85 atoms depend on the package pseudo-range, “similarly,” or the example-plus-continuation city mapping.
- Goal: 7/34; 27 irregular goal pairs are missing.
- Missing: 27; ambiguous: 110 (25 object items plus 85 init atoms); contradictory: 0.
- Over-generated: 78 (77 non-golden package labels implied by the inclusive `obj11`–`obj123` pseudo-range, plus one unsupported efficiency objective).

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `In the initial setup of this logistics challenge, we have packages labeled from obj11 to obj123, which are spread across various locations.` | `In the initial setup of this logistics challenge, we have packages objX1, objX2, and objX3 for every integer X from 1 through 12, where X is replaced by its decimal numeral in each identifier (so X = 10 yields obj101, obj102, and obj103); these packages are spread across various locations.` | Replaces the 113-label inclusive pseudo-range with the exact 36-label construction while preserving the surrounding sentence. / 用精确的 36 项构造替换含 113 个标签的包含式伪范围，同时保留周边句式。 | Package objects: `golden_problem.pddl:8–10,15–17,22–24,30–32,37–39,51–53,59–61,66–68,73–75,80–82,88–90`; package types: lines 93–128. |
| 2 | `The scenario includes twelve cities, each having a position and an airport as a location.` | `The scenario includes twelve cities, cit1 through cit12; for every integer X from 1 through 12, posX and aptX are locations, and aptX is an airport in citX.` | Names every city/location and supplies exact location and airport typing. / 明确每个城市与地点，并给出精确的地点和机场类型。 | `golden_problem.pddl:141–188`: all city, location, and airport atoms. |
| 3 | `Each truck and package also begins at a specific position: for example, tru1 along with packages obj11, obj12, and obj13 are at position pos1 in city 1, tru2 with packages obj21, obj22, and obj23 are situated at position pos2 in city 2, and this pattern continues similarly for all twelve trucks and positions.` | `For every integer X from 1 through 12, truck truX and packages objX1, objX2, and objX3 begin at posX.` | Replaces two examples and “similarly” with the complete finite mapping. / 用完整的有限映射替换两个示例和“类似地”。 | `golden_problem.pddl:195–242`: all 48 truck/package initial `AT` atoms. |
| 4 | `Each position and airport location is designated to be within a specific city, such as pos1 and apt1 in city 1, pos2 and apt2 in city 2, continuing sequentially up to city 12.` | `For every integer X from 1 through 12, posX and aptX are in citX.` | Makes all 24 same-index city memberships explicit as one bounded rule. / 用一条有界规则明确全部 24 个同索引城市隶属关系。 | `golden_problem.pddl:243–266`: all 24 `IN-CITY` atoms. |
| 5 | `For instance, obj13 should remain at pos1, while obj53 needs to be relocated to the airport in city 1. We need obj21 to reach the airport in city 9, obj32 to be delivered to pos12, and similar specific targets for each package listed, including obj122 arriving at pos7, obj72 being transferred to pos2, and obj111 staying at pos11.` | `Specifically, obj13 should remain at pos1; obj53 needs to be relocated to apt1; obj21 needs to reach apt9; obj32 should be delivered to pos12; obj23 should reach apt11; obj122 should arrive at pos7; obj73 should reach pos3; obj42 should reach pos6; obj22 should reach apt2; obj81 should reach apt7; obj121 should reach pos3; obj52 should reach pos9; obj11 should reach apt8; obj72 should be transferred to pos2; obj112 should reach apt11; obj111 should stay at pos11; obj93 should reach apt7; obj63 should reach pos12; obj123 should reach pos11; obj83 should reach pos6; obj33 should reach apt10; obj12 should reach apt6; obj41 should reach pos8; obj92 should reach pos6; obj61 should reach apt2; obj91 should reach apt1; obj101 should reach apt3; obj31 should reach apt1; obj62 should reach pos11; obj82 should reach apt6; obj51 should reach pos10; obj71 should reach apt2; obj113 should reach apt2; and obj43 should reach apt1.` | Replaces examples and a vague placeholder with all 34 irregular package–destination pairs. / 用全部 34 个不规则包裹—目的地对替换示例和模糊占位语。 | `golden_problem.pddl:269–302`: complete goal conjunction. |
| 6 | `the most efficient route` | `a route` | Removes an optimization criterion absent from the golden PDDL while preserving the close. / 删除黄金 PDDL 中不存在的优化标准，同时保留结尾句。 | `golden_problem.pddl:268–303`: only a destination conjunction; no metric. |

## Material deliberately preserved

- The airplane inventory and the three initial airplane locations, whose airport-in-city references are unique under the repaired city rule.
- The goal introduction, the harmless general phrase “spread across various locations” because exact placements follow, and all other unaffected challenge-oriented wording.
- The single-paragraph organization and closing sentence apart from `the most efficient route`.

## Post-rewrite verification

- Objects: 87/87; init: 174/174; goal: 34/34; ledger: 295/295 rows.
- Expanding X over exactly 1 through 12 yields 36 packages, 12 trucks, 12 cities, 24 locations, 12 airports, 48 truck/package placements, and 24 city memberships. Multi-digit indices produce `obj101`–`obj103`, `obj111`–`obj113`, and `obj121`–`obj123`, with no integer pseudo-range expansion.
- The explicit goal sentence contains exactly the 34 golden pairs and requires no analogy or unstated continuation.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has unique direct or deterministic-rule evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据或确定性规则证据，最终描述没有引入任何额外项。

## p69

Case artifacts: [p69/](p69/)


Decision: `REWRITE REQUIRED`

The original names only examples for most initial package placements and goals, uses an over-generating package pseudo-range, leaves city indexing implicit, and gives ambiguous airplane locations. The final text makes only the bounded and irregular mappings explicit that are necessary for complete recovery.

原文对大多数包裹初始位置和目标只给出示例，使用会过度生成的包裹伪范围，未明确城市索引，并含有歧义的飞机位置。最终文本只补充了实现完整恢复所必需的有界规则和不规则映射。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, preserved unchanged.
- `natural_original.txt`: original English description, preserved unchanged.
- Objects: 87/87 parsed.
- Initial-state atoms: 174/174 parsed, including every unary type fact.
- Goal atoms: 35/35 parsed.
- Total semantic items: 296.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 47/87 |
| Initial atoms covered | 63/174 |
| Goal atoms covered | 5/35 |
| Missing | 54 |
| Ambiguous/incomplete | 127 |
| Contradictory | 0 |
| Over-generated | 78 |

The over-generation count comprises 77 nongolden package identifiers implied by the literal integer pseudo-range plus one unsupported extra goal claim (all-package coverage in p69; efficiency in p70). Missing and ambiguous counts classify uncovered golden semantic items and therefore do not include those extras.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Initial setup for the logistics game includes 36 packages labeled from obj11 to obj123 and 12 trucks labeled from tru1 to tru12. | Initial setup for the logistics game includes, for each X from 1 to 12, the three packages objX1, objX2, and objX3, and includes 12 trucks labeled from tru1 to tru12. | Replaces the pseudo-range obj11 to obj123 with a bounded two-index construction while preserving the truck declaration. / 用有界的双索引构造替换 obj11 到 obj123 的伪范围，并保留卡车声明。 | `golden_problem.pddl:lines 4-90: exact object set`<br>`golden_problem.pddl:lines 93-140: (PACKAGE ...) and (TRUCK ...) facts` |
| 2 | There are also 12 cities each with a position and airport location. | There are also 12 cities labeled from cit1 to cit12, each with a position and airport location. | Adds the missing city labels while preserving the original count and city/location framing. / 补充缺失的城市标签，同时保留原有数量和城市/地点表述。 | `golden_problem.pddl:lines 141-152: (CITY CIT1) through (CITY CIT12)` |
| 3 | Every airplane (apn1, apn2, and apn3) is initially stationed at apt12 or apt7. | Every airplane (apn1, apn2, and apn3) is initially stationed as follows: apn1 and apn2 are at apt12, and apn3 is at apt7. | Resolves the ambiguous apt12-or-apt7 placement into the three exact initial airplane locations. / 将含糊的 apt12 或 apt7 表述改为三架飞机各自的确切初始位置。 | `golden_problem.pddl:line 192: (AT APN1 APT12)`<br>`golden_problem.pddl:line 193: (AT APN2 APT12)`<br>`golden_problem.pddl:line 194: (AT APN3 APT7)` |
| 4 | Each position from pos1 to pos12 is located within its corresponding city, and similarly, each airport (apt1 to apt12) is located in its respective city. | For each X from 1 to 12, posX and aptX are locations in citX, and aptX is an airport. | Defines the index correspondence, location types, airport types, and all location-to-city relations without guessing. / 明确索引对应、地点类型、机场类型和全部地点到城市关系，无需猜测。 | `golden_problem.pddl:lines 153-188: (LOCATION ...) and (AIRPORT ...) facts`<br>`golden_problem.pddl:lines 243-266: (IN-CITY ...) facts` |
| 5 | Specifically, the packages start at various locations; for example, obj11, obj12, and obj13 are at pos1, with the corresponding truck tru1. | Specifically, initially, for each X from 1 to 12, truck truX and packages objX1, objX2, and objX3 are at posX. | Replaces a vague example with the complete bounded initial mapping for all 12 trucks and 36 packages. / 用完整有界规则替换模糊示例，覆盖 12 辆卡车和 36 个包裹的初始位置。 | `golden_problem.pddl:lines 195-242: all truck and package (AT ...) facts` |
| 6 | For instance, obj81 needs to be at pos1, obj62 at pos5, obj123 at pos7, obj42 at apt12, and obj112 at apt6. | Specifically, obj81 needs to be at pos1; obj62 needs to be at pos5; obj123 needs to be at pos7; obj42 needs to be at apt12; obj112 needs to be at apt6; obj63 needs to be at apt8; obj111 needs to be at pos5; obj122 needs to be at apt5; obj72 needs to be at pos1; obj52 needs to be at apt2; obj103 needs to be at apt3; obj61 needs to be at apt5; obj21 needs to be at apt9; obj31 needs to be at apt12; obj121 needs to be at pos12; obj41 needs to be at apt10; obj51 needs to be at apt5; obj22 needs to be at pos3; obj93 needs to be at apt10; obj13 needs to be at apt5; obj71 needs to be at pos7; obj73 needs to be at pos7; obj92 needs to be at apt2; obj12 needs to be at apt6; obj83 needs to be at apt8; obj33 needs to be at pos12; obj102 needs to be at pos11; obj23 needs to be at pos12; obj11 needs to be at apt9; obj32 needs to be at apt3; obj43 needs to be at apt7; obj91 needs to be at pos5; obj53 needs to be at apt6; obj113 needs to be at pos9; obj101 needs to be at apt12. | Expands the five examples into the exact irregular 35-atom goal mapping. / 将五个示例扩展为精确的不规则 35 原子目标映射。 | `golden_problem.pddl:lines 269-303: all 35 goal atoms` |
| 7 | The comprehensive list outlines destinations for all packages ensuring proper distribution and logistics management to achieve the described end positions for each package. | These 35 package destinations must all hold simultaneously. | Removes the unsupported claim about all 36 packages and states that the 35 listed goals are simultaneous. / 删除关于全部 36 个包裹的不受支持声明，并明确列出的 35 个目标同时成立。 | `golden_problem.pddl:lines 268-304: conjunctive goal containing 35 atoms` |

## Material deliberately preserved

- The original narrative order (setup, initial state, then goal).
- The sentence “The goal is to rearrange these packages such that specific packages end up at certain locations.”
- All wording not implicated in an atomic defect.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 87/87 |
| Initial atoms covered | 174/174 |
| Goal atoms covered | 35/35 |
| Ledger rows | 296/296 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was expanded over X = 1 through 12 and checked against its complete sibling family. The final expansion introduces no identifier or atom outside the golden problem. Every irregular goal mapping was checked individually.

已将每条有界规则在 X = 1 到 12 的完整范围内展开，并与全部同族事实核对；最终展开不会引入黄金问题之外的标识符或原子。每个不规则目标映射也已逐项核对。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p70

Case artifacts: [p70/](p70/)


Decision: `REWRITE REQUIRED`

The original goal list and airplane placements are correct, but its package pseudo-range, unnamed city family, and undefined “corresponding” initial mapping prevent unique recovery; its efficiency wording also adds an unsupported objective. The final text repairs only those spans.

原文的目标清单和飞机位置正确，但包裹伪范围、未命名的城市族以及未定义的“对应”初始映射妨碍唯一恢复；效率措辞还增加了 PDDL 未支持的目标。最终文本仅修复这些片段。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, preserved unchanged.
- `natural_original.txt`: original English description, preserved unchanged.
- Objects: 87/87 parsed.
- Initial-state atoms: 174/174 parsed, including every unary type fact.
- Goal atoms: 35/35 parsed.
- Total semantic items: 296.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 75/87 |
| Initial atoms covered | 92/174 |
| Goal atoms covered | 35/35 |
| Missing | 22 |
| Ambiguous/incomplete | 72 |
| Contradictory | 0 |
| Over-generated | 78 |

The over-generation count comprises 77 nongolden package identifiers implied by the literal integer pseudo-range plus one unsupported extra goal claim (all-package coverage in p69; efficiency in p70). Missing and ambiguous counts classify uncovered golden semantic items and therefore do not include those extras.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | The packages are labeled from obj11 to obj123, the trucks are labeled from tru1 to tru12, and the airplanes are labeled apn1, apn2, and apn3. | For each X from 1 to 12, the three packages are labeled objX1, objX2, and objX3; the trucks are labeled from tru1 to tru12; and the airplanes are labeled apn1, apn2, and apn3. | Replaces the package pseudo-range with the exact bounded construction and preserves the truck and airplane declarations. / 用精确的有界构造替换包裹伪范围，并保留卡车和飞机声明。 | `golden_problem.pddl:lines 4-90: exact object set`<br>`golden_problem.pddl:lines 93-140 and 189-191: type facts` |
| 2 | There are also twelve cities, each with two locations: a posX location and an aptX airport, where X is the city number from 1 to 12. | There are also twelve cities labeled from cit1 to cit12, each with two locations: a posX location and an aptX airport, where X is the city number from 1 to 12. | Adds the missing cit1-through-cit12 labels; the existing X rule then uniquely links posX and aptX to citX. / 补充缺失的 cit1 到 cit12 标签，使原有 X 规则能唯一关联 posX、aptX 与 citX。 | `golden_problem.pddl:lines 141-188: city, location, and airport facts`<br>`golden_problem.pddl:lines 243-266: location-to-city facts` |
| 3 | Initially, each truck is located at its corresponding posX location with three corresponding packages, and each airplane is stationed at a specific airport: apn1 is at apt11, apn2 is at apt9, and apn3 is at apt2. | Initially, for each X from 1 to 12, truX and packages objX1, objX2, and objX3 are at posX, and each airplane is stationed at a specific airport: apn1 is at apt11, apn2 is at apt9, and apn3 is at apt2. | Defines the complete truck/package suffix correspondence while preserving the already-correct airplane mapping verbatim. / 明确完整的卡车/包裹后缀对应，并逐字保留原本正确的飞机映射。 | `golden_problem.pddl:lines 192-242: all airplane, truck, and package (AT ...) facts` |
| 4 | The goal is to move the packages efficiently to these locations using the trucks and airplanes available. | All 35 listed package destinations must hold simultaneously. | Removes an unsupported efficiency objective and makes the conjunction of the 35 listed destinations explicit. / 删除 PDDL 未支持的效率目标，并明确 35 个列出目的地构成合取目标。 | `golden_problem.pddl:lines 268-304: conjunctive goal containing 35 atoms` |

## Material deliberately preserved

- The opening Logistics-game framing.
- The cit1/pos1/apt1 example.
- The exact airplane-to-airport mapping.
- The complete irregular 35-package goal sentence, unchanged verbatim.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 87/87 |
| Initial atoms covered | 174/174 |
| Goal atoms covered | 35/35 |
| Ledger rows | 296/296 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was expanded over X = 1 through 12 and checked against its complete sibling family. The final expansion introduces no identifier or atom outside the golden problem. Every irregular goal mapping was checked individually.

已将每条有界规则在 X = 1 到 12 的完整范围内展开，并与全部同族事实核对；最终展开不会引入黄金问题之外的标识符或原子。每个不规则目标映射也已逐项核对。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p71

Case artifacts: [p71/](p71/)


Decision: `NO REWRITE REQUIRED`

The original description directly enumerates every object, unary type fact, initial relation, and goal atom. It has no omission, ambiguity, contradiction, or over-generation, so the English text is preserved byte-for-byte.

原描述直接枚举了每个对象、一元类型事实、初始关系和目标原子，不存在遗漏、歧义、矛盾或过度生成，因此英文文本逐字节保留。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, preserved unchanged.
- `natural_original.txt`: original English description, preserved unchanged.
- Objects: 87/87 parsed.
- Initial-state atoms: 174/174 parsed, including every unary type fact.
- Goal atoms: 36/36 parsed.
- Total semantic items: 297.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 87/87 |
| Initial atoms covered | 174/174 |
| Goal atoms covered | 36/36 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every original evidence span is direct and unique; no rule expansion or unstated convention is needed.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of `natural_original.txt`. | The original already covers all 297 semantic items uniquely. / 原文已唯一覆盖全部 297 个语义项。 | `golden_problem.pddl:lines 4-304` |

## Material deliberately preserved

- The complete original English description; no span needed repair.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 87/87 |
| Initial atoms covered | 174/174 |
| Goal atoms covered | 36/36 |
| Ledger rows | 297/297 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was expanded over X = 1 through 12 and checked against its complete sibling family. The final expansion introduces no identifier or atom outside the golden problem. Every irregular goal mapping was checked individually.

已将每条有界规则在 X = 1 到 12 的完整范围内展开，并与全部同族事实核对；最终展开不会引入黄金问题之外的标识符或原子。每个不规则目标映射也已逐项核对。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p72

Case artifacts: [p72/](p72/)


Decision: `NO REWRITE REQUIRED`

The original description directly enumerates every object, unary type fact, initial relation, and goal atom. It has no omission, ambiguity, contradiction, or over-generation, so the English text is preserved byte-for-byte.

原描述直接枚举了每个对象、一元类型事实、初始关系和目标原子，不存在遗漏、歧义、矛盾或过度生成，因此英文文本逐字节保留。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative object, initial-state, and goal specification, preserved unchanged.
- `natural_original.txt`: original English description, preserved unchanged.
- Objects: 87/87 parsed.
- Initial-state atoms: 174/174 parsed, including every unary type fact.
- Goal atoms: 36/36 parsed.
- Total semantic items: 297.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 87/87 |
| Initial atoms covered | 174/174 |
| Goal atoms covered | 36/36 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every original evidence span is direct and unique; no rule expansion or unstated convention is needed.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of `natural_original.txt`. | The original already covers all 297 semantic items uniquely. / 原文已唯一覆盖全部 297 个语义项。 | `golden_problem.pddl:lines 4-304` |

## Material deliberately preserved

- The complete original English description; no span needed repair.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 87/87 |
| Initial atoms covered | 174/174 |
| Goal atoms covered | 36/36 |
| Ledger rows | 297/297 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was expanded over X = 1 through 12 and checked against its complete sibling family. The final expansion introduces no identifier or atom outside the golden problem. Every irregular goal mapping was checked individually.

已将每条有界规则在 X = 1 到 12 的完整范围内展开，并与全部同族事实核对；最终展开不会引入黄金问题之外的标识符或原子。每个不规则目标映射也已逐项核对。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p73

Case artifacts: [p73/](p73/)


**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Three local rule substitutions are necessary to remove an over-generating package pseudo-range and make the package, truck, location, airport, and city mappings uniquely recoverable.
中文：需要改写。必须进行三处局部规则替换，以消除会过度生成的包裹伪范围，并使包裹、卡车、地点、机场和城市的对应关系都可被唯一恢复。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem; authoritative for this audit.
- `natural_original.txt`: original English description.
- Parsed totals: **95 objects**, **190 init atoms**, **37 goal atoms**, **322 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 92/95
- Init atoms covered: 106/190
- Goal atoms covered: 37/37
- Missing: 9; ambiguous: 78; contradictory: 0; over-generated: 84.
- The over-generation count is the 84 extra integer labels implied by the pseudo-range `obj11` through `obj133` beyond the 39 golden grouped labels.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | There are packages named obj11 through obj133 and these are located across various positions labeled pos1, pos2, ..., pos13. | There are exactly 39 packages: for each integer i from 1 through 13, the three package names are formed by concatenating obj, i, and each of 1, 2, and 3, and all three packages are initially located at the position named by concatenating pos and the same i. | The pseudo-range over-generated 84 package labels and 'across various positions' did not define the initial package-to-position mapping. / 该伪范围会多生成 84 个包裹标签，而“分布在各种位置”没有定义包裹初始位置的对应关系。 | golden_problem.pddl:lines 9-11,16-18,23-25,30-32,38-40,45-47,52-54,59-61,67-69,74-76,81-83,88-90,96-98: package objects<br>golden_problem.pddl:lines 101-139: package type atoms<br>golden_problem.pddl:lines 214-216,218-220,222-224,226-228,230-232,234-236,238-240,242-244,246-248,250-252,254-256,258-260,262-264: package initial positions |
| 2 | We also have a series of trucks, tru1 through tru13, which are stationed at these positions. | We also have a series of trucks, tru1 through tru13; for each integer i from 1 through 13, the truck named by concatenating tru and i is initially stationed at the position named by concatenating pos and the same i. | The phrase 'these positions' did not uniquely pair each truck with its initial position. / “这些位置”没有唯一确定每辆卡车与其初始位置的配对。 | golden_problem.pddl:lines 140-152: (TRUCK TRU1) through (TRUCK TRU13)<br>golden_problem.pddl:lines 213,217,221,225,229,233,237,241,245,249,253,257,261: truck initial positions |
| 3 | The setting includes cities cit1 through cit13, each containing a position and an airport, creating a map of interrelated locations. | The setting includes cities cit1 through cit13; for each integer i from 1 through 13, the names citi, posi, and apti are formed by concatenating cit, pos, and apt respectively with i, posi and apti are locations, apti is an airport, and both posi and apti are in citi, creating a map of interrelated locations. | The original did not name every position/airport or define the shared-index city correspondence and unary location/airport facts. / 原文没有给出全部位置与机场名称，也没有定义共享索引的城市对应关系及地点/机场类型事实。 | golden_problem.pddl:lines 153-165: city atoms<br>golden_problem.pddl:lines 166-204: location and airport atoms<br>golden_problem.pddl:lines 265-290: in-city atoms |

## Material deliberately preserved / 有意保留的实质文本

- The opening sentence was preserved verbatim because it is compatible context.
- The complete ordered airplane mapping was preserved verbatim.
- The complete 37-atom goal sentence and closing sentence were preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 95/95
- Init atoms covered: 190/190
- Goal atoms covered: 37/37
- Ledger rows: 322 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked against its sibling atoms.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** all golden objects, init atoms, and conjunctive goal atoms are uniquely covered, and all four final defect counts are zero. / **最终断言：**全部黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p74

Case artifacts: [p74/](p74/)


**Decision:** `NO REWRITE REQUIRED`

## Finding / 结论

English: NO REWRITE REQUIRED. The original description explicitly and correctly covers every golden object, initial-state atom, and conjunctive goal atom without ambiguity, contradiction, or over-generation.
中文：无需改写。原始描述明确且正确地覆盖了全部黄金对象、初始状态原子和合取目标原子，不存在歧义、矛盾或过度生成。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem; authoritative for this audit.
- `natural_original.txt`: original English description.
- Parsed totals: **95 objects**, **190 init atoms**, **37 goal atoms**, **322 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 95/95
- Init atoms covered: 190/190
- Goal atoms covered: 37/37
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | The original was copied byte-for-byte. | Every item is already directly and uniquely supported; the no-rewrite gate therefore applies. / 每一项均已有直接且唯一的证据，因此适用不改写门槛。 | `golden_problem.pddl:lines 4-330` |

## Material deliberately preserved / 有意保留的实质文本

- The complete original English description was preserved byte-for-byte because every object, init atom, and goal atom is explicit and correct.

## Post-rewrite verification / 改写后核验

- Objects covered: 95/95
- Init atoms covered: 190/190
- Goal atoms covered: 37/37
- Ledger rows: 322 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked against its sibling atoms.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** all golden objects, init atoms, and conjunctive goal atoms are uniquely covered, and all four final defect counts are zero. / **最终断言：**全部黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p75

Case artifacts: [p75/](p75/)


**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Three local substitutions are necessary because the package pseudo-range over-generates labels and the example-based city and initial-location mappings do not expand uniquely.
中文：需要改写。必须进行三处局部替换，因为包裹伪范围会多生成标签，而基于示例的城市关系和初始位置关系不能唯一展开。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem; authoritative for this audit.
- `natural_original.txt`: original English description.
- Parsed totals: **95 objects**, **190 init atoms**, **38 goal atoms**, **323 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 91/95
- Init atoms covered: 105/190
- Goal atoms covered: 38/38
- Missing: 0; ambiguous: 89; contradictory: 0; over-generated: 84.
- The over-generation count is the 84 extra integer labels implied by the pseudo-range `obj11` through `obj133` beyond the 39 golden grouped labels.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Initially, we have 39 packages labeled from obj11 to obj133, 13 trucks named tru1 to tru13, 13 cities known as cit1 to cit13, and several locations, both positional and airport, across these cities. | Initially, for each integer i from 1 through 13, there are exactly three packages whose names are formed by concatenating obj, i, and each of 1, 2, and 3; one truck named by concatenating tru and i; one city named by concatenating cit and i; and two locations named by concatenating pos and i and apt and i, with the latter also being an airport. | The package pseudo-range over-generated 84 labels, and the locations were neither finitely named nor typed. / 包裹伪范围会多生成 84 个标签，而且地点既未被有限地命名，也未明确类型。 | golden_problem.pddl:lines 4-98: complete object declarations<br>golden_problem.pddl:lines 101-208: unary package, truck, city, location, airport, and airplane facts |
| 2 | Each city hosts a position and an airport, for example, pos1 and apt1 are within cit1. | For each integer i from 1 through 13, the position named by concatenating pos and i and the airport named by concatenating apt and the same i are both within the city named by concatenating cit and i. | One example did not establish the other 24 required in-city atoms. / 单个示例不能建立其余 24 个必需的地点—城市关系。 | golden_problem.pddl:lines 265-290: all 26 in-city atoms |
| 3 | Correspondingly, each truck, along with its respective packages, is located at a position within a city. For instance, tru1 and packages obj11, obj12, obj13 are located at pos1 within cit1. | For each integer i from 1 through 13, the truck named by concatenating tru and i and the three packages named by concatenating obj, i, and each of 1, 2, and 3 are all initially located at the position named by concatenating pos and the same i. | The vague correspondence plus one example did not define the other 48 initial truck/package locations. / 模糊的对应描述加一个示例，不能定义其余 48 个卡车/包裹初始位置。 | golden_problem.pddl:lines 213-264: all 52 initial truck/package at atoms |

## Material deliberately preserved / 有意保留的实质文本

- The opening sentence and both airplane sentences were preserved verbatim.
- The complete two-paragraph goal wording, including all 38 goal pairs, was preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 95/95
- Init atoms covered: 190/190
- Goal atoms covered: 38/38
- Ledger rows: 323 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked against its sibling atoms.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** all golden objects, init atoms, and conjunctive goal atoms are uniquely covered, and all four final defect counts are zero. / **最终断言：**全部黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p76

Case artifacts: [p76/](p76/)


**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Two local substitutions are necessary because 'similarly' and 'continuing in the same way' do not uniquely support the unlisted initial-location and in-city atoms.
中文：需要改写。必须进行两处局部替换，因为“同样”及“以同样方式继续”无法唯一支持未列出的初始位置原子和地点—城市原子。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem; authoritative for this audit.
- `natural_original.txt`: original English description.
- Parsed totals: **95 objects**, **190 init atoms**, **38 goal atoms**, **323 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 95/95
- Init atoms covered: 124/190
- Goal atoms covered: 38/38
- Missing: 0; ambiguous: 66; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | The trucks and packages are initially located as follows: tru1 along with packages obj11, obj12, and obj13 are at position pos1; tru2 with obj21, obj22, and obj23 at pos2, and similarly for the other trucks at their respective positions and corresponding packages. | The trucks and packages are initially located as follows: for each integer i from 1 through 13, the truck named by concatenating tru and i and the three packages named by concatenating obj, i, and each of 1, 2, and 3 are all at the position named by concatenating pos and the same i. | 'Similarly' and 'respective/corresponding' left 44 initial at atoms without a uniquely expandable rule. / “同样”以及“各自/对应”没有为其余 44 个初始位置原子提供可唯一展开的规则。 | golden_problem.pddl:lines 213-264: all 52 initial truck/package at atoms |
| 2 | Each position and airport is situated within different cities: pos1 and apt1 in cit1, pos2 and apt2 in cit2, continuing in the same way up to pos13 and apt13 in cit13. | Each position and airport is situated within its indexed city: for each integer i from 1 through 13, the position named by concatenating pos and i and the airport named by concatenating apt and the same i are both in the city named by concatenating cit and i. | 'Continuing in the same way' did not count as a complete deterministic correspondence for the remaining 22 in-city atoms. / “以同样方式继续”不能作为其余 22 个地点—城市原子的完整确定性对应规则。 | golden_problem.pddl:lines 265-290: all 26 in-city atoms |

## Material deliberately preserved / 有意保留的实质文本

- The explicit package, vehicle, city/location, airport, and airplane sentences were preserved verbatim.
- The complete 38-atom goal sentence was preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 95/95
- Init atoms covered: 190/190
- Goal atoms covered: 38/38
- Ledger rows: 323 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked against its sibling atoms.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** all golden objects, init atoms, and conjunctive goal atoms are uniquely covered, and all four final defect counts are zero. / **最终断言：**全部黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p77

Case artifacts: [p77/](p77/)


Decision: `REWRITE REQUIRED`

The original gives open-ended sequential examples for city and ground mappings, only three of 39 irregular goal destinations, and unsupported truck/efficiency goal language. The final English repairs only those three spans with two bounded rules and the complete goal mapping.

原文用开放式顺序示例描述城市和地面映射，只给出 39 个不规则目标中的 3 个，并加入了未受支持的卡车/效率目标措辞。最终英文仅修复这三个片段，加入两条有界规则和完整目标映射。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 95/95 parsed.
- Initial-state atoms: 190/190 parsed, including all unary type facts.
- Goal atoms: 39/39 parsed.
- Total semantic items: 324.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 75/95 |
| Initial atoms covered | 96/190 |
| Goal atoms covered | 3/39 |
| Missing | 36 |
| Ambiguous/incomplete | 114 |
| Contradictory | 0 |
| Over-generated | 14 |

The 114 ambiguous items are 20 city/position objects plus 94 init items left dependent on “continuing”/“corresponding” language. The 36 missing items are the unlisted goal mappings. The 14 over-generated requirements are 13 truck-goal implications plus the unsupported efficiency objective.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Cities and their corresponding locations include: cit1 with pos1 and apt1; cit2 with pos2 and apt2; continuing sequentially up to cit13 with pos13 and apt13. | For each X from 1 to 13, city citX has locations posX and aptX, and aptX is an airport. | Replaces an open-ended sequential example with the exact finite city/location/airport construction. / 用精确的有限城市/地点/机场构造替换开放式顺序示例。 | `golden_problem.pddl:lines 4-98: CIT/POS/APT objects`<br>`golden_problem.pddl:lines 153-204: city, location, and airport type atoms`<br>`golden_problem.pddl:lines 265-290: all (IN-CITY ...) atoms` |
| 2 | Trucks and packages have initial positions within their respective city locations; for example, tru1 and obj11 to obj13 are at pos1, tru2 and obj21 to obj23 are at pos2, this continues up to tru13 having obj131 to obj133 at pos13. | For each X from 1 to 13, truck truX and packages objX1, objX2, and objX3 are initially at posX. | Replaces examples plus “this continues” with a bounded rule for all 13 trucks and 39 packages. / 用有界规则替换示例和“继续如此”的模糊说法，覆盖 13 辆卡车和 39 个包裹。 | `golden_problem.pddl:lines 213-264: all truck/package (AT ...) atoms` |
| 3 | Our goal is to rearrange packages to specific targets: obj21 to apt3, obj62 to apt8, obj133 to apt10, and similar specific end locations for each package respectively. The remaining packages and trucks need to be arranged as follows: variously in airports, positions, or cities, as specified for each, ultimately organizing the logistics for efficient distribution. | Our goal is to rearrange packages to specific targets: obj21 must be at apt3; obj62 must be at apt8; obj133 must be at apt10; obj132 must be at apt11; obj63 must be at pos10; obj92 must be at pos12; obj93 must be at apt3; obj32 must be at apt7; obj72 must be at pos2; obj91 must be at pos9; obj43 must be at pos7; obj33 must be at pos11; obj53 must be at pos8; obj31 must be at pos12; obj113 must be at apt7; obj23 must be at pos4; obj41 must be at apt13; obj52 must be at apt10; obj103 must be at pos13; obj83 must be at apt12; obj123 must be at pos6; obj73 must be at apt11; obj122 must be at apt7; obj13 must be at apt3; obj121 must be at pos7; obj82 must be at apt2; obj11 must be at apt4; obj101 must be at apt13; obj71 must be at pos3; obj131 must be at apt4; obj42 must be at apt8; obj61 must be at pos9; obj102 must be at apt2; obj112 must be at apt11; obj12 must be at pos13; obj111 must be at pos1; obj51 must be at apt12; obj22 must be at pos1; obj81 must be at apt13. All 39 package destinations must hold simultaneously. | Replaces three examples and vague remaining goals with the exact irregular 39-atom package goal and removes unsupported truck/efficiency goals. / 用精确的不规则 39 原子包裹目标替换三个示例和模糊的剩余目标，并删除未受支持的卡车/效率目标。 | `golden_problem.pddl:lines 292-332: conjunctive 39-atom goal` |

## Material deliberately preserved

- The opening framing and exhaustive 39-package list.
- The complete truck and airplane declarations.
- All four correct airplane placements.
- The original ordering from objects through initial state to goal.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 95/95 |
| Initial atoms covered | 190/190 |
| Goal atoms covered | 39/39 |
| Ledger rows | 324/324 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded and matched against its complete golden sibling family. Every direct and irregular mapping was checked atom by atom, with no extra identifier or relation introduced.

每条有界规则均已完整展开，并与其全部黄金同族项核对；每个直接和不规则映射也已逐原子检查，未引入额外标识符或关系。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p78

Case artifacts: [p78/](p78/)


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

## p79

Case artifacts: [p79/](p79/)


Decision: `NO REWRITE REQUIRED`

The original directly enumerates every object, unary type fact, initial relation, and goal atom. It contains no omission, ambiguity, contradiction, or over-generation, so the English description is preserved byte-for-byte.

原文直接枚举了每个对象、一元类型事实、初始关系和目标原子，不存在遗漏、歧义、矛盾或过度生成，因此英文描述逐字节保留。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 95/95 parsed.
- Initial-state atoms: 190/190 parsed, including all unary type facts.
- Goal atoms: 39/39 parsed.
- Total semantic items: 324.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 95/95 |
| Initial atoms covered | 190/190 |
| Goal atoms covered | 39/39 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every original evidence span is direct and unique; no rule expansion or unstated convention is needed.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of `natural_original.txt`. | The original already covers all 324 semantic items uniquely. / 原文已唯一覆盖全部 324 个语义项。 | `golden_problem.pddl:complete object/init/goal sections` |

## Material deliberately preserved

- The complete original English description; no span needed repair.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 95/95 |
| Initial atoms covered | 190/190 |
| Goal atoms covered | 39/39 |
| Ledger rows | 324/324 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded and matched against its complete golden sibling family. Every direct and irregular mapping was checked atom by atom, with no extra identifier or relation introduced.

每条有界规则均已完整展开，并与其全部黄金同族项核对；每个直接和不规则映射也已逐原子检查，未引入额外标识符或关系。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p80

Case artifacts: [p80/](p80/)


Decision: `NO REWRITE REQUIRED`

The original directly enumerates every object, unary type fact, initial relation, and goal atom. It contains no omission, ambiguity, contradiction, or over-generation, so the English description is preserved byte-for-byte.

原文直接枚举了每个对象、一元类型事实、初始关系和目标原子，不存在遗漏、歧义、矛盾或过度生成，因此英文描述逐字节保留。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 102/102 parsed.
- Initial-state atoms: 204/204 parsed, including all unary type facts.
- Goal atoms: 40/40 parsed.
- Total semantic items: 346.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 102/102 |
| Initial atoms covered | 204/204 |
| Goal atoms covered | 40/40 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every original evidence span is direct and unique; no rule expansion or unstated convention is needed.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of `natural_original.txt`. | The original already covers all 346 semantic items uniquely. / 原文已唯一覆盖全部 346 个语义项。 | `golden_problem.pddl:complete object/init/goal sections` |

## Material deliberately preserved

- The complete original English description; no span needed repair.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 102/102 |
| Initial atoms covered | 204/204 |
| Goal atoms covered | 40/40 |
| Ledger rows | 346/346 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded and matched against its complete golden sibling family. Every direct and irregular mapping was checked atom by atom, with no extra identifier or relation introduced.

每条有界规则均已完整展开，并与其全部黄金同族项核对；每个直接和不规则映射也已逐原子检查，未引入额外标识符或关系。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p81

Case artifacts: [p81/](p81/)


## Decision

`REWRITE REQUIRED`

The original uses an over-generating package pseudo-range, examples and undefined correspondences for most initial facts, and only five examples for the 40 irregular goals. It also omits two airplane starts, implies goals for all 42 packages, and adds unsupported route-efficiency language. Bounded index rules, the complete goal list, and local scope/optimization edits repair those defects while preserving all unaffected wording.
原文使用会过度生成的包裹伪范围，以示例和未定义的对应关系代替大多数初始事实，并且对 40 个不规则目标只给出五个示例。原文还遗漏两个飞机初始位置，暗示全部 42 个包裹都有目标，并加入无支持的路线效率表述。有界索引规则、完整目标清单以及局部范围/优化措辞修改修复了这些缺陷，同时保留所有不受影响的文字。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics; 85 lines.
- `golden_problem.pddl`: 102 objects on lines 4–105; 204 init atoms on lines 108–311; 40 goal atoms on lines 314–353.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 346 semantic items.

## Before-rewrite coverage and defects

- Objects: 45/102; init: 52/204; goal: 5/40.
- Missing: 37 (two airplane starts and 35 goal pairs).
- Ambiguous: 207 (57 object items and 150 init atoms dependent on the pseudo-range, examples, `such as`, `various locations`, or undefined correspondence).
- Contradictory: 0.
- Over-generated: 94 (91 non-golden integer labels from `obj11` through `obj143`, two extra package goals implied by “each package,” and one efficiency objective).

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `Specifically, we have packages named obj11 through obj143, and our fleet includes trucks tru1 to tru14, and airplanes apn1 to apn4.` | `Specifically, for every integer X from 1 through 14, we have packages objX1, objX2, and objX3, where X is replaced by its decimal numeral in each identifier (so X = 10 yields obj101, obj102, and obj103); our fleet includes trucks tru1 to tru14, and airplanes apn1 to apn4.` | Replaces the pseudo-range with the exact 42-package construction; valid vehicle ranges remain. / 用精确的 42 包裹构造替换伪范围；正确的交通工具范围保持不变。 | Package objects: lines 8–10, 16–18, 23–25, 30–32, 37–39, 45–47, 52–54, 59–61, 66–68, 74–76, 81–83, 88–90, 95–97, 103–105; package types: lines 108–149. |
| 2 | `Our cities, numbered cit1 to cit14, contain specific positions and airports.` | `Our cities, numbered cit1 to cit14, each contain a position and an airport; specifically, for every integer X from 1 through 14, posX is a location in citX and aptX is an airport location in citX.` | Supplies exact location/airport identifiers, types, and all city memberships. / 补充精确的地点/机场标识符、类型和全部城市隶属关系。 | `golden_problem.pddl:164–219`, `284–311`. |
| 3 | `Trucks are stationed at positions such as pos1 in cit1 and pos2 in cit2, corresponding to the packages they need to load initially.` | `For every integer X from 1 through 14, truck truX and packages objX1, objX2, and objX3 are stationed at posX initially.` | Replaces examples and undefined correspondence with the complete finite placement rule. / 用完整的有限位置规则替换示例和未定义对应。 | `golden_problem.pddl:228–283`: 56 truck/package `AT` atoms. |
| 4 | `Airplanes, on the other hand, start at specific airports such as apn1 at apt3 in cit3 and apn2 at apt4 in cit4.` | `Airplanes, on the other hand, start at specific airports: apn1 at apt3 in cit3, apn2 at apt4 in cit4, apn3 at apt8 in cit8, and apn4 at apt4 in cit4.` | Removes `such as` and adds the two omitted starts. / 删除“例如”并补充两个遗漏位置。 | `golden_problem.pddl:224–227`. |
| 5 | First goal-introduction occurrence of `each package` | `the packages listed below` | Restricts the goal to the 40 golden goal subjects. / 将目标限定为 40 个黄金目标主体。 | `golden_problem.pddl:313–354`. |
| 6 | `The main objectives include moving obj52 to pos7, obj142 to apt4, and obj42 to pos10 among others. Each package's final destination is clearly defined, such as obj11 going to apt5 and obj123 to pos7.` | `The main objectives are to move obj52 to pos7; obj142 to apt4; obj42 to pos10; obj11 to apt5; obj123 to pos7; obj33 to pos4; obj112 to apt14; obj113 to apt8; obj61 to apt8; obj73 to apt5; obj132 to apt12; obj111 to pos11; obj103 to apt11; obj51 to apt3; obj122 to pos10; obj31 to pos7; obj72 to apt11; obj131 to apt13; obj91 to apt8; obj13 to apt11; obj41 to apt14; obj102 to pos13; obj12 to apt9; obj23 to pos12; obj83 to apt4; obj62 to apt4; obj81 to apt8; obj92 to apt13; obj43 to apt7; obj143 to pos4; obj82 to apt11; obj32 to apt13; obj133 to apt3; obj71 to pos9; obj63 to apt1; obj21 to pos1; obj93 to apt4; obj141 to pos9; obj53 to pos1; and obj101 to pos13.` | Replaces examples and `among others` with all 40 irregular pairs. / 用全部 40 个不规则目标对替换示例和“其他”。 | `golden_problem.pddl:314–353`. |
| 7 | `optimizing` | `selecting` | Removes an unsupported optimization criterion. / 删除无支持的优化标准。 | `golden_problem.pddl:313–354` has no metric. |
| 8 | Closing occurrence of `each package` | `each listed package` | Prevents two extra package goals. / 防止产生两个额外包裹目标。 | `golden_problem.pddl:313–354`. |
| 9 | `efficiently` | *(deleted)* | Removes the remaining unsupported optimization implication. / 删除剩余的无支持优化含义。 | `golden_problem.pddl:313–354` has no metric. |
| 10 | `such as trucks and airplanes` | `namely trucks and airplanes` | Closes the vehicle-mode inventory instead of suggesting unnamed modes. / 封闭交通方式清单，避免暗示未命名方式。 | Complete truck/airplane objects: `golden_problem.pddl:7,11,15,22,29,36,40,44,51,58,65,69,73,80,87,94,98,102`. |
| 11 | `various locations` | `the specified locations` | Refers the overview to the exact bounded rules rather than a vague set. / 使概述指向精确的有界规则，而非模糊集合。 | `golden_problem.pddl:178–219`: complete location/airport inventories. |

## Material deliberately preserved

- The opening challenge and initial-state overview were preserved as compatible summaries; exact rules later provide the evidence.
- The valid truck, airplane, and city ranges and the goal/planning organization were retained.
- All unaffected wording in the closing sentence was preserved.

## Post-rewrite verification

- Objects: 102/102; init: 204/204; goal: 40/40; ledger: 346/346 rows.
- X = 1…14 expands to exactly 42 packages, 14 trucks, 14 cities, 28 locations, 14 airports, 56 truck/package placements, and 28 city memberships.
- The goal sentence contains exactly the 40 golden pairs; missing 0, ambiguous 0, contradictory 0, over-generated 0.

Every golden item has unique direct or deterministic-rule evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据或确定性规则证据，最终描述没有引入任何额外项。

## p82

Case artifacts: [p82/](p82/)


## Decision

`REWRITE REQUIRED`

The original gives exact examples for indices 1–3 and 14 but relies on “this pattern continues” and “and so forth” for the remaining objects and initial facts. It states only seven of 41 irregular goals and then implies a target for every package; it also calls all targets “new,” although two golden goals equal their initial locations. Two bounded rules, a full goal list, and two local scope/newness repairs are sufficient.
原文为索引 1–3 和 14 给出精确示例，但其余对象和初始事实依赖“该模式继续”和“等等”。原文只陈述 41 个不规则目标中的七个，随后却暗示每个包裹都有目标；它还把所有目标称为“新”地点，但两个黄金目标与其初始位置相同。两条有界规则、一份完整目标清单以及两处局部范围/新旧措辞修复即可解决问题。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics; 85 lines.
- `golden_problem.pddl`: 102 objects on lines 4–105; 204 init atoms on lines 108–311; 41 goal atoms on lines 314–354.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 347 semantic items.

## Before-rewrite coverage and defects

- Objects: 45/102; init: 80/204; goal: 7/41.
- Missing: 34 omitted irregular goal pairs.
- Ambiguous: 181 (57 object items and 124 init atoms dependent on continuation phrases rather than a complete rule).
- Contradictory: 0; over-generated: 1 (the unlisted package implied to have a goal by “Each package”).

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | `This pattern continues up to packages obj141, obj142, and obj143 at location pos14 with truck tru14.` | `For every integer X from 1 through 14, truck truX and packages objX1, objX2, and objX3 are initially at posX, where X is replaced by the same decimal numeral in every identifier (so X = 10 yields tru10, obj101, obj102, obj103, and pos10).` | Defines every package/truck identifier and all 56 placements while retaining the preceding exact examples. / 定义每个包裹/卡车标识符及全部 56 个位置，同时保留前面的精确示例。 | Objects: lines 7–10, 15–18, 22–25, 29–39, 44–105; placements: `golden_problem.pddl:228–283`. |
| 2 | `Each location is associated with a specific city, so pos1 and airport apt1 are in city cit1, pos2 and airport apt2 are in city cit2, and so forth, up to pos14 and airport apt14 in city cit14.` | `For every integer X from 1 through 14, posX is a location in citX and aptX is an airport location in citX.` | Replaces `and so forth` with exact types and 28 same-index city memberships. / 用精确类型和 28 个同索引城市隶属关系替换“等等”。 | `golden_problem.pddl:164–219`, `284–311`. |
| 3 | `Our objective is to transport these packages to new destinations.` | `Our objective is for the packages listed below to reach their target destinations.` | Limits scope to the goal conjunction and accommodates goals already true initially. / 将范围限定为目标合取式，并容纳初始时已成立的目标。 | Goal scope: lines 313–355; unchanged `(AT OBJ62 POS6)` at lines 250/323 and `(AT OBJ111 POS11)` at lines 269/348. |
| 4 | `Specifically, we want obj52 at airport apt13, obj101 at airport apt10, obj42 at location apt11, obj83 at pos14, obj143 at pos11, obj91 at pos5, obj41 at apt14, and continue this relocation for all listed packages.` | `Specifically, we want obj52 at apt13; obj101 at apt10; obj42 at apt11; obj83 at pos14; obj143 at pos11; obj91 at pos5; obj41 at apt14; obj22 at apt12; obj131 at apt12; obj62 at pos6; obj71 at apt13; obj141 at apt9; obj61 at pos13; obj13 at pos3; obj82 at pos14; obj63 at pos13; obj11 at apt3; obj102 at pos14; obj123 at apt12; obj12 at apt10; obj21 at apt11; obj72 at apt2; obj122 at apt10; obj121 at pos6; obj92 at pos12; obj103 at apt3; obj43 at pos3; obj73 at pos14; obj53 at apt9; obj133 at pos10; obj23 at apt4; obj31 at pos11; obj81 at pos13; obj132 at pos2; obj111 at pos11; obj113 at pos6; obj93 at pos1; obj32 at pos10; obj142 at pos12; obj112 at apt1; and obj51 at apt14.` | Replaces seven examples and vague continuation with all 41 irregular pairs. / 用全部 41 个不规则目标对替换七个示例和模糊续写。 | `golden_problem.pddl:314–354`. |
| 5 | `Each package has a specific new target location` | `Each listed package has a specific target location` | Restricts scope to the 41 listed subjects and removes incorrect newness. / 将范围限定为列出的 41 个主体并删除不正确的“新”。 | `golden_problem.pddl:313–355`; unchanged goals at lines 323 and 348. |

## Material deliberately preserved

- The opening and exact initial placement examples for indices 1, 2, and 3.
- The complete ordered airplane-start sentence.
- Goal framing and destination classification apart from the necessary scope/newness wording.

## Post-rewrite verification

- Objects: 102/102; init: 204/204; goal: 41/41; ledger: 347/347 rows.
- X = 1…14 expands to the exact 42-package, 14-truck, 14-city, 28-location initial instance, with no extras.
- The goal sentence contains exactly 41 pairs; missing 0, ambiguous 0, contradictory 0, over-generated 0.

Every golden item has unique direct or deterministic-rule evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据或确定性规则证据，最终描述没有引入任何额外项。

## p83

Case artifacts: [p83/](p83/)


## Decision

`NO REWRITE REQUIRED`

The original directly enumerates all 102 objects and unary types, every initial airplane/truck/package location, all 28 location-to-city relations, and all 41 irregular goal pairs. It contains no ambiguity, contradiction, or extra object, fact, or goal, so the final English description is byte-for-byte identical to the original.
原描述直接列出了全部 102 个对象及一元类型、每架飞机/每辆卡车/每个包裹的初始位置、全部 28 个地点到城市的关系以及全部 41 个不规则目标对。原文不含歧义、矛盾或额外对象、事实或目标，因此最终英文描述与原文逐字节一致。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics; 85 lines.
- `golden_problem.pddl`: 102 objects on lines 4–105; 204 init atoms on lines 108–311; 41 goal atoms on lines 314–354.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 347 semantic items.

## Before-rewrite coverage and defects

- Objects: 102/102; init: 204/204; goal: 41/41.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | `natural_rewritten.txt` is an exact copy of `natural_original.txt`. | Every semantic item already has direct, unique evidence and no extra item is implied. / 每个语义项都已有直接且唯一的证据，也未暗示任何额外项。 | Objects: `golden_problem.pddl:4–105`; init: lines 108–311; goal: lines 314–354. |

## Material deliberately preserved

- All exact inventories, initial placements, location-to-city mappings, and goal pairs.
- The entire one-paragraph wording and organization.

## Post-rewrite verification

- Objects: 102/102; init: 204/204; goal: 41/41; ledger: 347/347 rows.
- Byte comparison of original and final English: identical.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has unique direct evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据，最终描述没有引入任何额外项。

## p84

Case artifacts: [p84/](p84/)


## Decision

`NO REWRITE REQUIRED`

The original explicitly names all 15 objects and supports all 30 init atoms: every type, both city memberships per city, and every vehicle/package initial location. Its final sentence also states all six goal pairs as one objective. It implies no extra item, so the final English description is byte-for-byte identical to the original.
原文明确给出全部 15 个对象并支持全部 30 个初始原子：每个类型、每座城市中的两个地点关系，以及每辆交通工具和每个包裹的初始位置。最后一句还把全部六个目标对作为同一目标陈述。原文未暗示额外项，因此最终英文描述与原文逐字节一致。

## Source inventory

- `golden_domain.pddl`: authoritative Logistics semantics; 85 lines.
- `golden_problem.pddl`: 15 objects on line 3; 30 init atoms on lines 4–10; 6 goal atoms on lines 11–12.
- `natural_original.txt`: original one-paragraph English description.
- Exact total: 51 semantic items.

## Before-rewrite coverage and defects

- Objects: 15/15; init: 30/30; goal: 6/6.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | `natural_rewritten.txt` is an exact copy of `natural_original.txt`. | All 51 semantic items already have direct, unique evidence and no extra item is implied. / 全部 51 个语义项都已有直接且唯一的证据，也未暗示任何额外项。 | Objects: `golden_problem.pddl:3`; init: lines 4–10; goal: lines 11–12. |

## Material deliberately preserved

- Every object/type statement, initial position, and city membership.
- The complete six-pair goal and all original wording and organization.

## Post-rewrite verification

- Objects: 15/15; init: 30/30; goal: 6/6; ledger: 51/51 rows.
- Byte comparison of original and final English: identical.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

Every golden item has unique direct evidence, and the final description introduces no extra item.
每个黄金项都有唯一的直接证据，最终描述没有引入任何额外项。

## p85

Case artifacts: [p85/](p85/)


**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Two local edits are needed to name both airplanes and state the six initial truck locations; all package and goal mappings are already complete.
中文：需要改写。需做两处局部修改，以命名两架飞机并说明六辆卡车的初始地点；所有包裹与目标对应关系已完整。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **32 objects**, **64 init atoms**, **6 goal atoms**, **102 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 30/32
- Init atoms covered: 54/64
- Goal atoms covered: 6/6
- Missing: 6; ambiguous: 6; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | City 6 through City 1 are home to Truck 6 to Truck 1 respectively. | Truck 6 through Truck 1 are initially at the normal locations of City 6 through City 1 respectively. | The original paired trucks with cities but did not uniquely state the six initial truck locations. / 原文只把卡车与城市配对，却没有唯一说明六辆卡车的初始地点。 | golden_problem.pddl:lines 20-25: truck type atoms<br>golden_problem.pddl:lines 60-65: (AT TRUCKi CITYi-1) for i=6..1 |
| 2 | There are two airplanes initially stationed at the airport in City 4. | There are two airplanes, Plane 2 and Plane 1, initially stationed at the airport in City 4. | Two airplanes were counted and located but not individually named, so Plane 1 and Plane 2 were not recoverable as distinct objects. / 原文只说明两架飞机及其位置，却未逐一命名，因此无法恢复飞机 1 和飞机 2 这两个独立对象。 | golden_problem.pddl:line 5: plane2 and plane1 objects<br>golden_problem.pddl:lines 26-27: airplane type atoms<br>golden_problem.pddl:lines 58-59: both airplanes at city4-2 |

## Material deliberately preserved / 有意保留的实质文本

- The package, city, location, and airport descriptions were preserved because their six-city mapping is complete.
- All six explicit package initial locations and all six goal destinations were preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 32/32
- Init atoms covered: 64/64
- Goal atoms covered: 6/6
- Ledger rows: 102 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked for exact equality with the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, with all four final defect counts equal to zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p86

Case artifacts: [p86/](p86/)


**Decision:** `NO REWRITE REQUIRED`

## Finding / 结论

English: NO REWRITE REQUIRED. Every golden object, initial atom, and conjunctive goal atom is explicitly and correctly represented without ambiguity or extra facts.
中文：无需改写。每个黄金对象、初始原子和合取目标原子都已被明确且正确地表示，不存在歧义或额外事实。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **113 objects**, **226 init atoms**, **17 goal atoms**, **356 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 113/113
- Init atoms covered: 226/226
- Goal atoms covered: 17/17
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | The original was copied byte-for-byte. | Every object and atom already has direct, unique evidence; the no-rewrite gate applies. / 每个对象和原子已有直接且唯一的证据，因此适用不改写门槛。 | Complete `golden_problem.pddl` object, init, and goal sections |

## Material deliberately preserved / 有意保留的实质文本

- The entire original English description was preserved byte-for-byte because it explicitly covers every item.

## Post-rewrite verification / 改写后核验

- Objects covered: 113/113
- Init atoms covered: 226/226
- Goal atoms covered: 17/17
- Ledger rows: 356 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked for exact equality with the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, with all four final defect counts equal to zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p87

Case artifacts: [p87/](p87/)


**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. Four local sentences need repair because examples, vague regional descriptions, and a disjunction leave locations and irregular initial mappings unrecoverable.
中文：需要改写。四个局部句子需要修复，因为示例、模糊的区域描述和析取表达使地点及不规则初始映射无法恢复。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **48 objects**, **96 init atoms**, **8 goal atoms**, **152 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 46/48
- Init atoms covered: 57/96
- Goal atoms covered: 8/8
- Missing: 24; ambiguous: 17; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Locations within these cities include designated areas (like city3-2 and city2-1) and airports (such as city1-3 and city2-3). | For each integer i from 1 through 3, the locations cityi-1, cityi-2, and cityi-3 are formed by concatenating city, i, and respectively -1, -2, and -3; all three locations are in cityi, and cityi-3 is an airport. | Examples did not enumerate or deterministically construct all nine locations, three airports, and nine in-city facts. / 示例不能枚举或确定性构造全部九个地点、三个机场以及九个地点—城市关系。 | golden_problem.pddl:lines 8-9: nine location objects<br>golden_problem.pddl:lines 49-69: location, airport, and in-city atoms |
| 2 | Initially, the airplanes are positioned as follows: plane6 is at city2-3, plane5 and plane1 are both stationed at city1-3, and planes 4, 3, and 2 are at city3-3 or city2-3. | Initially, the airplanes are positioned as follows: plane6 is at city2-3, plane5 and plane1 are both stationed at city1-3, plane4 is at city3-3, and plane3 and plane2 are at city2-3. | The disjunction left the initial locations of Plane 4, Plane 3, and Plane 2 unresolved. / 析取表达使飞机 4、飞机 3 和飞机 2 的初始位置无法确定。 | golden_problem.pddl:lines 70-75: all six airplane initial locations |
| 3 | Regarding trucks: truck22 is at city3-2, trucks like truck21 and truck16 are at various city2 locations, whereas trucks 20, 18, and 13 are spread across city1 locations, and several others are in use around city3. | Regarding trucks: truck22 and truck4 are at city3-2; truck21 and truck16 are at city2-1; truck20, truck18, and truck13 are at city1-2; truck19, truck15, truck9, truck7, truck6, truck5, and truck1 are at city2-3; truck17, truck14, truck12, and truck3 are at city2-2; truck11 and truck8 are at city3-3; truck10 is at city3-1; and truck2 is at city1-1. | Vague examples and regional descriptions did not uniquely support 21 of the 22 irregular truck locations. / 模糊示例和区域性描述无法唯一支持 22 个不规则卡车位置中的 21 个。 | golden_problem.pddl:lines 76-97: all 22 truck initial locations |
| 4 | Packages are spread across the cities too: for example, package8 is at city1-2, package7 is at city2-1, package6 is at city3-2, and package5 and package1 both start at city1-3. | Packages are spread across the cities too: package8 is at city1-2; package7 is at city2-1; package6 and package2 are at city3-2; package5 and package1 are at city1-3; package4 is at city3-3; and package3 is at city2-2. | The example-only sentence omitted the initial locations of Package 4, Package 3, and Package 2. / 仅含示例的句子遗漏了包裹 4、包裹 3 和包裹 2 的初始位置。 | golden_problem.pddl:lines 98-105: all eight package initial locations |

## Material deliberately preserved / 有意保留的实质文本

- The opening context, complete package/city/vehicle inventories, and complete eight-atom goal sentence were preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 48/48
- Init atoms covered: 96/96
- Goal atoms covered: 8/8
- Ledger rows: 152 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked for exact equality with the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, with all four final defect counts equal to zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p88

Case artifacts: [p88/](p88/)


**Decision:** `NO REWRITE REQUIRED`

## Finding / 结论

English: NO REWRITE REQUIRED. Every golden object, initial atom, and conjunctive goal atom is explicitly and correctly represented without ambiguity or extra facts.
中文：无需改写。每个黄金对象、初始原子和合取目标原子都已被明确且正确地表示，不存在歧义或额外事实。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **204 objects**, **408 init atoms**, **5 goal atoms**, **617 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 204/204
- Init atoms covered: 408/408
- Goal atoms covered: 5/5
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | The original was copied byte-for-byte. | Every object and atom already has direct, unique evidence; the no-rewrite gate applies. / 每个对象和原子已有直接且唯一的证据，因此适用不改写门槛。 | Complete `golden_problem.pddl` object, init, and goal sections |

## Material deliberately preserved / 有意保留的实质文本

- The entire original English description was preserved byte-for-byte because it explicitly covers every item.

## Post-rewrite verification / 改写后核验

- Objects covered: 204/204
- Init atoms covered: 408/408
- Goal atoms covered: 5/5
- Ledger rows: 617 (one per semantic item).
- Every deterministic rule was expanded across its full finite bounds and checked for exact equality with the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, with all four final defect counts equal to zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p89

Case artifacts: [p89/](p89/)


Decision: `REWRITE REQUIRED`

The original leaves the entire location system and 59 of 61 initial placements unspecified, although its eight package goals are complete. The final English adds one finite location rule, the required irregular initial mappings, and removes the unsupported efficiency objective.

原文未指定整个地点系统以及 61 个初始位置中的 59 个，但八个包裹目标完整。最终英文加入一条有限地点规则、所需的不规则初始映射，并删除未受支持的效率目标。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 206/206 parsed.
- Initial-state atoms: 412/412 parsed, including all unary type facts.
- Goal atoms: 8/8 parsed.
- Total semantic items: 626.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 100/206 |
| Initial atoms covered | 104/412 |
| Goal atoms covered | 8/8 |
| Missing | 385 |
| Ambiguous/incomplete | 29 |
| Contradictory | 0 |
| Over-generated | 1 |

The 385 missing items are 106 location objects, 106 location-type atoms, 114 location-to-city atoms, and 59 unspecified AT atoms. The 29 airport atoms are ambiguous under “some designated as airports.” The efficiency objective is one over-generated requirement.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Each city has specific locations, including some designated as airports. | For each city index X from 1 to 29 and location index Y from 1 to 4, cityX-Y is a location in cityX, and cityX-4 is an airport. | Defines the complete 29-by-4 location family, city correspondence, and airport suffix. / 定义完整的 29×4 地点族、城市对应关系和机场后缀。 | `golden_problem.pddl:lines 14-31: all location objects`<br>`golden_problem.pddl:lines 122-382: location, airport, and in-city atoms` |
| 2 | Currently, the planes and trucks are parked at specific city locations, and packages are scattered across different places. For example, package 23 is currently located at city 26, location 2, while package 22 is at city 1, location 1. | Currently, the planes are parked as follows: plane9 is at city28-4; plane8 is at city23-4; plane7 is at city27-4; plane6 is at city29-4; plane5 is at city13-4; plane4 is at city4-4; plane3 is at city14-4; plane2 is at city14-4; plane1 is at city13-4. The trucks are parked as follows: truck29 is at city29-1; truck28 is at city28-2; truck27 is at city27-3; truck26 is at city26-1; truck25 is at city25-2; truck24 is at city24-3; truck23 is at city23-3; truck22 is at city22-3; truck21 is at city21-1; truck20 is at city20-1; truck19 is at city19-3; truck18 is at city18-2; truck17 is at city17-3; truck16 is at city16-2; truck15 is at city15-3; truck14 is at city14-3; truck13 is at city13-2; truck12 is at city12-3; truck11 is at city11-1; truck10 is at city10-2; truck9 is at city9-3; truck8 is at city8-2; truck7 is at city7-3; truck6 is at city6-3; truck5 is at city5-3; truck4 is at city4-2; truck3 is at city3-2; truck2 is at city2-3; truck1 is at city1-1. The packages are located as follows: package23 is at city26-2; package22 is at city1-1; package21 is at city3-1; package20 is at city18-2; package19 is at city17-2; package18 is at city21-1; package17 is at city1-4; package16 is at city29-4; package15 is at city1-2; package14 is at city4-4; package13 is at city10-1; package12 is at city13-1; package11 is at city24-3; package10 is at city5-4; package9 is at city9-4; package8 is at city3-4; package7 is at city13-1; package6 is at city7-3; package5 is at city16-1; package4 is at city3-2; package3 is at city17-1; package2 is at city11-1; package1 is at city21-4. | Replaces two package examples and unspecified vehicle placements with every irregular airplane, truck, and package initial location. / 用全部不规则的飞机、卡车和包裹初始位置替换两个包裹示例和未指定的车辆位置。 | `golden_problem.pddl:lines 383-443: all 61 initial (AT ...) atoms` |
| 3 | Your task is to efficiently coordinate the movement of vehicles and packages to achieve this desired outcome. | All eight listed package destinations must hold simultaneously. | Removes the unsupported efficiency objective and explicitly states the eight-way goal conjunction. / 删除未受支持的效率目标，并明确八个目标同时成立。 | `golden_problem.pddl:lines 444-451: conjunctive eight-atom goal` |

## Material deliberately preserved

- All package, city, truck, and airplane range declarations.
- The complete eight-package goal sentence, verbatim.
- The original setup-to-goal ordering.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 206/206 |
| Initial atoms covered | 412/412 |
| Goal atoms covered | 8/8 |
| Ledger rows | 626/626 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded against the golden sibling family, and every irregular initial or goal mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有界规则均已对照黄金同族项完整展开，每个不规则初始或目标映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p90

Case artifacts: [p90/](p90/)


Decision: `NO REWRITE REQUIRED`

The original directly enumerates every object, unary type fact, initial relation, and goal atom. It contains no omission, ambiguity, contradiction, or over-generation, so the English description is preserved byte-for-byte.

原文直接枚举了每个对象、一元类型事实、初始关系和目标原子，不存在遗漏、歧义、矛盾或过度生成，因此英文描述逐字节保留。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 117/117 parsed.
- Initial-state atoms: 234/234 parsed, including all unary type facts.
- Goal atoms: 19/19 parsed.
- Total semantic items: 370.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 117/117 |
| Initial atoms covered | 234/234 |
| Goal atoms covered | 19/19 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every original evidence span is direct and unique; no rule expansion or unstated convention is needed.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of `natural_original.txt`. | The original already covers all 370 semantic items uniquely. / 原文已唯一覆盖全部 370 个语义项。 | `golden_problem.pddl:complete object/init/goal sections` |

## Material deliberately preserved

- The complete original English description; no span needed repair.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 117/117 |
| Initial atoms covered | 234/234 |
| Goal atoms covered | 19/19 |
| Ledger rows | 370/370 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded against the golden sibling family, and every irregular initial or goal mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有界规则均已对照黄金同族项完整展开，每个不规则初始或目标映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p91

Case artifacts: [p91/](p91/)


Decision: `REWRITE REQUIRED`

The original omits location identifiers and all initial mappings, falsely says package locations are distinct, and supplies only four of 14 goals while implying goals for nine nongolden packages. The final English repairs exactly those spans.

原文遗漏地点标识符和全部初始映射，错误声称包裹位置彼此不同，并且只给出 14 个目标中的 4 个，同时暗示九个非黄金包裹目标。最终英文只修复这些片段。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 56/56 parsed.
- Initial-state atoms: 112/112 parsed, including all unary type facts.
- Goal atoms: 14/14 parsed.
- Total semantic items: 182.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 42/56 |
| Initial atoms covered | 42/112 |
| Goal atoms covered | 4/14 |
| Missing | 74 |
| Ambiguous/incomplete | 3 |
| Contradictory | 17 |
| Over-generated | 9 |

The 74 missing items cover 14 location objects, 14 location-type atoms, 18 in-city atoms, 18 unmapped vehicle/package AT atoms not covered by the distinctness contradiction, and 10 missing goals. Three airport atoms are ambiguous. Seventeen package AT atoms participate in shared locations and contradict “distinct”; nine packages are additionally implied to have nongolden goals.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Specifically, package23 through package1 are scattered across distinct locations. | Specifically, the initial package locations are: package23 is at city1-5; package22 is at city1-5; package21 is at city2-4; package20 is at city2-3; package19 is at city1-2; package18 is at city3-3; package17 is at city2-3; package16 is at city3-5; package15 is at city2-2; package14 is at city2-1; package13 is at city3-4; package12 is at city1-6; package11 is at city1-4; package10 is at city3-3; package9 is at city3-3; package8 is at city1-2; package7 is at city1-4; package6 is at city1-4; package5 is at city3-1; package4 is at city2-1; package3 is at city1-5; package2 is at city3-3; package1 is at city1-2. | Replaces the false claim that all packages occupy distinct locations with the complete irregular initial package mapping. / 用完整的不规则包裹初始映射替换所有包裹位于不同地点的错误说法。 | `golden_problem.pddl:lines 101-123: all package (AT ...) atoms` |
| 2 | We have three major city hubs: city1, city2, and city3, each with various locations and airports within them. | We have three major city hubs: city1, city2, and city3; for each city index X from 1 to 3 and location index Y from 1 to 6, cityX-Y is a location in cityX, and cityX-6 is an airport. | Defines all 18 location identifiers, their cities, and the -6 airport suffix. / 定义全部 18 个地点标识符、所属城市和 -6 机场后缀。 | `golden_problem.pddl:lines 8-11: location objects`<br>`golden_problem.pddl:lines 50-88: location, airport, and in-city atoms` |
| 3 | Each vehicle is stationed at specific locations within these cities. | The airplanes are stationed as follows: plane7 is at city1-6; plane6 is at city2-6; plane5 is at city1-6; plane4 is at city1-6; plane3 is at city3-6; plane2 is at city1-6; plane1 is at city2-6. The trucks are stationed as follows: truck5 is at city3-4; truck4 is at city2-3; truck3 is at city1-5; truck2 is at city1-3; truck1 is at city1-6. | Expands unspecified vehicle positions into all seven airplane and five truck locations. / 将未指定的车辆位置展开为七架飞机和五辆卡车的全部位置。 | `golden_problem.pddl:lines 89-100: vehicle (AT ...) atoms` |
| 4 | For example, package23 needs to be transported to city2-3, while package22 should remain at city1-5. Other packages need to be carefully placed according to the requirements, such as transferring package21 to city1-6 and package20 to city1-1. Our end goal is to ensure all specified packages are accurately positioned at their respective target locations, thus completing the logistics challenge. | The required package destinations are: package23 must be at city2-3; package22 must be at city1-5; package21 must be at city1-6; package20 must be at city1-1; package19 must be at city1-3; package18 must be at city1-3; package17 must be at city1-5; package16 must be at city1-1; package15 must be at city3-3; package14 must be at city1-5; package13 must be at city2-5; package12 must be at city3-2; package11 must be at city2-6; package10 must be at city1-6. All 14 listed package destinations must hold simultaneously. | Replaces four examples and vague remaining requirements with the complete irregular 14-atom goal, excluding nine packages with no golden goal. / 用完整的不规则 14 原子目标替换四个示例和模糊剩余要求，并排除没有黄金目标的九个包裹。 | `golden_problem.pddl:lines 124-137: conjunctive 14-atom goal` |

## Material deliberately preserved

- The opening framing and finite fleet declarations.
- The task-transition sentence.
- All unaffected wording and narrative order.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 56/56 |
| Initial atoms covered | 112/112 |
| Goal atoms covered | 14/14 |
| Ledger rows | 182/182 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded against the golden sibling family, and every irregular initial or goal mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有界规则均已对照黄金同族项完整展开，每个不规则初始或目标映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p92

Case artifacts: [p92/](p92/)


Decision: `REWRITE REQUIRED`

The original leaves most location identities and 66 of 72 initial placements unspecified; its seven package goals are complete. The final English adds the finite location rule, complete irregular initial mappings, and removes unsupported safety/efficiency objectives.

原文未指定大多数地点身份以及 72 个初始位置中的 66 个；七个包裹目标完整。最终英文加入有限地点规则、完整的不规则初始映射，并删除未受支持的安全/效率目标。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 116/116 parsed.
- Initial-state atoms: 232/232 parsed, including all unary type facts.
- Goal atoms: 7/7 parsed.
- Total semantic items: 355.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 91/116 |
| Initial atoms covered | 98/232 |
| Goal atoms covered | 7/7 |
| Missing | 149 |
| Ambiguous/incomplete | 10 |
| Contradictory | 0 |
| Over-generated | 2 |

The 149 missing items are 25 location objects, 25 location-type atoms, 33 in-city atoms, and 66 unspecified AT atoms. Ten airport atoms remain ambiguous after the one named airport. Safety and efficiency are two over-generated objectives.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Each city contains multiple locations, including airports. | For each city index X from 1 to 11 and location index Y from 1 to 3, cityX-Y is a location in cityX, and cityX-3 is an airport. | Defines the complete 11-by-3 location family, city correspondence, and airport suffix. / 定义完整的 11×3 地点族、城市对应关系和机场后缀。 | `golden_problem.pddl:lines 14-18: location objects`<br>`golden_problem.pddl:lines 102-178: location, airport, and in-city atoms` |
| 2 | The trucks and planes are stationed at specific locations within these cities at the start of the game. For example, plane1 is at airport city6-3, and truck1 is at city5-2. | Initially, the airplanes are stationed as follows: plane13 is at city10-3; plane12 is at city5-3; plane11 is at city11-3; plane10 is at city1-3; plane9 is at city9-3; plane8 is at city7-3; plane7 is at city1-3; plane6 is at city8-3; plane5 is at city7-3; plane4 is at city9-3; plane3 is at city1-3; plane2 is at city11-3; plane1 is at city6-3. The trucks are stationed as follows: truck52 is at city11-2; truck51 is at city10-1; truck50 is at city9-2; truck49 is at city8-1; truck48 is at city7-1; truck47 is at city6-1; truck46 is at city5-2; truck45 is at city4-1; truck44 is at city3-2; truck43 is at city2-2; truck42 is at city1-2; truck41 is at city7-2; truck40 is at city6-1; truck39 is at city2-3; truck38 is at city3-1; truck37 is at city2-3; truck36 is at city7-1; truck35 is at city8-2; truck34 is at city8-2; truck33 is at city7-2; truck32 is at city6-3; truck31 is at city2-2; truck30 is at city11-3; truck29 is at city1-2; truck28 is at city3-1; truck27 is at city9-2; truck26 is at city7-2; truck25 is at city1-3; truck24 is at city4-1; truck23 is at city9-2; truck22 is at city3-1; truck21 is at city1-1; truck20 is at city7-3; truck19 is at city4-3; truck18 is at city1-1; truck17 is at city4-3; truck16 is at city11-3; truck15 is at city6-2; truck14 is at city5-3; truck13 is at city5-1; truck12 is at city8-1; truck11 is at city8-1; truck10 is at city5-2; truck9 is at city8-3; truck8 is at city1-1; truck7 is at city8-2; truck6 is at city9-3; truck5 is at city10-2; truck4 is at city6-3; truck3 is at city11-1; truck2 is at city5-3; truck1 is at city5-2. | Replaces one plane and one truck example with all 13 airplane and 52 truck initial locations. / 用全部 13 架飞机和 52 辆卡车的初始位置替换一个飞机和一个卡车示例。 | `golden_problem.pddl:lines 179-243: vehicle (AT ...) atoms` |
| 3 | The packages are spread out in various locations as well; for instance, package1, package2, and package3 are all at city7-2, while package7 starts at city4-2. | The initial package locations are: package7 is at city4-2; package6 is at city4-1; package5 is at city11-2; package4 is at city2-2; package3 is at city7-2; package2 is at city7-2; package1 is at city7-2. | Replaces four package examples with the complete seven-package initial mapping. / 用完整的七包裹初始映射替换四个包裹示例。 | `golden_problem.pddl:lines 244-250: package (AT ...) atoms` |
| 4 | By using the available trucks and airplanes strategically, each package must reach its destination safely and efficiently. | All seven listed package destinations must hold simultaneously. | Removes unsupported safety and efficiency objectives and makes the seven-way goal conjunction explicit. / 删除未受支持的安全和效率目标，并明确七个目标同时成立。 | `golden_problem.pddl:lines 251-257: conjunctive seven-atom goal` |

## Material deliberately preserved

- All package, city, truck, and airplane range declarations.
- The complete seven-package goal sentence, verbatim.
- The original narrative order.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 116/116 |
| Initial atoms covered | 232/232 |
| Goal atoms covered | 7/7 |
| Ledger rows | 355/355 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every bounded rule was fully expanded against the golden sibling family, and every irregular initial or goal mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有界规则均已对照黄金同族项完整展开，每个不规则初始或目标映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p93

Case artifacts: [p93/](p93/)


**Decision:** `NO REWRITE REQUIRED`

## Finding / 结论

English: NO REWRITE REQUIRED. Every object, initial atom, and goal atom is explicitly and correctly enumerated.
中文：无需改写。每个对象、初始原子和目标原子均已明确且正确地枚举。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **81 objects**, **162 init atoms**, **8 goal atoms**, **251 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 81/81
- Init atoms covered: 162/162
- Goal atoms covered: 8/8
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | The original was copied byte-for-byte. | Every semantic item already has direct or uniquely expandable evidence; the no-rewrite gate applies. / 每个语义项已有直接或可唯一展开的证据，因此适用不改写门槛。 | Complete `golden_problem.pddl` object, init, and goal sections |

## Material deliberately preserved / 有意保留的实质文本

- The complete original English description was preserved byte-for-byte because every object and atom is explicit.

## Post-rewrite verification / 改写后核验

- Objects covered: 81/81
- Init atoms covered: 162/162
- Goal atoms covered: 8/8
- Ledger rows: 251 (one per semantic item).
- Every deterministic rule was expanded over its full finite bound and matched exactly to the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, and all four final defect counts are zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p94

Case artifacts: [p94/](p94/)


**Decision:** `NO REWRITE REQUIRED`

## Finding / 结论

English: NO REWRITE REQUIRED. The bounded cityX construction and all vehicle, package, and goal mappings are complete and unique.
中文：无需改写。有限的 cityX 构造以及所有运输工具、包裹和目标映射均完整且唯一。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **25 objects**, **50 init atoms**, **3 goal atoms**, **78 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 25/25
- Init atoms covered: 50/50
- Goal atoms covered: 3/3
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | The original was copied byte-for-byte. | Every semantic item already has direct or uniquely expandable evidence; the no-rewrite gate applies. / 每个语义项已有直接或可唯一展开的证据，因此适用不改写门槛。 | Complete `golden_problem.pddl` object, init, and goal sections |

## Material deliberately preserved / 有意保留的实质文本

- The complete original English description was preserved byte-for-byte; the finite cityX location rule and all mappings are already unique.

## Post-rewrite verification / 改写后核验

- Objects covered: 25/25
- Init atoms covered: 50/50
- Goal atoms covered: 3/3
- Ledger rows: 78 (one per semantic item).
- Every deterministic rule was expanded over its full finite bound and matched exactly to the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, and all four final defect counts are zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p95

Case artifacts: [p95/](p95/)


**Decision:** `NO REWRITE REQUIRED`

## Finding / 结论

English: NO REWRITE REQUIRED. Every object, initial atom, and goal atom has direct, contradiction-free evidence.
中文：无需改写。每个对象、初始原子和目标原子都有直接且无矛盾的证据。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **21 objects**, **42 init atoms**, **3 goal atoms**, **66 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 21/21
- Init atoms covered: 42/42
- Goal atoms covered: 3/3
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text was changed. | The original was copied byte-for-byte. | Every semantic item already has direct or uniquely expandable evidence; the no-rewrite gate applies. / 每个语义项已有直接或可唯一展开的证据，因此适用不改写门槛。 | Complete `golden_problem.pddl` object, init, and goal sections |

## Material deliberately preserved / 有意保留的实质文本

- The complete original English description was preserved byte-for-byte because every object and atom is explicit.

## Post-rewrite verification / 改写后核验

- Objects covered: 21/21
- Init atoms covered: 42/42
- Goal atoms covered: 3/3
- Ledger rows: 66 (one per semantic item).
- Every deterministic rule was expanded over its full finite bound and matched exactly to the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, and all four final defect counts are zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p96

Case artifacts: [p96/](p96/)


**Decision:** `REWRITE REQUIRED`

## Finding / 结论

English: REWRITE REQUIRED. One local deterministic rule is needed because 'corresponding trucks' does not define the index pairing for ten initial truck locations.
中文：需要改写。由于“对应的卡车”没有定义十个初始卡车位置的索引配对，因此需要加入一条局部确定性规则。

## Source inventory and totals / 来源清单与总数

- `golden_domain.pddl`: copied golden Logistics domain.
- `golden_problem.pddl`: copied golden problem and authoritative audit source.
- `natural_original.txt`: original English description.
- Parsed totals: **49 objects**, **98 init atoms**, **5 goal atoms**, **152 semantic items**.

## Before-rewrite coverage / 改写前覆盖

- Objects covered: 49/49
- Init atoms covered: 88/98
- Goal atoms covered: 5/5
- Missing: 0; ambiguous: 10; contradictory: 0; over-generated: 0.

## Complete change table / 完整改动表

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| 1 | Each city has its corresponding trucks located at the general area. | For each integer i from 1 through 10, trucki is initially located at the general area of cityi, where each occurrence of i is replaced by the same integer. | The undefined word 'corresponding' did not uniquely pair the ten trucks with the ten cities' general locations. / 未定义的“对应”一词没有唯一地将十辆卡车与十座城市的普通地点配对。 | golden_problem.pddl:lines 25-34: (TRUCK TRUCK10) through (TRUCK TRUCK1)<br>golden_problem.pddl:lines 93-102: (AT TRUCKi CITYi-1) for i=10..1 |

## Material deliberately preserved / 有意保留的实质文本

- The package, city/location, vehicle inventory, package placements, airplane placements, and complete five-atom goal were preserved verbatim.

## Post-rewrite verification / 改写后核验

- Objects covered: 49/49
- Init atoms covered: 98/98
- Goal atoms covered: 5/5
- Ledger rows: 152 (one per semantic item).
- Every deterministic rule was expanded over its full finite bound and matched exactly to the golden sibling set.
- Missing: 0; ambiguous: 0; contradictory: 0; over-generated: 0.

**Final assertion:** every golden object, init atom, and conjunctive goal atom is uniquely covered, and all four final defect counts are zero. / **最终断言：**每个黄金对象、初始原子和合取目标原子均被唯一覆盖，四项最终缺陷计数均为零。

## p97

Case artifacts: [p97/](p97/)


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

## p98

Case artifacts: [p98/](p98/)


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

## p99

Case artifacts: [p99/](p99/)


Decision: `NO REWRITE REQUIRED`

The original directly enumerates every object, unary type fact, initial relation, and goal atom. It contains no omission, ambiguity, contradiction, or over-generation, so the English description is preserved byte-for-byte.

原文直接枚举了每个对象、一元类型事实、初始关系和目标原子，不存在遗漏、歧义、矛盾或过度生成，因此英文描述逐字节保留。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 53/53 parsed.
- Initial-state atoms: 106/106 parsed, including all unary type facts.
- Goal atoms: 5/5 parsed.
- Total semantic items: 164.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 53/53 |
| Initial atoms covered | 106/106 |
| Goal atoms covered | 5/5 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every original evidence span is direct and unique; no rule expansion or unstated convention is needed.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of `natural_original.txt`. | The original already covers all 164 semantic items uniquely. / 原文已唯一覆盖全部 164 个语义项。 | `golden_problem.pddl:complete object/init/goal sections` |

## Material deliberately preserved

- The complete original English description; no span needed repair.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 53/53 |
| Initial atoms covered | 106/106 |
| Goal atoms covered | 5/5 |
| Ledger rows | 164/164 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every finite rule was expanded against its complete golden family, and every direct mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有限规则均已对照完整黄金集合展开，每个直接映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

## p100

Case artifacts: [p100/](p100/)


Decision: `NO REWRITE REQUIRED`

The original directly enumerates every object, unary type fact, initial relation, and goal atom. It contains no omission, ambiguity, contradiction, or over-generation, so the English description is preserved byte-for-byte.

原文直接枚举了每个对象、一元类型事实、初始关系和目标原子，不存在遗漏、歧义、矛盾或过度生成，因此英文描述逐字节保留。

## Source inventory and totals

- `golden_domain.pddl`: authoritative predicate and action semantics, preserved unchanged.
- `golden_problem.pddl`: authoritative objects, initial state, and goal, preserved unchanged.
- `natural_original.txt`: complete original English, preserved unchanged.
- Objects: 77/77 parsed.
- Initial-state atoms: 154/154 parsed, including all unary type facts.
- Goal atoms: 21/21 parsed.
- Total semantic items: 252.

## Before-rewrite coverage and defects

| Measure | Count |
|---|---:|
| Objects covered | 77/77 |
| Initial atoms covered | 154/154 |
| Goal atoms covered | 21/21 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every original evidence span is direct and unique; no rule expansion or unstated convention is needed.

## Complete change table

| # | Original text | Revised text | Reason / 原因 | Golden PDDL evidence |
|---:|---|---|---|---|
| — | No text changed. | Byte-for-byte copy of `natural_original.txt`. | The original already covers all 252 semantic items uniquely. / 原文已唯一覆盖全部 252 个语义项。 | `golden_problem.pddl:complete object/init/goal sections` |

## Material deliberately preserved

- The complete original English description; no span needed repair.

## Post-rewrite verification

| Measure | Count |
|---|---:|
| Objects covered | 77/77 |
| Initial atoms covered | 154/154 |
| Goal atoms covered | 21/21 |
| Ledger rows | 252/252 |
| Missing | 0 |
| Ambiguous/incomplete | 0 |
| Contradictory | 0 |
| Over-generated | 0 |

Every finite rule was expanded against its complete golden family, and every direct mapping was checked atom by atom. No extra identifier, relation, or objective remains.

每条有限规则均已对照完整黄金集合展开，每个直接映射也已逐原子检查。最终没有额外标识符、关系或目标。

Final assertion: missing, ambiguous, contradictory, and over-generated counts are all zero.

最终断言：遗漏、歧义、矛盾和过度生成计数均为零。

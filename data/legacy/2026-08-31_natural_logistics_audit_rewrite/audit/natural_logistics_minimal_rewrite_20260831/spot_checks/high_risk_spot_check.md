# High-risk Natural Logistics spot check

**Date:** 2026-08-31  
**Scope:** p25, p39, p57, p68, p77, p82, p89, and p91  
**Overall result:** **PASS (8/8)**  
**Confidence:** High

## Executive conclusion

All eight completed cases pass an independent read-only re-audit. The rewritten descriptions recover all 2,452 golden semantic items: 753 objects, 1,506 init atoms, and 193 goal atoms. Their ledgers contain exactly 2,452 unique covered rows with exact natural-language evidence. Independently expanding every relevant finite rule produced exactly the golden inventories and init states, and independently extracting every stated goal produced exactly the golden goal conjunctions. No missing, ambiguous, contradictory, or over-generated semantic item was found.

The recorded edits also pass the minimality check: replaying only the recorded replacement/insertion spans reconstructs each rewrite, apart from terminal newline normalization. Each `rewrite_notes.md` records every change category, bilingual reason, preservation decision, before/after counts, and supporting golden evidence; every cited golden-problem line reference is valid and was reconciled with the relevant object, init, or goal family.

全部八个高风险案例均通过独立只读复核。重写文本完整且唯一地恢复了 2,452 个黄金语义项，证据台账逐项覆盖且无重复。所有相关有界规则经独立展开后与黄金对象、初始状态和目标合取式完全一致；未发现遗漏、歧义、矛盾或过度生成。记录的修改也满足最小修复要求。

## Checks performed

1. Parsed every object, init atom (including unary type atoms), and goal atom from each `golden_problem.pddl`.
2. Read the Logistics domain and verified predicates `package`, `truck`, `airplane`, `airport`, `location`, `in-city`, `city`, `at`, and `in`, plus the six standard load/unload/drive/fly actions. All eight domain copies have SHA-256 `fa50210f8e39e7a38baf4c780f5370520466c67b6bee70b35c03fc93da2f5f2f`; neither domain nor problems contain a metric.
3. Expanded each rewritten finite identifier, type, city-membership, and initial-placement rule from its stated bounds and substitutions, without crediting `similarly`, examples, or generic overview phrases.
4. Compared the independently expanded object/init sets and directly enumerated goal pairs with the golden sets; checked for both omissions and extras.
5. Compared every ledger row with the parsed golden semantic set (PDDL identifiers normalized only for case, because PDDL is case-insensitive). Checked row uniqueness, `covered` status, direct/deterministic evidence kind, and exact evidence-text occurrence in `natural_rewritten.txt`.
6. Replayed the recorded edit spans against `natural_original.txt`, checked the change tables and bilingual reasons in `rewrite_notes.md`, and reconciled their golden evidence with the cited PDDL lines.
7. Re-applied the no-rewrite-if-correct gate retrospectively: each original had a demonstrated semantic defect, and each rewrite was limited to the spans needed to repair its inventory/init/goal or unsupported optimization language.

## Results

| Case | Result | Objects | Init | Goal | Ledger | Recorded changes | Independent rule/goal check |
|---|---:|---:|---:|---:|---:|---:|---|
| p25 | PASS | 83 | 166 | 7 | 256/256 | 2 | Exact city family; exact 9/5 truck partition; missing package4 placement added; 7/7 goals |
| p39 | PASS | 51 | 102 | 21 | 174/174 | 5 | `i=1..7` expands exactly; 21-package inventory and 21/21 irregular goals exact |
| p57 | PASS | 73 | 146 | 29 | 248/248 | 6 | `i=1..10` decimal construction exact, including `obj101`–`obj103`; 29/29 goals exact |
| p68 | PASS | 87 | 174 | 34 | 295/295 | 6 | `X=1..12` construction exact; 48 placements, 24 memberships, and 34/34 goals exact |
| p77 | PASS | 95 | 190 | 39 | 324/324 | 3 | `X=1..13` construction exact; 52 placements and 39/39 goals exact |
| p82 | PASS | 102 | 204 | 41 | 347/347 | 5 | `X=1..14` construction exact; 56 placements, 28 memberships, and 41/41 goals exact |
| p89 | PASS | 206 | 412 | 8 | 626/626 | 3 | `X=1..29, Y=1..4` yields exactly 116 locations/memberships; all 61 irregular starts and 8/8 goals exact |
| p91 | PASS | 56 | 112 | 14 | 182/182 | 4 | `X=1..3, Y=1..6` yields exactly 18 locations/memberships; all 35 irregular starts and 14/14 goals exact |

## Case findings

### p25 — PASS

- The three-location rule yields exactly 42 locations, 14 airports, and 42 `in-city` atoms.
- The rewritten truck sentence is a complete disjoint partition: trucks 14, 13, 12, 11, 10, 7, 5, 2, and 1 are at suffix 1; trucks 9, 8, 6, 4, and 3 are at suffix 2.
- The airplane and package starts match all 13 direct mappings, including the newly supplied `(at package4 city8-1)`; all seven goal pairs match.
- The two recorded repairs reproduce the rewrite and are the smallest sufficient semantic changes.

### p39 — PASS

- The explicit 21-package inventory has no pseudo-range extras.
- Expanding `i=1..7` yields exactly 14 location objects/types, seven airports, 14 city memberships, seven truck starts, and 21 package starts; the two airplane starts are exact.
- The 21 explicitly listed goals equal the full golden conjunction and exclude any efficiency objective.
- All five changes and their golden evidence are represented in the notes. Long inventory/goal cells use display ellipses, but the described finite inventory and full goal replacement were independently checked against the complete rewrite and atomic ledger.

### p57 — PASS

- The bounded decimal construction yields exactly 30 package names; it does not create the integer pseudo-range between `obj11` and `obj103`.
- The two same-index rules yield exactly 20 locations, ten airports, 20 city memberships, ten truck starts, and 30 package starts. Airplanes start at `apt1`, `apt4`, and `apt8` exactly.
- All 29 irregular goal pairs are explicit and simultaneous. The wording does not require every package to move and adds no optimization goal.
- All six recorded changes replay cleanly and preserve unaffected wording.

### p68 — PASS

- Expanding `X=1..12` yields exactly 36 package identifiers, including the multi-digit groups `obj101`–`obj103`, `obj111`–`obj113`, and `obj121`–`obj123`, with no pseudo-range extras.
- The city and placement rules yield exactly 24 locations, 12 airports, 24 city memberships, 12 truck starts, and 36 package starts. The three airplane city references resolve uniquely to `apt11`, `apt12`, and `apt7`.
- All 34 irregular goals are explicit and simultaneous; the unsupported “most efficient” objective was removed.
- Informational finding: the preserved phrase “spread across various locations” was not credited as evidence and does not substitute for a missing fact. The later bounded rule uniquely supplies all 48 truck/package `at` atoms, so the phrase functions only as a compatible overview and introduces no extra atom. This is consistent with minimal preservation and does not require a case-specific exception.

### p77 — PASS

- The two `X=1..13` rules yield exactly 13 cities, 26 locations, 13 airports, 26 memberships, 13 truck starts, and 39 package starts; the four airplane starts match exactly.
- The rewritten goal enumerates all and only the 39 golden package destinations and explicitly requires them simultaneously. Unsupported truck and efficiency goals are absent.
- The three recorded replacements fully account for the rewrite.

### p82 — PASS

- The `X=1..14` rules yield exactly 42 package identifiers, 14 trucks, 28 locations, 14 airports, 28 memberships, 14 truck starts, and 42 package starts. Multi-digit substitution is explicit and unique.
- Airplanes start at `apt8`, `apt9`, `apt4`, and `apt12`; all 41 listed goals exactly match the golden conjunction, including goals already true initially.
- Informational finding: the opening distribution sentence was not credited as placement evidence. The later bounded rule uniquely supplies all 56 truck/package `at` atoms, so the overview creates no unresolved correspondence or extra `in` relation.
- All five recorded changes are necessary local repairs and replay to the final rewrite.

### p89 — PASS

- Expanding `X=1..29, Y=1..4` yields exactly 116 location objects/types, 116 city memberships, and the 29 suffix-4 airports.
- The explicit mapping contains all and only 9 airplane, 29 truck, and 23 package starts (61 total).
- The eight package destinations match the complete golden goal and are explicitly simultaneous; the efficiency implication is absent.
- All three changes and cited golden families reconcile exactly.

### p91 — PASS

- Expanding `X=1..3, Y=1..6` yields exactly 18 locations/types, 18 city memberships, and three suffix-6 airports.
- The rewrite explicitly supplies all 23 package, seven airplane, and five truck starts (35 total), including repeated locations that invalidate the original “distinct” claim.
- All and only the 14 golden package goals are listed; nine packages without golden goals are not over-generated into the conjunction.
- All four changes replay exactly and are supported by the cited golden ranges.

## Final bilingual conclusion

**English:** PASS for p25, p39, p57, p68, p77, p82, p89, and p91. No case defect was found, and no case edit is recommended. The completed artifacts satisfy the universal minimal-rewrite gate, exact semantic coverage, deterministic compression, ledger completeness, change accounting, and bilingual reporting requirements.

**中文：** p25、p39、p57、p68、p77、p82、p89 和 p91 均为 **PASS**。未发现案例缺陷，也不建议修改任何案例文件。现有产物满足通用最小重写门槛、精确语义覆盖、确定性压缩、逐项证据台账、修改记录及双语报告要求。

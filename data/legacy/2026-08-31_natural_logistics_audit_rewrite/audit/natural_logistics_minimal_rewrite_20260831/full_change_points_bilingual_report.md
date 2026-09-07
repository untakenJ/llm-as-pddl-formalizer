# Natural Logistics Full Change-Point Audit

# Natural Logistics 全量改写点审计

- Problems audited / 审计题目：100 / 100
- Rewritten descriptions / 需要改写：49
- Preserved verbatim / 原样保留：51
- Recorded change points / 改写点：144
- Semantic items verified / 核验语义项目：19,718 / 19,718
- Mechanical validation / 机械验证：100 / 100

The following register contains every recorded change span, its replacement, bilingual reason, and golden PDDL evidence. Original and revised spans remain in English because they are source text; explanatory analysis is bilingual and adjacent.

以下清单收录全部改写片段、替换文本、中英文原因及 golden PDDL 证据。原文与改写文本保留英文源文，分析说明按中英文相邻呈现。

## Category summary / 类别汇总

| Category | 中文 | Change points |
|---|---|---:|
| missing_rule | 补充缺失规则 | 51 |
| ambiguity | 消除歧义 | 46 |
| contradiction | 修正矛盾 | 31 |
| irregular_mapping | 补全不规则映射 | 16 |

## p06 - 2 changes / 2 个改写点

Objects 22 · Init 44 · Goal 8 · Semantic items 74

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | nine packages labeled from obj11 to obj33 |
| Revised text / 改写文本 | nine packages labeled obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, and obj33 |
| Reason | The pseudo-range does not uniquely construct the nine golden labels and can imply 14 non-golden labels.<br>该伪范围无法唯一构造九个黄金标签，并可能暗示 14 个非黄金标签。 |
| Golden PDDL evidence | golden_problem.pddl:3: (:objects ... obj33 obj32 obj31 obj23 obj22 obj21 obj13 obj12 obj11) \| golden_problem.pddl:4-5: (package obj11) ... (package obj33) |

### Change 2 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | obj33 remains at apt3 |
| Revised text / 改写文本 | obj33 is moved to apt3 |
| Reason | The persistence word conflicts with obj33's golden initial location at pos3; only its goal is apt3.<br>该持续状态用词与 obj33 在 pos3 的黄金初始位置冲突；只有其目标位置是 apt3。 |
| Golden PDDL evidence | golden_problem.pddl:11: (at obj33 pos3) \| golden_problem.pddl:14-15: (at obj33 apt3) |


## p09 - 1 changes / 1 个改写点

Objects 29 · Init 58 · Goal 10 · Semantic items 97

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | nine packages named obj11 through obj43 |
| Revised text / 改写文本 | twelve packages named obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, and obj43 |
| Reason | Corrects the false count and replaces a pseudo-range that would over-generate 21 nonexistent package identifiers.<br>更正错误总数，并替换会过度生成 21 个不存在包裹标识符的伪范围。 |
| Golden PDDL evidence | golden_problem.pddl:3: object declarations \| golden_problem.pddl:4-6: (package obj11) through (package obj43), exactly twelve listed atoms |


## p10 - 1 changes / 1 个改写点

Objects 29 · Init 58 · Goal 10 · Semantic items 97

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | None - insertion / 无 - 新增 |
| Revised text / 改写文本 | The locations apt1 through apt4 are airports. |
| Reason | Adds the missing airport typing for apt3 through a bounded rule that expands to exactly the four golden airport atoms.<br>通过一条恰好展开为四个黄金机场原子的有界规则，补充 apt3 缺失的机场类型。 |
| Golden PDDL evidence | golden_problem.pddl:8-10: location and airport atoms for apt1 through apt4 |


## p11 - 1 changes / 1 个改写点

Objects 29 · Init 58 · Goal 11 · Semantic items 98

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | None - insertion / 无 - 新增 |
| Revised text / 改写文本 | The positions pos1 through pos4 and the airports apt1 through apt4 are all locations. |
| Reason | Adds exact bounded typing evidence for four location atoms and three airport atoms that were only generically or indirectly suggested.<br>为原文仅笼统或间接暗示的四个地点原子和三个机场原子增加精确有界的类型证据。 |
| Golden PDDL evidence | golden_problem.pddl:8-10: location and airport atoms for pos1 through pos4 and apt1 through apt4 |


## p12 - 2 changes / 2 个改写点

Objects 15 · Init 30 · Goal 4 · Semantic items 49

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | These are part of city cit1. |
| Revised text / 改写文本 | Position pos1 is part of city cit1. |
| Reason | Names pos1 as the subject of the required city-membership fact and removes three extra package-city implications.<br>明确以 pos1 作为所需城市隶属事实的主语，并消除三个额外的包裹-城市暗示。 |
| Golden PDDL evidence | golden_problem.pddl:9: (in-city pos1 cit1) |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | None - insertion / 无 - 新增 |
| Revised text / 改写文本 | Both airports are locations. |
| Reason | The immediately preceding sentence defines exactly apt1 and apt2 as the two airports, so this rule expands to exactly two location atoms.<br>紧邻前句恰好将 apt1 和 apt2 定义为两个机场，因此该规则恰好展开为两个地点原子。 |
| Golden PDDL evidence | golden_problem.pddl:6: (location apt1) and (location apt2) |


## p16 - 2 changes / 2 个改写点

Objects 37 · Init 74 · Goal 13 · Semantic items 124

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | holding packages obj31, obj32, and obj33 |
| Revised text / 改写文本 | along with packages obj31, obj32, and obj33 |
| Reason | The original implies truck containment; the golden init instead has three package-at-pos3 atoms and no matching in atoms.<br>原文暗示包裹装在卡车内；黄金初始状态给出三个包裹位于 pos3 的原子，且没有相应的 in 原子。 |
| Golden PDDL evidence | golden_problem.pddl:14: (at obj31 pos3) \| golden_problem.pddl:14: (at obj32 pos3) \| golden_problem.pddl:14: (at obj33 pos3) \| golden_domain.pddl:13-14: (at ?obj ?loc) and (in ?obj ?obj) are distinct predicates |

### Change 2 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | within a specific city (cit1, cit2, cit3, cit4, cit5) |
| Revised text / 改写文本 | within its same-numbered city (cit1, cit2, cit3, cit4, cit5) |
| Reason | The original lists five cities without defining which position-airport pair belongs to which city; the same-number rule uniquely yields exactly the ten golden in-city atoms.<br>原文列出五座城市，却未定义位置-机场对与城市的对应关系；同编号规则唯一地产生恰好十个黄金 in-city 原子。 |
| Golden PDDL evidence | golden_problem.pddl:16-19: (in-city pos1 cit1) through (in-city apt5 cit5), matched by shared numeric index |


## p18 - 3 changes / 3 个改写点

Objects 37 · Init 74 · Goal 14 · Semantic items 125

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | three airplanes named apn1 and apn2 |
| Revised text / 改写文本 | two airplanes named apn1 and apn2 |
| Reason | The golden problem declares and types exactly two airplanes.<br>黄金问题只声明并标注了两架飞机。 |
| Golden PDDL evidence | golden_problem.pddl:3: apn2 apn1 \| golden_problem.pddl:11-12: (airplane apn1) (airplane apn2) |

### Change 2 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | each containing locations such as |
| Revised text / 改写文本 | along with locations |
| Reason | The original scope could suggest non-golden cross-city memberships; the revised phrase is only an inventory, followed by the retained exact mapping.<br>原作用域可能暗示黄金 PDDL 中不存在的跨城市归属；修订后仅表示清单，随后仍有保留的精确映射。 |
| Golden PDDL evidence | golden_problem.pddl:16-19: the ten exact (in-city ...) atoms |

### Change 3 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | carrying obj51, obj52, and obj53 |
| Revised text / 改写文本 | with packages obj51, obj52, and obj53 |
| Reason | The golden init locates all three packages at pos5 and contains no loaded-cargo atoms.<br>黄金初始状态将三个包裹都置于 pos5，且不含任何装载关系原子。 |
| Golden PDDL evidence | golden_problem.pddl:15-16: (at tru5 pos5) (at obj51 pos5) (at obj52 pos5) (at obj53 pos5) |


## p19 - 1 changes / 1 个改写点

Objects 37 · Init 74 · Goal 14 · Semantic items 125

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | None - insertion / 无 - 新增 |
| Revised text / 改写文本 | For each index i from 1 through 5, position posi and airport apti are locations in city citi, where i is replaced by that index in all three identifiers. |
| Reason | A bounded index rule supplies the four missing city-membership atoms and expands to exactly the complete golden ten-pair family.<br>有界索引规则补足四个缺失的城市归属原子，并恰好展开为黄金 PDDL 中完整的十对关系。 |
| Golden PDDL evidence | golden_problem.pddl:3: pos1..pos5, apt1..apt5, cit1..cit5 objects \| golden_problem.pddl:8-11: city, location, and airport type atoms \| golden_problem.pddl:16-19: ten exact (in-city ...) atoms |


## p22 - 3 changes / 3 个改写点

Objects 32 · Init 64 · Goal 6 · Semantic items 102

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | There are six packages, named package1 through package6, and each is located in different places across six cities, labeled city1 through city6. |
| Revised text / 改写文本 | There are six packages, named package1 through package6, and six cities, labeled city1 through city6. |
| Reason | Removes the unsupported implication that the six packages occupy different places; package3 and package4 are co-located.<br>删除六个包裹位于不同地点这一无依据的含义；package3 与 package4 位于同一地点。 |
| Golden PDDL evidence | golden_problem.pddl:68: (at package4 city1-1) \| golden_problem.pddl:69: (at package3 city1-1) |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city has a distinct location labeled city]-1 and an airport labeled city]-2 (for example, city1-1 and city1-2 for city1). |
| Revised text / 改写文本 | For each N from 1 through 6, cityN has a distinct location cityN-1 and an airport location cityN-2 (for example, city1-1 and city1-2 for city1). |
| Reason | Replaces malformed placeholders with a complete bounded construction rule and states both type facts for each airport location.<br>用完整的有界构造规则替换错误占位符，并说明每个机场地点的两项类型事实。 |
| Golden PDDL evidence | golden_problem.pddl:3-7: cityN-1 and cityN-2 objects for N=1..6 \| golden_problem.pddl:28-45: location and airport type atoms \| golden_problem.pddl:46-57: in-city atoms |

### Change 3 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | The trucks are initially located at their corresponding city]-1 locations, and both airplanes are initially stationed at city4-2. |
| Revised text / 改写文本 | For each N from 1 through 6, truckN is initially located at cityN-1, and both airplanes are initially stationed at city4-2. |
| Reason | Makes the finite truck-to-location index correspondence explicit and uniquely expandable.<br>明确有限的卡车到地点索引对应关系，使其可唯一展开。 |
| Golden PDDL evidence | golden_problem.pddl:60: (at truck6 city6-1) \| golden_problem.pddl:61: (at truck5 city5-1) \| golden_problem.pddl:62: (at truck4 city4-1) \| golden_problem.pddl:63: (at truck3 city3-1) \| golden_problem.pddl:64: (at truck2 city2-1) \| golden_problem.pddl:65: (at truck1 city1-1) |


## p25 - 2 changes / 2 个改写点

Objects 83 · Init 166 · Goal 7 · Semantic items 256

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | Truck assignments: truck14 is at the first location in city14, truck13 at the first location in city13, continuing similarly down to truck1 at the first location in city1. |
| Revised text / 改写文本 | Truck assignments: trucks truck14, truck13, truck12, truck11, truck10, truck7, truck5, truck2, and truck1 are at the first location in their same-numbered cities, while trucks truck9, truck8, truck6, truck4, and truck3 are at the second location in their same-numbered cities. |
| Reason | The original continuation contradicts five golden second-location truck atoms and generates five false first-location atoms.<br>原有延续规则与五个黄金第二地点卡车原子矛盾，并生成五个错误的第一地点原子。 |
| Golden PDDL evidence | golden_problem.pddl:162: (at truck9 city9-2) \| golden_problem.pddl:163: (at truck8 city8-2) \| golden_problem.pddl:165: (at truck6 city6-2) \| golden_problem.pddl:167: (at truck4 city4-2) \| golden_problem.pddl:168: (at truck3 city3-2) |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | None - insertion / 无 - 新增 |
| Revised text / 改写文本 | Package4 is situated at the first location in city8. |
| Reason | The original has no evidence for package4's golden initial location.<br>原文没有为 package4 的黄金初始位置提供证据。 |
| Golden PDDL evidence | golden_problem.pddl:176: (at package4 city8-1) |


## p26 - 4 changes / 4 个改写点

Objects 100 · Init 200 · Goal 7 · Semantic items 307

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city has several locations and some also have airports. |
| Revised text / 改写文本 | For each N from 1 through 13, cityN has locations cityN-1, cityN-2, and cityN-3, plus the airport location cityN-4; all four locations are part of cityN. |
| Reason | A bounded rule is required to identify and type all 52 locations, all 13 airports, and all 52 city memberships.<br>需要有界规则来标识并定型全部 52 个地点、13 个机场及 52 个城市归属关系。 |
| Golden PDDL evidence | golden_problem.pddl:9-16: 52 location objects \| golden_problem.pddl:65-129: location and airport type atoms \| golden_problem.pddl:130-181: all (in-city ...) atoms |

### Change 2 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | For the initial setup, planes and trucks are stationed in different locations within their respective cities. For example, plane1 is currently located at the airport in city2, while truck23 is at a location in city13. |
| Revised text / 改写文本 | For the initial setup, the planes and trucks are stationed as follows. Plane5 is at city12-4, plane4 at city8-4, plane3 at city6-4, plane2 at city13-4, and plane1 at city2-4. Truck23 is at city13-2, truck22 at city12-3, truck21 at city11-3, truck20 at city10-1, truck19 at city9-1, truck18 at city8-2, truck17 at city7-3, truck16 at city6-3, truck15 at city5-2, truck14 at city4-1, truck13 at city3-3, truck12 at city2-1, truck11 at city1-1, truck10 at city10-3, truck9 at city8-1, truck8 at city2-2, truck7 at city9-4, truck6 at city9-2, truck5 at city8-2, truck4 at city7-3, truck3 at city7-1, truck2 at city8-1, and truck1 at city5-4. |
| Reason | The original examples do not determine the irregular five-plane and 23-truck placement mapping, and the different-locations claim conflicts with three truck co-locations.<br>原有示例无法确定不规则的五架飞机和 23 辆卡车位置映射，且“不同地点”的说法与三组卡车共址事实冲突。 |
| Golden PDDL evidence | golden_problem.pddl:182-186: five plane placements \| golden_problem.pddl:187-209: 23 truck placements, including three co-located truck pairs |

### Change 3 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | The packages are distributed as follows: package7 is at the airport in city1, package6 is at a location in city2, package5 is at the same location as truck20 in city10, package4 is at the airport in city5, package3 is at a location in city11, package2 is at the same location as truck21 in city11, and package1 is at a location in city4. |
| Revised text / 改写文本 | The packages are distributed as follows: package7 is at city1-4, package6 is at city2-3, package5 is at city10-1, package4 is at city5-4, package3 is at city11-1, package2 is at city11-3, and package1 is at city4-2. |
| Reason | The exact seven package-location identifiers cannot be recovered from vague city-only or relational wording.<br>无法从模糊的仅城市或关系性措辞恢复七个精确的包裹-地点标识符。 |
| Golden PDDL evidence | golden_problem.pddl:210-216: seven package placements |

### Change 4 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | My goal is to move these packages to specific destinations: package7 needs to reach a location in city12, package6 has to be delivered to a location in city9, package5 should be transported to the same location as package7 in city12, package4 is to be sent to the airport in city8, package3 needs to arrive at the airport in city13, package2 is to be delivered to a location in city7, and finally, package1 has to reach a location in city13. |
| Revised text / 改写文本 | My goal is to move these packages to specific destinations: package7 needs to reach city12-3, package6 has to be delivered to city9-3, package5 should be transported to city12-3, package4 is to be sent to city8-4, package3 needs to arrive at city13-4, package2 is to be delivered to city7-1, and finally, package1 has to reach city13-1. |
| Reason | Every conjunctive goal needs its exact destination because the mapping is irregular.<br>由于映射不规则，每个合取目标都需要精确目的地。 |
| Golden PDDL evidence | golden_problem.pddl:217-223: all seven goal atoms |


## p27 - 2 changes / 2 个改写点

Objects 44 · Init 88 · Goal 16 · Semantic items 148

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | Initially, we have six packages in each city, numbered from obj11 to obj63. |
| Revised text / 改写文本 | Initially, we have 18 packages labeled obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, and obj63. |
| Reason | The original count is false and its pseudo-range can generate 35 non-golden package identifiers.<br>原有数量错误，且其伪范围可能生成 35 个非黄金包裹标识符。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47: exactly 18 package objects \| golden_problem.pddl:50-67: exactly 18 package type atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | None - insertion / 无 - 新增 |
| Revised text / 改写文本 | The locations apt1 through apt6 are airports. |
| Reason | Adds the missing airport types for apt1, apt3, apt5, and apt6 through an exact finite range.<br>通过精确有限范围补充 apt1、apt3、apt5 和 apt6 缺失的机场类型。 |
| Golden PDDL evidence | golden_problem.pddl:92-97: (airport apt1) through (airport apt6) |


## p28 - 2 changes / 2 个改写点

Objects 44 · Init 88 · Goal 16 · Semantic items 148

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | There are packages labeled obj11 through obj63 and trucks labeled tru1 through tru6. |
| Revised text / 改写文本 | There are packages labeled obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, and obj63, and trucks labeled tru1 through tru6. |
| Reason | The pseudo-range can generate 35 non-golden identifiers; the exact list cannot.<br>伪范围可能生成 35 个非黄金标识符；精确列表不会。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47: exactly 18 package objects \| golden_problem.pddl:50-67: exactly 18 package type atoms |

### Change 2 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Each city, cit1 through cit6, has a position (pos1 through pos6) and an airport (apt1 through apt6). |
| Revised text / 改写文本 | Each city, cit1 through cit6, has its same-numbered position (pos1 through pos6) and its same-numbered airport (apt1 through apt6). |
| Reason | The two same-numbered modifiers uniquely pair every position and airport with its city.<br>两处“同编号”修饰语将每个位置和机场与其城市唯一配对。 |
| Golden PDDL evidence | golden_problem.pddl:126-137: (in-city pos1 cit1), (in-city apt1 cit1), ..., (in-city apt6 cit6) |


## p31 - 1 changes / 1 个改写点

Objects 44 · Init 88 · Goal 18 · Semantic items 150

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | obj11 to obj63 |
| Revised text / 改写文本 | obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, and obj63 |
| Reason | The pseudo-range can imply all integer labels from obj11 through obj63; the explicit list yields exactly the 18 golden package objects.<br>伪范围可能暗示从 obj11 到 obj63 的所有整数标签；显式列表仅生成 18 个金标包裹对象。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47: package object declarations \| golden_problem.pddl:50-67: (PACKAGE OBJ11) through (PACKAGE OBJ63) for the exact listed identifiers |


## p33 - 1 changes / 1 个改写点

Objects 51 · Init 102 · Goal 19 · Semantic items 172

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | We have seven packages labeled from obj11 to obj73. |
| Revised text / 改写文本 | We have twenty-one packages: obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, obj63, obj71, obj72, and obj73. |
| Reason | The original count contradicts the 21 golden package objects, and the endpoint range can suggest 42 unsupported integer labels. Explicit enumeration is the smallest safe repair.<br>原文的数量与黄金 PDDL 中的 21 个包裹对象冲突，而且端点范围可能暗示 42 个不受支持的整数标签。显式列举是最小且安全的修复。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,15-17,23-25,30-32,37-39,44-46,52-54: package objects \| golden_problem.pddl:57-77: (PACKAGE OBJ11) through (PACKAGE OBJ73) |


## p35 - 1 changes / 1 个改写点

Objects 51 · Init 102 · Goal 19 · Semantic items 172

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | There are seven packages to manage: |
| Revised text / 改写文本 | There are twenty-one packages to manage: |
| Reason | The sentence explicitly lists 21 golden package objects, so changing only the incorrect count removes the contradiction.<br>该句明确列出了黄金 PDDL 中的 21 个包裹对象，因此只修改错误数量即可消除冲突。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,15-17,23-25,30-32,37-39,44-46,52-54: package objects \| golden_problem.pddl:57-77: (PACKAGE OBJ11) through (PACKAGE OBJ73) |


## p37 - 1 changes / 1 个改写点

Objects 51 · Init 102 · Goal 20 · Semantic items 173

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | each containing a location and an airport |
| Revised text / 改写文本 | each containing two locations, a position and an airport |
| Reason | Explicitly states that each airport is also a location.<br>明确说明每个机场同时也是地点。 |
| Golden PDDL evidence | golden_problem.pddl:92-105: (LOCATION POS1) through (LOCATION APT7) \| golden_problem.pddl:106-112: (AIRPORT APT1) through (AIRPORT APT7) |


## p38 - 3 changes / 3 个改写点

Objects 51 · Init 102 · Goal 21 · Semantic items 174

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | each city has a position and an airport respective to them, such as pos1 and apt1 for cit1, and so forth up to pos7 and apt7 for cit7 |
| Revised text / 改写文本 | for every integer i from 1 through 7, city citi has position posi and airport apti, where citi, posi, and apti denote the prefixes cit, pos, and apt followed by the same integer i |
| Reason | Provides a finite bound and exact same-index identifier construction.<br>提供有限范围及精确的同索引标识符构造。 |
| Golden PDDL evidence | golden_problem.pddl:85-112: city, location, and airport unary atoms \| golden_problem.pddl:145-158: all same-index IN-CITY atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | This pattern continues similarly for all trucks, packages, and positions up to tru7 at pos7 with packages obj71, obj72, and obj73. |
| Revised text / 改写文本 | For each integer i from 4 through 6, truck trui and packages obji1, obji2, and obji3 are at posi, where identifiers are formed by appending i to tru and pos and by placing i between obj and each suffix 1, 2, or 3; tru7 is at pos7 with packages obj71, obj72, and obj73. |
| Reason | Replaces vague analogy with exact construction for the omitted middle groups while retaining index 7.<br>用精确构造替代模糊类推，同时保留第 7 组。 |
| Golden PDDL evidence | golden_problem.pddl:129-144: (AT TRU4 POS4) through (AT OBJ73 POS7) |

### Change 3 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | pos1 and apt1 lie in cit1, pos2 and apt2 are in cit2, and so forth up to pos7 and apt7 in cit7 |
| Revised text / 改写文本 | for every integer i from 1 through 7, posi and apti lie in citi, where posi, apti, and citi denote the prefixes pos, apt, and cit followed by the same integer i |
| Reason | Uniquely expands to all and only the 14 city-membership atoms.<br>唯一展开为且仅展开为 14 个城市隶属原子。 |
| Golden PDDL evidence | golden_problem.pddl:145-158: (IN-CITY POS1 CIT1) through (IN-CITY APT7 CIT7) |


## p39 - 5 changes / 5 个改写点

Objects 51 · Init 102 · Goal 21 · Semantic items 174

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | There are seven packages labeled from obj11 to obj73, seven trucks named tru1 to tru7, seven cities named cit1 to cit7, and seven airports, apt1 through apt7, which also serve as locations. |
| Revised text / 改写文本 | There are 21 packages: obj11, obj12, obj13, obj21, obj22, obj23, obj31, obj32, obj33, obj41, obj42, obj43, obj51, obj52, obj53, obj61, obj62, obj63, obj71, obj72, and obj73; seven trucks named tru1 to tru7; seven cities named cit1 to cit7; and seven airports, apt1 through apt7, which also serve as locations. |
| Reason | Corrects the package count and replaces an over-generating pseudo-range with the exact inventory.<br>修正包裹数量，并用精确清单替换过度生成的伪范围。 |
| Golden PDDL evidence | golden_problem.pddl:4-54: complete object inventory \| golden_problem.pddl:57-77: 21 PACKAGE atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Trucks are stationed at positions pos1 through pos7, each in their respective cities cit1 to cit7, along with three packages per position. |
| Revised text / 改写文本 | For every integer i from 1 through 7, position posi and airport apti are locations in city citi, truck trui is initially at posi, and packages obji1, obji2, and obji3 are initially at posi; in these identifiers, i is the same integer appended to pos, apt, cit, and tru and placed between obj and the package suffix 1, 2, or 3. |
| Reason | Defines every location, city mapping, truck placement, and package placement with one finite exact rule.<br>用一条有限精确规则定义全部地点、城市映射、卡车位置和包裹位置。 |
| Golden PDDL evidence | golden_problem.pddl:92-112: location and airport types \| golden_problem.pddl:117-158: truck/package AT and all IN-CITY atoms |

### Change 3 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Similarly, the positions pos2 to pos7 in cities cit2 to cit7 are each associated with one truck and three packages. |
| Revised text / 改写文本 | The preceding complete rule covers indices 2 through 7 as well. |
| Reason | Ties the remaining indices to the now-complete rule instead of an undefined analogy.<br>将其余索引绑定到完整规则，而非未定义的类推。 |
| Golden PDDL evidence | golden_problem.pddl:121-158: all index-2 through index-7 placements and city mappings |

### Change 4 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | These targets include obj61 reaching apt5, obj52 ending up at pos2, obj21 being delivered to apt5, and several other packages reaching specific airports or positions within or across the different cities. For example, obj13 should be at pos7, obj32 should arrive at apt5, and obj11 must be delivered to apt4. |
| Revised text / 改写文本 | These targets are obj61 reaching apt5, obj52 ending up at pos2, obj21 being delivered to apt5, obj53 remaining at pos5, obj63 reaching pos2, obj62 reaching apt2, obj22 reaching apt4, obj23 reaching apt2, obj31 reaching apt7, obj42 reaching pos5, obj13 reaching pos7, obj72 reaching pos5, obj71 reaching apt6, obj33 reaching apt4, obj12 reaching apt2, obj73 reaching apt4, obj32 reaching apt5, obj11 reaching apt4, obj43 reaching apt4, obj41 reaching apt6, and obj51 remaining at pos5. |
| Reason | Enumerates all 21 irregular goal pairs rather than giving examples.<br>列举全部 21 个不规则目标对，而非仅给示例。 |
| Golden PDDL evidence | golden_problem.pddl:161-181: complete 21-atom goal conjunction |

### Change 5 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | to meet the specified destinations efficiently |
| Revised text / 改写文本 | to meet the specified destinations |
| Reason | Removes an unsupported optimization implication.<br>删除无支持的优化含义。 |
| Golden PDDL evidence | golden_problem.pddl:160-182: destination conjunction with no metric |


## p42 - 4 changes / 4 个改写点

Objects 58 · Init 116 · Goal 23 · Semantic items 197

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | This pattern continues up to city cit8, where packages obj81, obj82, and obj83 are located at pos8. |
| Revised text / 改写文本 | This pattern applies to every index i from 1 through 8: for each such i, where i is replaced by the same index in every identifier, the three packages obji1, obji2, and obji3 are initially at posi. |
| Reason | The vague continuation did not uniquely enumerate package groups 3-7 or their initial positions. The bounded substitution rule expands to exactly obji1-obji3 at posi for i=1...8.<br>原有模糊续写无法唯一枚举第 3-7 组包裹及其初始位置；有界替换规则恰好展开为 i=1...8 时 obji1-obji3 位于 posi。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,15-17,22-24,30-32,37-39,44-46,51-53,59-61 (all OBJ objects) \| golden_problem.pddl:64-87 ((PACKAGE OBJ11) through (PACKAGE OBJ83)) \| golden_problem.pddl:133-163 (all package AT atoms) |

### Change 2 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Airplanes apn1 and apn2 are at airports apt8 and apt7. |
| Revised text / 改写文本 | Airplanes apn1 and apn2 are at airports apt8 and apt7, respectively. |
| Reason | Without “respectively,” the two airplanes could not be uniquely paired with the two airports.<br>缺少“分别”时，两架飞机与两个机场之间无法唯一配对。 |
| Golden PDDL evidence | golden_problem.pddl:130: (AT APN1 APT8) \| golden_problem.pddl:131: (AT APN2 APT7) |

### Change 3 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | The locations pos1 to pos8, along with apt1 to apt8, are distributed among the cities cit1 to cit8. |
| Revised text / 改写文本 | For every index i from 1 through 8, where i is replaced by the same index in every identifier, posi and apti are locations in city citi, apti is an airport, and citi is a city. |
| Reason | “Distributed among” did not define the index correspondence, and apt3 was not otherwise explicitly typed as an airport. The replacement supplies the exact finite location, airport, city, and in-city rule.<br>“分布于”没有定义索引对应关系，且 apt3 在其他地方未被明确标为机场；替换文本给出了精确有限的地点、机场、城市及隶属城市规则。 |
| Golden PDDL evidence | golden_problem.pddl:96-103 ((CITY CIT1) through (CITY CIT8)) \| golden_problem.pddl:104-119 ((LOCATION POS1)/(LOCATION APT1) through (LOCATION POS8)/(LOCATION APT8)) \| golden_problem.pddl:120-127 ((AIRPORT APT1) through (AIRPORT APT8)) \| golden_problem.pddl:164-179 ((IN-CITY POS1 CIT1)/(IN-CITY APT1 CIT1) through index 8) |

### Change 4 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | The objective is to move all packages to their respective destinations efficiently. |
| Revised text / 改写文本 | All 23 listed destination conditions must hold simultaneously. |
| Reason | “All packages” implied an unlisted destination for obj42, and “efficiently” added an optimization objective absent from the conjunctive PDDL goal. The replacement states only the 23 listed conjuncts.<br>“所有包裹”暗示 obj42 还有未列出的目的地，而“高效地”增加了 PDDL 合取目标中不存在的优化目标；替换文本只要求列出的 23 个合取条件。 |
| Golden PDDL evidence | golden_problem.pddl:182-204 (the complete 23-atom goal; no OBJ42 goal atom and no optimization metric) |


## p43 - 2 changes / 2 个改写点

Objects 58 · Init 116 · Goal 23 · Semantic items 197

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | an airport (apt1 through apt8) |
| Revised text / 改写文本 | an airport location (apt1 through apt8) |
| Reason | Adding “location” directly supports the independent LOCATION facts for apt1-apt8 while preserving their airport type.<br>添加“地点”一词，可直接支持 apt1-apt8 各自独立的 LOCATION 事实，同时保留其机场类型。 |
| Golden PDDL evidence | golden_problem.pddl:105,107,109,111,113,115,117,119 ((LOCATION APT1) through (LOCATION APT8)) \| golden_problem.pddl:120-127 ((AIRPORT APT1) through (AIRPORT APT8)) |

### Change 2 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Airports apt1 through apt8 are scattered across cities cit1 to cit8. |
| Revised text / 改写文本 | Airports apt1 through apt8 are in cities cit1 through cit8, respectively. |
| Reason | “Scattered across” did not uniquely map each airport to a city. Ordered ranges plus “respectively” uniquely map aptN to citN.<br>“散布在”无法唯一确定每个机场所属的城市；有序范围加“分别”可唯一确定 aptN 到 citN 的映射。 |
| Golden PDDL evidence | golden_problem.pddl:165,167,169,171,173,175,177,179 ((IN-CITY APT1 CIT1) through (IN-CITY APT8 CIT8)) |


## p47 - 2 changes / 2 个改写点

Objects 66 · Init 132 · Goal 25 · Semantic items 223

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | nine packages |
| Revised text / 改写文本 | twenty-seven packages |
| Reason | The explicit inventory and golden problem contain 27 packages.<br>明确清单和黄金问题均包含 27 个包裹。 |
| Golden PDDL evidence | golden_problem.pddl:lines 9-11,16-18,23-25,30-32,38-40,45-47,52-54,59-61,67-69: package objects \| golden_problem.pddl:lines 72-98: (PACKAGE ...) facts |

### Change 2 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | nine locations, nine airports |
| Revised text / 改写文本 | eighteen locations (the nine positions and nine airports) |
| Reason | The golden problem types all nine positions and all nine airports as locations.<br>黄金问题把九个普通位置和九个机场全部标为地点。 |
| Golden PDDL evidence | golden_problem.pddl:lines 117-134: (LOCATION ...) facts \| golden_problem.pddl:lines 135-143: (AIRPORT ...) facts |


## p48 - 1 changes / 1 个改写点

Objects 66 · Init 132 · Goal 25 · Semantic items 223

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city from cit1 to cit9 has a position and an airport location (apt1 to apt9) with corresponding vehicles and packages. |
| Revised text / 改写文本 | For each integer X from 1 through 9, citX is a city, posX and aptX are locations in citX, aptX is an airport, truX is a truck, and objX1, objX2, and objX3 are packages; initially, truX and those three packages are at posX. |
| Reason | The original correspondence was undefined; the bounded X=1..9 rule uniquely supplies every required object, type, initial position, and city membership.<br>原对应关系未定义；有限的 X=1..9 规则唯一给出每个必需对象、类型、初始位置和城市隶属关系。 |
| Golden PDDL evidence | golden_problem.pddl:lines 4-69: object families \| golden_problem.pddl:lines 72-146: unary type facts \| golden_problem.pddl:lines 150-185: truck/package initial positions \| golden_problem.pddl:lines 186-203: location-city facts |


## p51 - 3 changes / 3 个改写点

Objects 66 · Init 132 · Goal 27 · Semantic items 225

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Packages are labeled from obj11 to obj93, with various trucks from tru1 to tru9, and cities from cit1 to cit9. |
| Revised text / 改写文本 | Packages are labeled objX1, objX2, and objX3 for each integer X from 1 through 9, with trucks tru1 through tru9 and cities cit1 through cit9. |
| Reason | Replace the package pseudo-range and weakened truck inventory with exact bounded constructions.<br>用精确的有限构造替换包裹伪范围和被弱化的卡车清单。 |
| Golden PDDL evidence | golden_problem.pddl:lines 4-69: exact object inventory \| golden_problem.pddl:lines 72-116: package, truck, and city type atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city contains specific locations, named as pos1 to pos9, and airports apt1 to apt9, with apt1 to apt9 designated as airports containing airplanes apn1 to apn3. |
| Revised text / 改写文本 | The locations are pos1 through pos9 and apt1 through apt9, with apt1 through apt9 designated as airports and apn1 through apn3 designated as airplanes. |
| Reason | State the exact location, airport, and airplane families without implying containment.<br>明确地点、机场和飞机对象族，且不暗示包含关系。 |
| Golden PDDL evidence | golden_problem.pddl:lines 117-134: (LOCATION ...) atoms \| golden_problem.pddl:lines 135-146: (AIRPORT ...) and (AIRPLANE ...) atoms |

### Change 3 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Trucks and packages are placed at the corresponding positions: tru1 is at pos1 with packages obj11, obj12, and obj13; tru2 is at pos2 with obj21, obj22, and obj23, and so forth up to tru9 at pos9 containing obj91, obj92, and obj93. |
| Revised text / 改写文本 | Trucks and packages are placed at the corresponding positions: for each integer X from 1 through 9, truX and packages objX1, objX2, and objX3 are at posX. |
| Reason | Replace vague continuation and containment wording with a finite same-index initial-position rule.<br>用有限的同索引初始位置规则替换模糊续写和包含关系措辞。 |
| Golden PDDL evidence | golden_problem.pddl:lines 150-185: exact truck and package (AT ...) atoms |


## p53 - 3 changes / 3 个改写点

Objects 73 · Init 146 · Goal 28 · Semantic items 247

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Specifically, the packages are labeled from obj11 to obj103, the trucks from tru1 to tru10, the cities from cit1 to cit10, and the locations which include positional areas and airports from pos1 to pos10 and apt1 to apt10, respectively. |
| Revised text / 改写文本 | Specifically, for each index i from 1 through 10, the three package labels are formed by writing obj, then i, then 1, 2, or 3; the trucks are labeled from tru1 to tru10, the cities from cit1 to cit10, and the locations which include positional areas and airports from pos1 to pos10 and apt1 to apt10, respectively. |
| Reason | The original package pseudo-range over-generates 63 identifiers; the bounded construction yields exactly the 30 golden package labels.<br>原包裹伪范围会多生成 63 个标识符；有限构造恰好产生 30 个黄金包裹标签。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47,52-54,59-61,66-68,74-76: exact OBJ declarations \| golden_problem.pddl:79-108: (PACKAGE ...) |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city contains a position and an airport: pos1 and apt1 in cit1, pos2 and apt2 in cit2, and so forth up to pos10 and apt10 in cit10. |
| Revised text / 改写文本 | Each city contains a position and an airport: for every index i from 1 through 10, pos followed by i and apt followed by i are in cit followed by the same i. |
| Reason | The continuation phrase does not define the middle location-to-city mappings.<br>延续性短语没有定义中间的地点到城市映射。 |
| Golden PDDL evidence | golden_problem.pddl:205-224: all 20 (IN-CITY ...) atoms |

### Change 3 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | For example, tru1 along with obj11, obj12, and obj13 is at pos1, tru2 with obj21, obj22, and obj23 is at pos2, and this pattern continues until tru10 at pos10 with obj101, obj102, and obj103. |
| Revised text / 改写文本 | For every index i from 1 through 10, tru followed by i and the three package labels formed by writing obj, then i, then 1, 2, or 3 are all at pos followed by the same i. |
| Reason | Examples and an undefined continuation do not uniquely state placements for indices 3 through 9.<br>示例和未定义的延续不能唯一陈述索引 3 至 9 的位置。 |
| Golden PDDL evidence | golden_problem.pddl:165-204: truck and package (AT ...) atoms |


## p54 - 4 changes / 4 个改写点

Objects 73 · Init 146 · Goal 28 · Semantic items 247

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | In the Logistics game, we start with the following initial conditions: We have several packages including obj11 through obj103, and trucks tru1 through tru10. |
| Revised text / 改写文本 | In the Logistics game, we start with the following initial conditions: for every index i from 1 through 10, the three package labels are formed by writing obj, then i, then 1, 2, or 3, and the trucks are tru1 through tru10. |
| Reason | The package pseudo-range over-generates 63 identifiers; the bounded construction yields exactly the 30 golden labels.<br>包裹伪范围会多生成 63 个标识符；有限构造恰好产生 30 个黄金标签。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47,52-54,59-61,66-68,74-76: exact OBJ declarations \| golden_problem.pddl:79-118: (PACKAGE ...) and (TRUCK ...) |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each package and truck is located in a specific position or city. |
| Revised text / 改写文本 | Initially, for every index i from 1 through 10, tru followed by i and the three package labels formed by writing obj, then i, then 1, 2, or 3 are all at pos followed by the same i. |
| Reason | The original does not provide any package/truck location mapping.<br>原句没有提供任何包裹或卡车的位置映射。 |
| Golden PDDL evidence | golden_problem.pddl:165-204: all truck and package (AT ...) atoms |

### Change 3 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | apt 10 |
| Revised text / 改写文本 | apt10 |
| Reason | The golden identifier has no internal space.<br>黄金标识符内部没有空格。 |
| Golden PDDL evidence | golden_problem.pddl:241: (AT OBJ61 APT10) |

### Change 4 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each location including pos1 through pos10 and apt1 through apt10, is situated in various cities, from cit1 to cit10. |
| Revised text / 改写文本 | Each location, including pos1 through pos10 and apt1 through apt10, is situated in a city from cit1 through cit10: for every index i from 1 through 10, pos followed by i and apt followed by i are both in cit followed by the same i, and each of apt1 through apt10 is an airport. |
| Reason | The original lacks unique in-city mappings and seven airport type facts.<br>原句缺少唯一的地点到城市映射以及七个机场类型事实。 |
| Golden PDDL evidence | golden_problem.pddl:119-158: (CITY ...), (LOCATION ...), and (AIRPORT ...) \| golden_problem.pddl:205-224: all (IN-CITY ...) atoms |


## p57 - 6 changes / 6 个改写点

Objects 73 · Init 146 · Goal 29 · Semantic items 248

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Initially, I have packages labeled obj11 through obj103 distributed in various positions. |
| Revised text / 改写文本 | For each integer i from 1 through 10, I have exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3; for example, i=1 gives obj11, obj12, and obj13, while i=10 gives obj101, obj102, and obj103. |
| Reason | Replaces an over-generating pseudo-range with a bounded construction for exactly the 30 golden packages.<br>用恰好构造 30 个黄金包裹的有界规则替换过度生成的伪范围。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47,52-54,59-61,66-68,74-76: package objects \| golden_problem.pddl:79-108: package type atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | I've got specific locations like pos1 to pos10 and airports from apt1 to apt10, with their corresponding city affiliations as cit1 through cit10. |
| Revised text / 改写文本 | For each integer i from 1 through 10, pos{i} and apt{i} are locations in cit{i}, and apt{i} is an airport, where every {i} is replaced by the same decimal integer. |
| Reason | Defines exact location identifiers, types, airport types, and city memberships.<br>精确定义地点标识符、地点类型、机场类型与城市隶属关系。 |
| Golden PDDL evidence | golden_problem.pddl:129-158: location and airport type atoms \| golden_problem.pddl:205-224: city-membership atoms |

### Change 3 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | For the trucks, tru1 through tru10 are at pos1 through pos10 respectively, each with a few packages. |
| Revised text / 改写文本 | For each integer i from 1 through 10, tru{i} is at pos{i}, and the three packages obj{i}1, obj{i}2, and obj{i}3 are at pos{i}, where every {i} is replaced by the same decimal integer. |
| Reason | Makes all regular truck and package placements uniquely expandable.<br>使全部规则性的卡车与包裹位置可以唯一展开。 |
| Golden PDDL evidence | golden_problem.pddl:165-204: truck and package placements |

### Change 4 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | specific items are relocated to other designated positions |
| Revised text / 改写文本 | specific items are at their designated locations |
| Reason | Allows unchanged initial destinations and airport locations without implying extra movement requirements.<br>允许与初始位置相同的目标和机场地点，且不暗示额外移动要求。 |
| Golden PDDL evidence | golden_problem.pddl:227-255: complete goal atoms |

### Change 5 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | For instance, I want obj63 to remain at pos6, obj93 to move to apt2, and obj72 to relocate to pos8. Some packages need to change airports or positions, such as obj12 to apt10, obj92 to apt10, and obj41 to apt4. Other packages need adjustments similarly, with clear targets of either city, airport, or position outlined. |
| Revised text / 改写文本 | The complete goal is that all of the following package locations hold simultaneously: obj63 at pos6; obj93 at apt2; obj72 at pos8; obj92 at apt10; obj41 at apt4; obj73 at pos9; obj12 at apt10; obj43 at apt5; obj53 at pos5; obj11 at pos4; obj101 at pos7; obj52 at pos10; obj91 at apt4; obj81 at apt8; obj13 at pos10; obj71 at apt1; obj61 at apt2; obj33 at apt9; obj42 at pos6; obj103 at apt4; obj83 at pos2; obj23 at pos3; obj31 at apt6; obj21 at pos6; obj102 at pos6; obj22 at apt2; obj51 at pos5; obj62 at pos4; and obj32 at apt2. |
| Reason | Enumerates all 29 irregular goal pairs and makes their conjunction explicit.<br>列举全部 29 个不规则目标对并明确其合取关系。 |
| Golden PDDL evidence | golden_problem.pddl:227-255: all 29 goal atoms |

### Change 6 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | meet the problem’s requirements efficiently |
| Revised text / 改写文本 | meet the problem’s requirements |
| Reason | Removes an unsupported optimization implication.<br>删除无支持的优化含义。 |
| Golden PDDL evidence | golden_problem.pddl:226-256: goal conjunction with no :metric \| golden_domain.pddl:4-85: no optimization criterion |


## p58 - 5 changes / 5 个改写点

Objects 73 · Init 146 · Goal 30 · Semantic items 249

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | There are packages labeled from obj11 to obj103 and trucks labeled from tru1 to tru10. |
| Revised text / 改写文本 | For each integer i from 1 through 10, there are exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3; for example, i=1 gives obj11, obj12, and obj13, while i=10 gives obj101, obj102, and obj103. The trucks are labeled from tru1 to tru10. |
| Reason | Replaces the package pseudo-range with exactly the 30 golden package identifiers.<br>用恰好 30 个黄金包裹标识符替换包裹伪范围。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47,52-54,59-61,66-68,74-76: package objects \| golden_problem.pddl:79-108: package type atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Additionally, there are airplanes labeled apn1 to apn3, and cities labeled cit1 to cit10, each with a designated location: pos1 to pos10 and airports apt1 to apt10. |
| Revised text / 改写文本 | Additionally, there are airplanes labeled apn1 to apn3 and cities labeled cit1 to cit10. For each integer i from 1 through 10, pos{i} and apt{i} are locations, and apt{i} is an airport, where every {i} is replaced by the same decimal integer. |
| Reason | Makes all location and airport types uniquely recoverable.<br>使全部地点与机场类型可被唯一恢复。 |
| Golden PDDL evidence | golden_problem.pddl:129-158: location and airport type atoms |

### Change 3 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each truck is starting at a position corresponding to the number, for instance, tru1 is at pos1, and each position contains packages with the same initial numbers as trucks and positions. |
| Revised text / 改写文本 | For each integer i from 1 through 10, tru{i} is initially at pos{i}, and obj{i}1, obj{i}2, and obj{i}3 are initially at pos{i}, where every {i} is replaced by the same decimal integer. |
| Reason | Defines the finite identifier correspondence for all truck and package placements.<br>定义全部卡车与包裹位置的有限标识符对应关系。 |
| Golden PDDL evidence | golden_problem.pddl:165-204: truck and package placements |

### Change 4 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Moreover, specific locations correspond to their respective cities; for example, pos1 and apt1 are located within cit1. |
| Revised text / 改写文本 | Moreover, for each integer i from 1 through 10, pos{i} and apt{i} are located within cit{i}, where every {i} is replaced by the same decimal integer; for example, pos1 and apt1 are located within cit1. |
| Reason | Expands the example into the exact 20-atom indexed city mapping.<br>将示例扩展为恰好 20 个原子的索引城市映射。 |
| Golden PDDL evidence | golden_problem.pddl:205-224: all city-membership atoms |

### Change 5 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | Our goal is to rearrange these packages to new designated locations: obj51 should be moved to pos2, obj43 to pos10, obj82 to apt6, obj33 should remain at pos3, and so forth. This involves packages being transported across different cities and locations, such as obj12 needing to move to pos7 and obj93 ending up at apt7. |
| Revised text / 改写文本 | The complete goal is that all of the following package locations hold simultaneously: obj51 at pos2; obj43 at pos10; obj82 at apt6; obj33 at pos3; obj61 at apt2; obj22 at pos6; obj103 at pos5; obj32 at apt7; obj12 at pos7; obj91 at apt6; obj31 at pos7; obj52 at apt5; obj83 at pos10; obj73 at apt2; obj23 at apt8; obj42 at apt8; obj62 at pos3; obj102 at apt8; obj53 at pos5; obj81 at pos6; obj93 at apt7; obj13 at pos4; obj72 at apt8; obj101 at pos1; obj71 at pos5; obj92 at pos2; obj63 at pos2; obj41 at pos8; obj11 at pos3; and obj21 at pos5. |
| Reason | Enumerates all 30 irregular goal pairs and makes their conjunction explicit.<br>列举全部 30 个不规则目标对并明确其合取关系。 |
| Golden PDDL evidence | golden_problem.pddl:227-256: all 30 goal atoms |


## p61 - 1 changes / 1 个改写点

Objects 80 · Init 160 · Goal 31 · Semantic items 271

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Initially, we have packages labeled from obj11 to obj113, eleven trucks from tru1 to tru11, and cities from cit1 to cit11. |
| Revised text / 改写文本 | Initially, for each integer i from 1 through 11, we have exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3; we also have eleven trucks from tru1 to tru11 and cities from cit1 to cit11. |
| Reason | The bounded concatenation rule yields exactly the 33 golden package labels and removes 70 labels introduced by the literal pseudo-range.<br>有界连接规则恰好生成 33 个黄金包裹标签，并删除字面伪范围引入的 70 个额外标签。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,15-17,23-25,30-32,37-39,44-46,52-54,59-61,66-68,73-75,81-83: package objects \| golden_problem.pddl:86-118: (PACKAGE ...) |


## p64 - 7 changes / 7 个改写点

Objects 80 · Init 160 · Goal 33 · Semantic items 273

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Initially, we have packages labeled obj11 through obj113, a total of 33 packages. |
| Revised text / 改写文本 | Initially, for each integer i from 1 through 11, we have exactly three packages labeled by concatenating obj, the decimal representation of i, and one of 1, 2, or 3, for a total of 33 packages. |
| Reason | The bounded construction yields exactly the 33 golden package labels.<br>有界构造恰好生成 33 个黄金包裹标签。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,15-17,23-25,30-32,37-39,44-46,52-54,59-61,66-68,73-75,81-83: package objects |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city has an airport location, apt1 through apt11, and contains one airplane: apn1 is at apt3, apn2 is at apt2, and apn3 is at apt11. |
| Revised text / 改写文本 | For each integer i from 1 through 11, the city labeled by concatenating cit and i contains the two locations labeled by concatenating pos and i and by concatenating apt and i, and the apt location is an airport; the three airplanes are apn1 at apt3, apn2 at apt2, and apn3 at apt11. |
| Reason | This states the complete same-index membership and airport rules and removes the one-airplane-per-city implication.<br>该句完整陈述同索引隶属及机场规则，并删除每城一架飞机的暗示。 |
| Golden PDDL evidence | golden_problem.pddl:141-179: location, airport, airplane, and airplane-location atoms \| golden_problem.pddl:224-245: (IN-CITY ...) |

### Change 3 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | - In city cit1, located at pos1, we have truck tru1 with packages obj11, obj12, and obj13. |
| Revised text / 改写文本 | - In city cit1, truck tru1 and packages obj11, obj12, and obj13 are initially at pos1. |
| Reason | This directly states all four co-location atoms.<br>该句直接陈述四个同地点原子。 |
| Golden PDDL evidence | golden_problem.pddl:180-183: (AT TRU1/OBJ11/OBJ12/OBJ13 POS1) |

### Change 4 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | - In city cit2, at pos2, truck tru2 holds packages obj21, obj22, and obj23. |
| Revised text / 改写文本 | - In city cit2, truck tru2 and packages obj21, obj22, and obj23 are initially at pos2. |
| Reason | This replaces unsupported in-truck containment with the four golden at-location atoms.<br>该句以四个黄金地点原子替换无支持的车内装载关系。 |
| Golden PDDL evidence | golden_problem.pddl:184-187: (AT TRU2/OBJ21/OBJ22/OBJ23 POS2) \| golden_domain.pddl:13-14: distinct (at ...) and (in ...) predicates |

### Change 5 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | - Similarly, the pattern continues across the cities up to city cit11 where truck tru11 is at pos11 with packages obj111, obj112, and obj113. Each city's airport is nearby, but initially, our focus is on the packages at different positions. |
| Revised text / 改写文本 | - For each integer i from 3 through 11, the truck labeled by concatenating tru and i and the three packages labeled by concatenating obj, i, and one of 1, 2, or 3 are initially at the position labeled by concatenating pos and i. |
| Reason | The finite rule expands to the exact remaining 36 placement atoms and removes an unsupported proximity relation.<br>有限规则恰好展开为其余 36 个位置原子，并删除无支持的邻近关系。 |
| Golden PDDL evidence | golden_problem.pddl:188-223: truck and package placements for indices 3-11 |

### Change 6 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | obj83 should remain at pos3 along with obj33 |
| Revised text / 改写文本 | obj83 should be at pos3 along with obj33 |
| Reason | Obj83 starts at pos8, so remain incorrectly implies a non-golden initial fact.<br>obj83 初始位于 pos8，因此 remain 错误暗示了非黄金初始事实。 |
| Golden PDDL evidence | golden_problem.pddl:211: (AT OBJ83 POS8) \| golden_problem.pddl:267-268: (AT OBJ83 POS3), (AT OBJ33 POS3) |

### Change 7 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | obj82 should stay at apt4 |
| Revised text / 改写文本 | obj82 should be at apt4 |
| Reason | Obj82 starts at pos8, so stay incorrectly implies a non-golden initial fact.<br>obj82 初始位于 pos8，因此 stay 错误暗示了非黄金初始事实。 |
| Golden PDDL evidence | golden_problem.pddl:210: (AT OBJ82 POS8) \| golden_problem.pddl:275: (AT OBJ82 APT4) |


## p66 - 1 changes / 1 个改写点

Objects 87 · Init 174 · Goal 34 · Semantic items 295

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | The trucks (tru1 through tru12) and their corresponding packages are positioned at locations pos1 through pos12. |
| Revised text / 改写文本 | For every integer X from 1 through 12, truck truX and packages objX1, objX2, and objX3 are positioned at posX initially, where X is replaced by the same decimal numeral in every identifier (so X = 10 yields tru10, obj101, obj102, obj103, and pos10). |
| Reason | Replaces an undefined ‘corresponding packages’ relation with a finite same-index construction that expands to exactly 12 truck and 36 package placements.<br>用有限的同索引构造替换未定义的“对应包裹”关系，该规则恰好展开为 12 个卡车位置和 36 个包裹位置。 |
| Golden PDDL evidence | golden_problem.pddl:195-242: all 48 truck/package initial AT atoms |


## p68 - 6 changes / 6 个改写点

Objects 87 · Init 174 · Goal 34 · Semantic items 295

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | In the initial setup of this logistics challenge, we have packages labeled from obj11 to obj123, which are spread across various locations. |
| Revised text / 改写文本 | In the initial setup of this logistics challenge, we have packages objX1, objX2, and objX3 for every integer X from 1 through 12, where X is replaced by its decimal numeral in each identifier (so X = 10 yields obj101, obj102, and obj103); these packages are spread across various locations. |
| Reason | Replaces the pseudo-range with the exact bounded package-identifier construction.<br>用精确且有界的包裹标识符构造替换伪范围。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,15-17,22-24,30-32,37-39,51-53,59-61,66-68,73-75,80-82,88-90: 36 package objects \| golden_problem.pddl:93-128: 36 PACKAGE atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | The scenario includes twelve cities, each having a position and an airport as a location. |
| Revised text / 改写文本 | The scenario includes twelve cities, cit1 through cit12; for every integer X from 1 through 12, posX and aptX are locations, and aptX is an airport in citX. |
| Reason | Names the complete city/location inventories and supplies exact location and airport typing with a bounded index rule.<br>明确完整的城市与地点清单，并用有界索引规则给出精确的地点和机场类型。 |
| Golden PDDL evidence | golden_problem.pddl:141-188: CITY, LOCATION, and AIRPORT atoms |

### Change 3 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Each truck and package also begins at a specific position: for example, tru1 along with packages obj11, obj12, and obj13 are at position pos1 in city 1, tru2 with packages obj21, obj22, and obj23 are situated at position pos2 in city 2, and this pattern continues similarly for all twelve trucks and positions. |
| Revised text / 改写文本 | For every integer X from 1 through 12, truck truX and packages objX1, objX2, and objX3 begin at posX. |
| Reason | Replaces examples and ‘similarly’ with one complete same-index rule for all 48 placements.<br>用一条完整的同索引规则替换示例及“类似地”表述，覆盖全部 48 个位置原子。 |
| Golden PDDL evidence | golden_problem.pddl:195-242: all truck/package initial AT atoms |

### Change 4 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Each position and airport location is designated to be within a specific city, such as pos1 and apt1 in city 1, pos2 and apt2 in city 2, continuing sequentially up to city 12. |
| Revised text / 改写文本 | For every integer X from 1 through 12, posX and aptX are in citX. |
| Reason | Makes the finite index correspondence explicit instead of relying on examples and a continuation phrase.<br>明确有限索引对应关系，不再依赖示例和续写占位语。 |
| Golden PDDL evidence | golden_problem.pddl:243-266: all 24 IN-CITY atoms |

### Change 5 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | For instance, obj13 should remain at pos1, while obj53 needs to be relocated to the airport in city 1. We need obj21 to reach the airport in city 9, obj32 to be delivered to pos12, and similar specific targets for each package listed, including obj122 arriving at pos7, obj72 being transferred to pos2, and obj111 staying at pos11. |
| Revised text / 改写文本 | Specifically, obj13 should remain at pos1; obj53 needs to be relocated to apt1; obj21 needs to reach apt9; obj32 should be delivered to pos12; obj23 should reach apt11; obj122 should arrive at pos7; obj73 should reach pos3; obj42 should reach pos6; obj22 should reach apt2; obj81 should reach apt7; obj121 should reach pos3; obj52 should reach pos9; obj11 should reach apt8; obj72 should be transferred to pos2; obj112 should reach apt11; obj111 should stay at pos11; obj93 should reach apt7; obj63 should reach pos12; obj123 should reach pos11; obj83 should reach pos6; obj33 should reach apt10; obj12 should reach apt6; obj41 should reach pos8; obj92 should reach pos6; obj61 should reach apt2; obj91 should reach apt1; obj101 should reach apt3; obj31 should reach apt1; obj62 should reach pos11; obj82 should reach apt6; obj51 should reach pos10; obj71 should reach apt2; obj113 should reach apt2; and obj43 should reach apt1. |
| Reason | Replaces seven examples and a vague placeholder with all 34 irregular goal pairs.<br>用全部 34 个不规则目标对替换七个示例和模糊占位语。 |
| Golden PDDL evidence | golden_problem.pddl:269-302: complete 34-atom goal conjunction |

### Change 6 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | the most efficient route |
| Revised text / 改写文本 | a route |
| Reason | Removes an unsupported optimization objective while preserving the closing sentence.<br>删除无 PDDL 支持的优化目标，同时保留结尾句。 |
| Golden PDDL evidence | golden_problem.pddl:268-303: destination conjunction with no metric |


## p69 - 7 changes / 7 个改写点

Objects 87 · Init 174 · Goal 35 · Semantic items 296

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Initial setup for the logistics game includes 36 packages labeled from obj11 to obj123 and 12 trucks labeled from tru1 to tru12. |
| Revised text / 改写文本 | Initial setup for the logistics game includes, for each X from 1 to 12, the three packages objX1, objX2, and objX3, and includes 12 trucks labeled from tru1 to tru12. |
| Reason | Replaces the pseudo-range obj11 to obj123 with a bounded two-index construction while preserving the truck declaration.<br>用有界的双索引构造替换 obj11 到 obj123 的伪范围，并保留卡车声明。 |
| Golden PDDL evidence | golden_problem.pddl:lines 4-90: exact object set \| golden_problem.pddl:lines 93-140: (PACKAGE ...) and (TRUCK ...) facts |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | There are also 12 cities each with a position and airport location. |
| Revised text / 改写文本 | There are also 12 cities labeled from cit1 to cit12, each with a position and airport location. |
| Reason | Adds the missing city labels while preserving the original count and city/location framing.<br>补充缺失的城市标签，同时保留原有数量和城市/地点表述。 |
| Golden PDDL evidence | golden_problem.pddl:lines 141-152: (CITY CIT1) through (CITY CIT12) |

### Change 3 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Every airplane (apn1, apn2, and apn3) is initially stationed at apt12 or apt7. |
| Revised text / 改写文本 | Every airplane (apn1, apn2, and apn3) is initially stationed as follows: apn1 and apn2 are at apt12, and apn3 is at apt7. |
| Reason | Resolves the ambiguous apt12-or-apt7 placement into the three exact initial airplane locations.<br>将含糊的 apt12 或 apt7 表述改为三架飞机各自的确切初始位置。 |
| Golden PDDL evidence | golden_problem.pddl:line 192: (AT APN1 APT12) \| golden_problem.pddl:line 193: (AT APN2 APT12) \| golden_problem.pddl:line 194: (AT APN3 APT7) |

### Change 4 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each position from pos1 to pos12 is located within its corresponding city, and similarly, each airport (apt1 to apt12) is located in its respective city. |
| Revised text / 改写文本 | For each X from 1 to 12, posX and aptX are locations in citX, and aptX is an airport. |
| Reason | Defines the index correspondence, location types, airport types, and all location-to-city relations without guessing.<br>明确索引对应、地点类型、机场类型和全部地点到城市关系，无需猜测。 |
| Golden PDDL evidence | golden_problem.pddl:lines 153-188: (LOCATION ...) and (AIRPORT ...) facts \| golden_problem.pddl:lines 243-266: (IN-CITY ...) facts |

### Change 5 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Specifically, the packages start at various locations; for example, obj11, obj12, and obj13 are at pos1, with the corresponding truck tru1. |
| Revised text / 改写文本 | Specifically, initially, for each X from 1 to 12, truck truX and packages objX1, objX2, and objX3 are at posX. |
| Reason | Replaces a vague example with the complete bounded initial mapping for all 12 trucks and 36 packages.<br>用完整有界规则替换模糊示例，覆盖 12 辆卡车和 36 个包裹的初始位置。 |
| Golden PDDL evidence | golden_problem.pddl:lines 195-242: all truck and package (AT ...) facts |

### Change 6 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | For instance, obj81 needs to be at pos1, obj62 at pos5, obj123 at pos7, obj42 at apt12, and obj112 at apt6. |
| Revised text / 改写文本 | Specifically, obj81 needs to be at pos1; obj62 needs to be at pos5; obj123 needs to be at pos7; obj42 needs to be at apt12; obj112 needs to be at apt6; obj63 needs to be at apt8; obj111 needs to be at pos5; obj122 needs to be at apt5; obj72 needs to be at pos1; obj52 needs to be at apt2; obj103 needs to be at apt3; obj61 needs to be at apt5; obj21 needs to be at apt9; obj31 needs to be at apt12; obj121 needs to be at pos12; obj41 needs to be at apt10; obj51 needs to be at apt5; obj22 needs to be at pos3; obj93 needs to be at apt10; obj13 needs to be at apt5; obj71 needs to be at pos7; obj73 needs to be at pos7; obj92 needs to be at apt2; obj12 needs to be at apt6; obj83 needs to be at apt8; obj33 needs to be at pos12; obj102 needs to be at pos11; obj23 needs to be at pos12; obj11 needs to be at apt9; obj32 needs to be at apt3; obj43 needs to be at apt7; obj91 needs to be at pos5; obj53 needs to be at apt6; obj113 needs to be at pos9; obj101 needs to be at apt12. |
| Reason | Expands the five examples into the exact irregular 35-atom goal mapping.<br>将五个示例扩展为精确的不规则 35 原子目标映射。 |
| Golden PDDL evidence | golden_problem.pddl:lines 269-303: all 35 goal atoms |

### Change 7 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | The comprehensive list outlines destinations for all packages ensuring proper distribution and logistics management to achieve the described end positions for each package. |
| Revised text / 改写文本 | These 35 package destinations must all hold simultaneously. |
| Reason | Removes the unsupported claim about all 36 packages and states that the 35 listed goals are simultaneous.<br>删除关于全部 36 个包裹的不受支持声明，并明确列出的 35 个目标同时成立。 |
| Golden PDDL evidence | golden_problem.pddl:lines 268-304: conjunctive goal containing 35 atoms |


## p70 - 4 changes / 4 个改写点

Objects 87 · Init 174 · Goal 35 · Semantic items 296

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | The packages are labeled from obj11 to obj123, the trucks are labeled from tru1 to tru12, and the airplanes are labeled apn1, apn2, and apn3. |
| Revised text / 改写文本 | For each X from 1 to 12, the three packages are labeled objX1, objX2, and objX3; the trucks are labeled from tru1 to tru12; and the airplanes are labeled apn1, apn2, and apn3. |
| Reason | Replaces the package pseudo-range with the exact bounded construction and preserves the truck and airplane declarations.<br>用精确的有界构造替换包裹伪范围，并保留卡车和飞机声明。 |
| Golden PDDL evidence | golden_problem.pddl:lines 4-90: exact object set \| golden_problem.pddl:lines 93-140 and 189-191: type facts |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | There are also twelve cities, each with two locations: a posX location and an aptX airport, where X is the city number from 1 to 12. |
| Revised text / 改写文本 | There are also twelve cities labeled from cit1 to cit12, each with two locations: a posX location and an aptX airport, where X is the city number from 1 to 12. |
| Reason | Adds the missing cit1-through-cit12 labels; the existing X rule then uniquely links posX and aptX to citX.<br>补充缺失的 cit1 到 cit12 标签，使原有 X 规则能唯一关联 posX、aptX 与 citX。 |
| Golden PDDL evidence | golden_problem.pddl:lines 141-188: city, location, and airport facts \| golden_problem.pddl:lines 243-266: location-to-city facts |

### Change 3 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Initially, each truck is located at its corresponding posX location with three corresponding packages, and each airplane is stationed at a specific airport: apn1 is at apt11, apn2 is at apt9, and apn3 is at apt2. |
| Revised text / 改写文本 | Initially, for each X from 1 to 12, truX and packages objX1, objX2, and objX3 are at posX, and each airplane is stationed at a specific airport: apn1 is at apt11, apn2 is at apt9, and apn3 is at apt2. |
| Reason | Defines the complete truck/package suffix correspondence while preserving the already-correct airplane mapping verbatim.<br>明确完整的卡车/包裹后缀对应，并逐字保留原本正确的飞机映射。 |
| Golden PDDL evidence | golden_problem.pddl:lines 192-242: all airplane, truck, and package (AT ...) facts |

### Change 4 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | The goal is to move the packages efficiently to these locations using the trucks and airplanes available. |
| Revised text / 改写文本 | All 35 listed package destinations must hold simultaneously. |
| Reason | Removes an unsupported efficiency objective and makes the conjunction of the 35 listed destinations explicit.<br>删除 PDDL 未支持的效率目标，并明确 35 个列出目的地构成合取目标。 |
| Golden PDDL evidence | golden_problem.pddl:lines 268-304: conjunctive goal containing 35 atoms |


## p73 - 3 changes / 3 个改写点

Objects 95 · Init 190 · Goal 37 · Semantic items 322

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | There are packages named obj11 through obj133 and these are located across various positions labeled pos1, pos2, ..., pos13. |
| Revised text / 改写文本 | There are exactly 39 packages: for each integer i from 1 through 13, the three package names are formed by concatenating obj, i, and each of 1, 2, and 3, and all three packages are initially located at the position named by concatenating pos and the same i. |
| Reason | The pseudo-range over-generated 84 package labels and 'across various positions' did not define the initial package-to-position mapping.<br>该伪范围会多生成 84 个包裹标签，而“分布在各种位置”没有定义包裹初始位置的对应关系。 |
| Golden PDDL evidence | golden_problem.pddl:lines 9-11,16-18,23-25,30-32,38-40,45-47,52-54,59-61,67-69,74-76,81-83,88-90,96-98: package objects \| golden_problem.pddl:lines 101-139: package type atoms \| golden_problem.pddl:lines 214-216,218-220,222-224,226-228,230-232,234-236,238-240,242-244,246-248,250-252,254-256,258-260,262-264: package initial positions |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | We also have a series of trucks, tru1 through tru13, which are stationed at these positions. |
| Revised text / 改写文本 | We also have a series of trucks, tru1 through tru13; for each integer i from 1 through 13, the truck named by concatenating tru and i is initially stationed at the position named by concatenating pos and the same i. |
| Reason | The phrase 'these positions' did not uniquely pair each truck with its initial position.<br>“这些位置”没有唯一确定每辆卡车与其初始位置的配对。 |
| Golden PDDL evidence | golden_problem.pddl:lines 140-152: (TRUCK TRU1) through (TRUCK TRU13) \| golden_problem.pddl:lines 213,217,221,225,229,233,237,241,245,249,253,257,261: truck initial positions |

### Change 3 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | The setting includes cities cit1 through cit13, each containing a position and an airport, creating a map of interrelated locations. |
| Revised text / 改写文本 | The setting includes cities cit1 through cit13; for each integer i from 1 through 13, the names citi, posi, and apti are formed by concatenating cit, pos, and apt respectively with i, posi and apti are locations, apti is an airport, and both posi and apti are in citi, creating a map of interrelated locations. |
| Reason | The original did not name every position/airport or define the shared-index city correspondence and unary location/airport facts.<br>原文没有给出全部位置与机场名称，也没有定义共享索引的城市对应关系及地点/机场类型事实。 |
| Golden PDDL evidence | golden_problem.pddl:lines 153-165: city atoms \| golden_problem.pddl:lines 166-204: location and airport atoms \| golden_problem.pddl:lines 265-290: in-city atoms |


## p75 - 3 changes / 3 个改写点

Objects 95 · Init 190 · Goal 38 · Semantic items 323

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Initially, we have 39 packages labeled from obj11 to obj133, 13 trucks named tru1 to tru13, 13 cities known as cit1 to cit13, and several locations, both positional and airport, across these cities. |
| Revised text / 改写文本 | Initially, for each integer i from 1 through 13, there are exactly three packages whose names are formed by concatenating obj, i, and each of 1, 2, and 3; one truck named by concatenating tru and i; one city named by concatenating cit and i; and two locations named by concatenating pos and i and apt and i, with the latter also being an airport. |
| Reason | The package pseudo-range over-generated 84 labels, and the locations were neither finitely named nor typed.<br>包裹伪范围会多生成 84 个标签，而且地点既未被有限地命名，也未明确类型。 |
| Golden PDDL evidence | golden_problem.pddl:lines 4-98: complete object declarations \| golden_problem.pddl:lines 101-208: unary package, truck, city, location, airport, and airplane facts |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city hosts a position and an airport, for example, pos1 and apt1 are within cit1. |
| Revised text / 改写文本 | For each integer i from 1 through 13, the position named by concatenating pos and i and the airport named by concatenating apt and the same i are both within the city named by concatenating cit and i. |
| Reason | One example did not establish the other 24 required in-city atoms.<br>单个示例不能建立其余 24 个必需的地点-城市关系。 |
| Golden PDDL evidence | golden_problem.pddl:lines 265-290: all 26 in-city atoms |

### Change 3 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Correspondingly, each truck, along with its respective packages, is located at a position within a city. For instance, tru1 and packages obj11, obj12, obj13 are located at pos1 within cit1. |
| Revised text / 改写文本 | For each integer i from 1 through 13, the truck named by concatenating tru and i and the three packages named by concatenating obj, i, and each of 1, 2, and 3 are all initially located at the position named by concatenating pos and the same i. |
| Reason | The vague correspondence plus one example did not define the other 48 initial truck/package locations.<br>模糊的对应描述加一个示例，不能定义其余 48 个卡车/包裹初始位置。 |
| Golden PDDL evidence | golden_problem.pddl:lines 213-264: all 52 initial truck/package at atoms |


## p76 - 2 changes / 2 个改写点

Objects 95 · Init 190 · Goal 38 · Semantic items 323

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | The trucks and packages are initially located as follows: tru1 along with packages obj11, obj12, and obj13 are at position pos1; tru2 with obj21, obj22, and obj23 at pos2, and similarly for the other trucks at their respective positions and corresponding packages. |
| Revised text / 改写文本 | The trucks and packages are initially located as follows: for each integer i from 1 through 13, the truck named by concatenating tru and i and the three packages named by concatenating obj, i, and each of 1, 2, and 3 are all at the position named by concatenating pos and the same i. |
| Reason | 'Similarly' and 'respective/corresponding' left 44 initial at atoms without a uniquely expandable rule.<br>“同样”以及“各自/对应”没有为其余 44 个初始位置原子提供可唯一展开的规则。 |
| Golden PDDL evidence | golden_problem.pddl:lines 213-264: all 52 initial truck/package at atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each position and airport is situated within different cities: pos1 and apt1 in cit1, pos2 and apt2 in cit2, continuing in the same way up to pos13 and apt13 in cit13. |
| Revised text / 改写文本 | Each position and airport is situated within its indexed city: for each integer i from 1 through 13, the position named by concatenating pos and i and the airport named by concatenating apt and the same i are both in the city named by concatenating cit and i. |
| Reason | 'Continuing in the same way' did not count as a complete deterministic correspondence for the remaining 22 in-city atoms.<br>“以同样方式继续”不能作为其余 22 个地点-城市原子的完整确定性对应规则。 |
| Golden PDDL evidence | golden_problem.pddl:lines 265-290: all 26 in-city atoms |


## p77 - 3 changes / 3 个改写点

Objects 95 · Init 190 · Goal 39 · Semantic items 324

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Cities and their corresponding locations include: cit1 with pos1 and apt1; cit2 with pos2 and apt2; continuing sequentially up to cit13 with pos13 and apt13. |
| Revised text / 改写文本 | For each X from 1 to 13, city citX has locations posX and aptX, and aptX is an airport. |
| Reason | Replaces an open-ended sequential example with the exact finite city/location/airport construction.<br>用精确的有限城市/地点/机场构造替换开放式顺序示例。 |
| Golden PDDL evidence | golden_problem.pddl:lines 4-98: CIT/POS/APT objects \| golden_problem.pddl:lines 153-204: city, location, and airport type atoms \| golden_problem.pddl:lines 265-290: all (IN-CITY ...) atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Trucks and packages have initial positions within their respective city locations; for example, tru1 and obj11 to obj13 are at pos1, tru2 and obj21 to obj23 are at pos2, this continues up to tru13 having obj131 to obj133 at pos13. |
| Revised text / 改写文本 | For each X from 1 to 13, truck truX and packages objX1, objX2, and objX3 are initially at posX. |
| Reason | Replaces examples plus “this continues” with a bounded rule for all 13 trucks and 39 packages.<br>用有界规则替换示例和“继续如此”的模糊说法，覆盖 13 辆卡车和 39 个包裹。 |
| Golden PDDL evidence | golden_problem.pddl:lines 213-264: all truck/package (AT ...) atoms |

### Change 3 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | Our goal is to rearrange packages to specific targets: obj21 to apt3, obj62 to apt8, obj133 to apt10, and similar specific end locations for each package respectively. The remaining packages and trucks need to be arranged as follows: variously in airports, positions, or cities, as specified for each, ultimately organizing the logistics for efficient distribution. |
| Revised text / 改写文本 | Our goal is to rearrange packages to specific targets: obj21 must be at apt3; obj62 must be at apt8; obj133 must be at apt10; obj132 must be at apt11; obj63 must be at pos10; obj92 must be at pos12; obj93 must be at apt3; obj32 must be at apt7; obj72 must be at pos2; obj91 must be at pos9; obj43 must be at pos7; obj33 must be at pos11; obj53 must be at pos8; obj31 must be at pos12; obj113 must be at apt7; obj23 must be at pos4; obj41 must be at apt13; obj52 must be at apt10; obj103 must be at pos13; obj83 must be at apt12; obj123 must be at pos6; obj73 must be at apt11; obj122 must be at apt7; obj13 must be at apt3; obj121 must be at pos7; obj82 must be at apt2; obj11 must be at apt4; obj101 must be at apt13; obj71 must be at pos3; obj131 must be at apt4; obj42 must be at apt8; obj61 must be at pos9; obj102 must be at apt2; obj112 must be at apt11; obj12 must be at pos13; obj111 must be at pos1; obj51 must be at apt12; obj22 must be at pos1; obj81 must be at apt13. All 39 package destinations must hold simultaneously. |
| Reason | Replaces three examples and vague remaining goals with the exact irregular 39-atom package goal and removes unsupported truck/efficiency goals.<br>用精确的不规则 39 原子包裹目标替换三个示例和模糊的剩余目标，并删除未受支持的卡车/效率目标。 |
| Golden PDDL evidence | golden_problem.pddl:lines 292-332: conjunctive 39-atom goal |


## p78 - 2 changes / 2 个改写点

Objects 15 · Init 30 · Goal 6 · Semantic items 51

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | Truck tru1 is located at pos1 in cit1, carrying packages obj11, obj12, and obj13. |
| Revised text / 改写文本 | Truck tru1 is located at pos1 in cit1, and packages obj11, obj12, and obj13 are also at pos1. |
| Reason | Replaces “carrying” with explicit co-location; the golden init has AT facts and no IN facts for these packages.<br>用明确的同地点表述替换“承载”；黄金初始状态含 AT 事实而不含这些包裹的 IN 事实。 |
| Golden PDDL evidence | golden_problem.pddl:lines 7-8: (AT TRU1 POS1) and package (AT ... POS1) atoms \| golden_domain.pddl:line 14: (in ?obj ?obj) is the containment predicate |

### Change 2 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Similarly, truck tru2 is located at pos2 in cit2 with packages obj21, obj22, and obj23. |
| Revised text / 改写文本 | Similarly, truck tru2 is located at pos2 in cit2, and packages obj21, obj22, and obj23 are also at pos2. |
| Reason | Makes the second truck/package relationship explicitly co-located rather than inheriting the preceding carrying interpretation.<br>明确第二组卡车和包裹是同地点关系，避免继承前句的承载含义。 |
| Golden PDDL evidence | golden_problem.pddl:lines 8-9: (AT TRU2 POS2) and package (AT ... POS2) atoms |


## p81 - 11 changes / 11 个改写点

Objects 102 · Init 204 · Goal 40 · Semantic items 346

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Specifically, we have packages named obj11 through obj143, and our fleet includes trucks tru1 to tru14, and airplanes apn1 to apn4. |
| Revised text / 改写文本 | Specifically, for every integer X from 1 through 14, we have packages objX1, objX2, and objX3, where X is replaced by its decimal numeral in each identifier (so X = 10 yields obj101, obj102, and obj103); our fleet includes trucks tru1 to tru14, and airplanes apn1 to apn4. |
| Reason | Replaces the package pseudo-range with the exact bounded identifier construction while preserving the valid truck and airplane ranges.<br>用精确的有界标识符构造替换包裹伪范围，同时保留正确的卡车和飞机范围。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47,52-54,59-61,66-68,74-76,81-83,88-90,95-97,103-105: 42 package objects \| golden_problem.pddl:108-149: PACKAGE atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Our cities, numbered cit1 to cit14, contain specific positions and airports. |
| Revised text / 改写文本 | Our cities, numbered cit1 to cit14, each contain a position and an airport; specifically, for every integer X from 1 through 14, posX is a location in citX and aptX is an airport location in citX. |
| Reason | Adds exact identifiers, types, and all 28 same-index city memberships with one finite rule.<br>用一条有限规则补充精确标识符、类型以及全部 28 个同索引城市隶属关系。 |
| Golden PDDL evidence | golden_problem.pddl:164-219: CITY, LOCATION, and AIRPORT atoms \| golden_problem.pddl:284-311: IN-CITY atoms |

### Change 3 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Trucks are stationed at positions such as pos1 in cit1 and pos2 in cit2, corresponding to the packages they need to load initially. |
| Revised text / 改写文本 | For every integer X from 1 through 14, truck truX and packages objX1, objX2, and objX3 are stationed at posX initially. |
| Reason | Replaces examples and an undefined correspondence with all 56 truck/package placements.<br>用全部 56 个卡车/包裹位置替换示例和未定义的对应关系。 |
| Golden PDDL evidence | golden_problem.pddl:228-283: truck/package initial AT atoms |

### Change 4 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Airplanes, on the other hand, start at specific airports such as apn1 at apt3 in cit3 and apn2 at apt4 in cit4. |
| Revised text / 改写文本 | Airplanes, on the other hand, start at specific airports: apn1 at apt3 in cit3, apn2 at apt4 in cit4, apn3 at apt8 in cit8, and apn4 at apt4 in cit4. |
| Reason | Removes ‘such as’ and adds the two omitted airplane starts.<br>删除“例如”并补充两个遗漏的飞机初始位置。 |
| Golden PDDL evidence | golden_problem.pddl:224-227: (AT APN1 APT3), (AT APN2 APT4), (AT APN3 APT8), (AT APN4 APT4) |

### Change 5 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | each package |
| Revised text / 改写文本 | the packages listed below |
| Reason | Restricts the stated goal to the 40 packages in the golden conjunction rather than implying goals for all 42 packages.<br>把目标限定为黄金合取式中的 40 个包裹，避免暗示全部 42 个包裹都有目标。 |
| Golden PDDL evidence | golden_problem.pddl:313-354: 40-atom goal conjunction |

### Change 6 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | The main objectives include moving obj52 to pos7, obj142 to apt4, and obj42 to pos10 among others. Each package's final destination is clearly defined, such as obj11 going to apt5 and obj123 to pos7. |
| Revised text / 改写文本 | The main objectives are to move obj52 to pos7; obj142 to apt4; obj42 to pos10; obj11 to apt5; obj123 to pos7; obj33 to pos4; obj112 to apt14; obj113 to apt8; obj61 to apt8; obj73 to apt5; obj132 to apt12; obj111 to pos11; obj103 to apt11; obj51 to apt3; obj122 to pos10; obj31 to pos7; obj72 to apt11; obj131 to apt13; obj91 to apt8; obj13 to apt11; obj41 to apt14; obj102 to pos13; obj12 to apt9; obj23 to pos12; obj83 to apt4; obj62 to apt4; obj81 to apt8; obj92 to apt13; obj43 to apt7; obj143 to pos4; obj82 to apt11; obj32 to apt13; obj133 to apt3; obj71 to pos9; obj63 to apt1; obj21 to pos1; obj93 to apt4; obj141 to pos9; obj53 to pos1; and obj101 to pos13. |
| Reason | Replaces five examples and vague continuation with all 40 irregular goal pairs.<br>用全部 40 个不规则目标对替换五个示例和模糊续写。 |
| Golden PDDL evidence | golden_problem.pddl:314-353: complete goal atom list |

### Change 7 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | optimizing |
| Revised text / 改写文本 | selecting |
| Reason | Removes an unsupported optimization criterion.<br>删除无支持的优化标准。 |
| Golden PDDL evidence | golden_problem.pddl:313-354: goal conjunction has no metric |

### Change 8 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | each package |
| Revised text / 改写文本 | each listed package |
| Reason | Prevents the closing sentence from implying goals for the two packages absent from the goal conjunction.<br>防止结尾句暗示目标合取式中未出现的两个包裹也有目标。 |
| Golden PDDL evidence | golden_problem.pddl:313-354: exact goal scope |

### Change 9 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | efficiently |
| Revised text / 改写文本 | Deleted / 删除 |
| Reason | Deletes a second unsupported optimization implication.<br>删除第二处无支持的优化含义。 |
| Golden PDDL evidence | golden_problem.pddl:313-354: no optimization metric |

### Change 10 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | such as trucks and airplanes |
| Revised text / 改写文本 | namely trucks and airplanes |
| Reason | Closes the vehicle-mode inventory instead of implying additional unnamed modes.<br>封闭交通方式清单，避免暗示其他未命名方式。 |
| Golden PDDL evidence | golden_problem.pddl:7,11,15,22,29,36,40,44,51,58,65,69,73,80,87,94,98,102: complete truck and airplane object inventory |

### Change 11 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | various locations |
| Revised text / 改写文本 | the specified locations |
| Reason | Makes the overview refer forward to the exact bounded location rules rather than a vague set.<br>使概述指向后文精确的有界地点规则，而非模糊集合。 |
| Golden PDDL evidence | golden_problem.pddl:178-219: complete location and airport inventories |


## p82 - 5 changes / 5 个改写点

Objects 102 · Init 204 · Goal 41 · Semantic items 347

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | This pattern continues up to packages obj141, obj142, and obj143 at location pos14 with truck tru14. |
| Revised text / 改写文本 | For every integer X from 1 through 14, truck truX and packages objX1, objX2, and objX3 are initially at posX, where X is replaced by the same decimal numeral in every identifier (so X = 10 yields tru10, obj101, obj102, obj103, and pos10). |
| Reason | Replaces an undefined continuation with the exact object construction and all 56 truck/package placements.<br>用精确的对象构造和全部 56 个卡车/包裹位置替换未定义的续写。 |
| Golden PDDL evidence | golden_problem.pddl:8-10,16-18,23-25,30-32,37-39,45-47,52-54,59-61,66-68,74-76,81-83,88-90,95-97,103-105: package objects \| golden_problem.pddl:150-163: trucks \| golden_problem.pddl:228-283: placements |

### Change 2 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Each location is associated with a specific city, so pos1 and airport apt1 are in city cit1, pos2 and airport apt2 are in city cit2, and so forth, up to pos14 and airport apt14 in city cit14. |
| Revised text / 改写文本 | For every integer X from 1 through 14, posX is a location in citX and aptX is an airport location in citX. |
| Reason | Replaces ‘and so forth’ with the complete bounded location/type/city rule.<br>用完整的有界地点、类型和城市规则替换“等等”。 |
| Golden PDDL evidence | golden_problem.pddl:164-219: CITY, LOCATION, AIRPORT atoms \| golden_problem.pddl:284-311: IN-CITY atoms |

### Change 3 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | Our objective is to transport these packages to new destinations. |
| Revised text / 改写文本 | Our objective is for the packages listed below to reach their target destinations. |
| Reason | Restricts the goal to the listed conjunction and avoids claiming that goal atoms already true initially require new destinations.<br>把目标限定为列出的合取式，并避免声称初始时已经成立的目标原子必须是新目的地。 |
| Golden PDDL evidence | golden_problem.pddl:313-355: exact 41-atom goal conjunction \| golden_problem.pddl:250 and 323: OBJ62 is initially and finally at POS6 \| golden_problem.pddl:269 and 348: OBJ111 is initially and finally at POS11 |

### Change 4 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | Specifically, we want obj52 at airport apt13, obj101 at airport apt10, obj42 at location apt11, obj83 at pos14, obj143 at pos11, obj91 at pos5, obj41 at apt14, and continue this relocation for all listed packages. |
| Revised text / 改写文本 | Specifically, we want obj52 at apt13; obj101 at apt10; obj42 at apt11; obj83 at pos14; obj143 at pos11; obj91 at pos5; obj41 at apt14; obj22 at apt12; obj131 at apt12; obj62 at pos6; obj71 at apt13; obj141 at apt9; obj61 at pos13; obj13 at pos3; obj82 at pos14; obj63 at pos13; obj11 at apt3; obj102 at pos14; obj123 at apt12; obj12 at apt10; obj21 at apt11; obj72 at apt2; obj122 at apt10; obj121 at pos6; obj92 at pos12; obj103 at apt3; obj43 at pos3; obj73 at pos14; obj53 at apt9; obj133 at pos10; obj23 at apt4; obj31 at pos11; obj81 at pos13; obj132 at pos2; obj111 at pos11; obj113 at pos6; obj93 at pos1; obj32 at pos10; obj142 at pos12; obj112 at apt1; and obj51 at apt14. |
| Reason | Replaces seven examples and vague continuation with all 41 irregular goal pairs.<br>用全部 41 个不规则目标对替换七个示例和模糊续写。 |
| Golden PDDL evidence | golden_problem.pddl:314-354: complete goal atom list |

### Change 5 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | Each package has a specific new target location |
| Revised text / 改写文本 | Each listed package has a specific target location |
| Reason | Limits the claim to the 41 listed packages and removes ‘new’ because two golden goals equal their initial locations.<br>把表述限定为列出的 41 个包裹，并删除“新”，因为两个黄金目标与其初始位置相同。 |
| Golden PDDL evidence | golden_problem.pddl:313-355: exact goal scope \| golden_problem.pddl:250,269,323,348: unchanged OBJ62 and OBJ111 locations |


## p85 - 2 changes / 2 个改写点

Objects 32 · Init 64 · Goal 6 · Semantic items 102

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | City 6 through City 1 are home to Truck 6 to Truck 1 respectively. |
| Revised text / 改写文本 | Truck 6 through Truck 1 are initially at the normal locations of City 6 through City 1 respectively. |
| Reason | The original paired trucks with cities but did not uniquely state the six initial truck locations.<br>原文只把卡车与城市配对，却没有唯一说明六辆卡车的初始地点。 |
| Golden PDDL evidence | golden_problem.pddl:lines 20-25: truck type atoms \| golden_problem.pddl:lines 60-65: (AT TRUCKi CITYi-1) for i=6..1 |

### Change 2 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | There are two airplanes initially stationed at the airport in City 4. |
| Revised text / 改写文本 | There are two airplanes, Plane 2 and Plane 1, initially stationed at the airport in City 4. |
| Reason | Two airplanes were counted and located but not individually named, so Plane 1 and Plane 2 were not recoverable as distinct objects.<br>原文只说明两架飞机及其位置，却未逐一命名，因此无法恢复飞机 1 和飞机 2 这两个独立对象。 |
| Golden PDDL evidence | golden_problem.pddl:line 5: plane2 and plane1 objects \| golden_problem.pddl:lines 26-27: airplane type atoms \| golden_problem.pddl:lines 58-59: both airplanes at city4-2 |


## p87 - 4 changes / 4 个改写点

Objects 48 · Init 96 · Goal 8 · Semantic items 152

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Locations within these cities include designated areas (like city3-2 and city2-1) and airports (such as city1-3 and city2-3). |
| Revised text / 改写文本 | For each integer i from 1 through 3, the locations cityi-1, cityi-2, and cityi-3 are formed by concatenating city, i, and respectively -1, -2, and -3; all three locations are in cityi, and cityi-3 is an airport. |
| Reason | Examples did not enumerate or deterministically construct all nine locations, three airports, and nine in-city facts.<br>示例不能枚举或确定性构造全部九个地点、三个机场以及九个地点-城市关系。 |
| Golden PDDL evidence | golden_problem.pddl:lines 8-9: nine location objects \| golden_problem.pddl:lines 49-69: location, airport, and in-city atoms |

### Change 2 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Initially, the airplanes are positioned as follows: plane6 is at city2-3, plane5 and plane1 are both stationed at city1-3, and planes 4, 3, and 2 are at city3-3 or city2-3. |
| Revised text / 改写文本 | Initially, the airplanes are positioned as follows: plane6 is at city2-3, plane5 and plane1 are both stationed at city1-3, plane4 is at city3-3, and plane3 and plane2 are at city2-3. |
| Reason | The disjunction left the initial locations of Plane 4, Plane 3, and Plane 2 unresolved.<br>析取表达使飞机 4、飞机 3 和飞机 2 的初始位置无法确定。 |
| Golden PDDL evidence | golden_problem.pddl:lines 70-75: all six airplane initial locations |

### Change 3 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | Regarding trucks: truck22 is at city3-2, trucks like truck21 and truck16 are at various city2 locations, whereas trucks 20, 18, and 13 are spread across city1 locations, and several others are in use around city3. |
| Revised text / 改写文本 | Regarding trucks: truck22 and truck4 are at city3-2; truck21 and truck16 are at city2-1; truck20, truck18, and truck13 are at city1-2; truck19, truck15, truck9, truck7, truck6, truck5, and truck1 are at city2-3; truck17, truck14, truck12, and truck3 are at city2-2; truck11 and truck8 are at city3-3; truck10 is at city3-1; and truck2 is at city1-1. |
| Reason | Vague examples and regional descriptions did not uniquely support 21 of the 22 irregular truck locations.<br>模糊示例和区域性描述无法唯一支持 22 个不规则卡车位置中的 21 个。 |
| Golden PDDL evidence | golden_problem.pddl:lines 76-97: all 22 truck initial locations |

### Change 4 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | Packages are spread across the cities too: for example, package8 is at city1-2, package7 is at city2-1, package6 is at city3-2, and package5 and package1 both start at city1-3. |
| Revised text / 改写文本 | Packages are spread across the cities too: package8 is at city1-2; package7 is at city2-1; package6 and package2 are at city3-2; package5 and package1 are at city1-3; package4 is at city3-3; and package3 is at city2-2. |
| Reason | The example-only sentence omitted the initial locations of Package 4, Package 3, and Package 2.<br>仅含示例的句子遗漏了包裹 4、包裹 3 和包裹 2 的初始位置。 |
| Golden PDDL evidence | golden_problem.pddl:lines 98-105: all eight package initial locations |


## p89 - 3 changes / 3 个改写点

Objects 206 · Init 412 · Goal 8 · Semantic items 626

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city has specific locations, including some designated as airports. |
| Revised text / 改写文本 | For each city index X from 1 to 29 and location index Y from 1 to 4, cityX-Y is a location in cityX, and cityX-4 is an airport. |
| Reason | Defines the complete 29-by-4 location family, city correspondence, and airport suffix.<br>定义完整的 29×4 地点族、城市对应关系和机场后缀。 |
| Golden PDDL evidence | golden_problem.pddl:lines 14-31: all location objects \| golden_problem.pddl:lines 122-382: location, airport, and in-city atoms |

### Change 2 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | Currently, the planes and trucks are parked at specific city locations, and packages are scattered across different places. For example, package 23 is currently located at city 26, location 2, while package 22 is at city 1, location 1. |
| Revised text / 改写文本 | Currently, the planes are parked as follows: plane9 is at city28-4; plane8 is at city23-4; plane7 is at city27-4; plane6 is at city29-4; plane5 is at city13-4; plane4 is at city4-4; plane3 is at city14-4; plane2 is at city14-4; plane1 is at city13-4. The trucks are parked as follows: truck29 is at city29-1; truck28 is at city28-2; truck27 is at city27-3; truck26 is at city26-1; truck25 is at city25-2; truck24 is at city24-3; truck23 is at city23-3; truck22 is at city22-3; truck21 is at city21-1; truck20 is at city20-1; truck19 is at city19-3; truck18 is at city18-2; truck17 is at city17-3; truck16 is at city16-2; truck15 is at city15-3; truck14 is at city14-3; truck13 is at city13-2; truck12 is at city12-3; truck11 is at city11-1; truck10 is at city10-2; truck9 is at city9-3; truck8 is at city8-2; truck7 is at city7-3; truck6 is at city6-3; truck5 is at city5-3; truck4 is at city4-2; truck3 is at city3-2; truck2 is at city2-3; truck1 is at city1-1. The packages are located as follows: package23 is at city26-2; package22 is at city1-1; package21 is at city3-1; package20 is at city18-2; package19 is at city17-2; package18 is at city21-1; package17 is at city1-4; package16 is at city29-4; package15 is at city1-2; package14 is at city4-4; package13 is at city10-1; package12 is at city13-1; package11 is at city24-3; package10 is at city5-4; package9 is at city9-4; package8 is at city3-4; package7 is at city13-1; package6 is at city7-3; package5 is at city16-1; package4 is at city3-2; package3 is at city17-1; package2 is at city11-1; package1 is at city21-4. |
| Reason | Replaces two package examples and unspecified vehicle placements with every irregular airplane, truck, and package initial location.<br>用全部不规则的飞机、卡车和包裹初始位置替换两个包裹示例和未指定的车辆位置。 |
| Golden PDDL evidence | golden_problem.pddl:lines 383-443: all 61 initial (AT ...) atoms |

### Change 3 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | Your task is to efficiently coordinate the movement of vehicles and packages to achieve this desired outcome. |
| Revised text / 改写文本 | All eight listed package destinations must hold simultaneously. |
| Reason | Removes the unsupported efficiency objective and explicitly states the eight-way goal conjunction.<br>删除未受支持的效率目标，并明确八个目标同时成立。 |
| Golden PDDL evidence | golden_problem.pddl:lines 444-451: conjunctive eight-atom goal |


## p91 - 4 changes / 4 个改写点

Objects 56 · Init 112 · Goal 14 · Semantic items 182

### Change 1 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | Specifically, package23 through package1 are scattered across distinct locations. |
| Revised text / 改写文本 | Specifically, the initial package locations are: package23 is at city1-5; package22 is at city1-5; package21 is at city2-4; package20 is at city2-3; package19 is at city1-2; package18 is at city3-3; package17 is at city2-3; package16 is at city3-5; package15 is at city2-2; package14 is at city2-1; package13 is at city3-4; package12 is at city1-6; package11 is at city1-4; package10 is at city3-3; package9 is at city3-3; package8 is at city1-2; package7 is at city1-4; package6 is at city1-4; package5 is at city3-1; package4 is at city2-1; package3 is at city1-5; package2 is at city3-3; package1 is at city1-2. |
| Reason | Replaces the false claim that all packages occupy distinct locations with the complete irregular initial package mapping.<br>用完整的不规则包裹初始映射替换所有包裹位于不同地点的错误说法。 |
| Golden PDDL evidence | golden_problem.pddl:lines 101-123: all package (AT ...) atoms |

### Change 2 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | We have three major city hubs: city1, city2, and city3, each with various locations and airports within them. |
| Revised text / 改写文本 | We have three major city hubs: city1, city2, and city3; for each city index X from 1 to 3 and location index Y from 1 to 6, cityX-Y is a location in cityX, and cityX-6 is an airport. |
| Reason | Defines all 18 location identifiers, their cities, and the -6 airport suffix.<br>定义全部 18 个地点标识符、所属城市和 -6 机场后缀。 |
| Golden PDDL evidence | golden_problem.pddl:lines 8-11: location objects \| golden_problem.pddl:lines 50-88: location, airport, and in-city atoms |

### Change 3 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | Each vehicle is stationed at specific locations within these cities. |
| Revised text / 改写文本 | The airplanes are stationed as follows: plane7 is at city1-6; plane6 is at city2-6; plane5 is at city1-6; plane4 is at city1-6; plane3 is at city3-6; plane2 is at city1-6; plane1 is at city2-6. The trucks are stationed as follows: truck5 is at city3-4; truck4 is at city2-3; truck3 is at city1-5; truck2 is at city1-3; truck1 is at city1-6. |
| Reason | Expands unspecified vehicle positions into all seven airplane and five truck locations.<br>将未指定的车辆位置展开为七架飞机和五辆卡车的全部位置。 |
| Golden PDDL evidence | golden_problem.pddl:lines 89-100: vehicle (AT ...) atoms |

### Change 4 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | For example, package23 needs to be transported to city2-3, while package22 should remain at city1-5. Other packages need to be carefully placed according to the requirements, such as transferring package21 to city1-6 and package20 to city1-1. Our end goal is to ensure all specified packages are accurately positioned at their respective target locations, thus completing the logistics challenge. |
| Revised text / 改写文本 | The required package destinations are: package23 must be at city2-3; package22 must be at city1-5; package21 must be at city1-6; package20 must be at city1-1; package19 must be at city1-3; package18 must be at city1-3; package17 must be at city1-5; package16 must be at city1-1; package15 must be at city3-3; package14 must be at city1-5; package13 must be at city2-5; package12 must be at city3-2; package11 must be at city2-6; package10 must be at city1-6. All 14 listed package destinations must hold simultaneously. |
| Reason | Replaces four examples and vague remaining requirements with the complete irregular 14-atom goal, excluding nine packages with no golden goal.<br>用完整的不规则 14 原子目标替换四个示例和模糊剩余要求，并排除没有黄金目标的九个包裹。 |
| Golden PDDL evidence | golden_problem.pddl:lines 124-137: conjunctive 14-atom goal |


## p92 - 4 changes / 4 个改写点

Objects 116 · Init 232 · Goal 7 · Semantic items 355

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city contains multiple locations, including airports. |
| Revised text / 改写文本 | For each city index X from 1 to 11 and location index Y from 1 to 3, cityX-Y is a location in cityX, and cityX-3 is an airport. |
| Reason | Defines the complete 11-by-3 location family, city correspondence, and airport suffix.<br>定义完整的 11×3 地点族、城市对应关系和机场后缀。 |
| Golden PDDL evidence | golden_problem.pddl:lines 14-18: location objects \| golden_problem.pddl:lines 102-178: location, airport, and in-city atoms |

### Change 2 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | The trucks and planes are stationed at specific locations within these cities at the start of the game. For example, plane1 is at airport city6-3, and truck1 is at city5-2. |
| Revised text / 改写文本 | Initially, the airplanes are stationed as follows: plane13 is at city10-3; plane12 is at city5-3; plane11 is at city11-3; plane10 is at city1-3; plane9 is at city9-3; plane8 is at city7-3; plane7 is at city1-3; plane6 is at city8-3; plane5 is at city7-3; plane4 is at city9-3; plane3 is at city1-3; plane2 is at city11-3; plane1 is at city6-3. The trucks are stationed as follows: truck52 is at city11-2; truck51 is at city10-1; truck50 is at city9-2; truck49 is at city8-1; truck48 is at city7-1; truck47 is at city6-1; truck46 is at city5-2; truck45 is at city4-1; truck44 is at city3-2; truck43 is at city2-2; truck42 is at city1-2; truck41 is at city7-2; truck40 is at city6-1; truck39 is at city2-3; truck38 is at city3-1; truck37 is at city2-3; truck36 is at city7-1; truck35 is at city8-2; truck34 is at city8-2; truck33 is at city7-2; truck32 is at city6-3; truck31 is at city2-2; truck30 is at city11-3; truck29 is at city1-2; truck28 is at city3-1; truck27 is at city9-2; truck26 is at city7-2; truck25 is at city1-3; truck24 is at city4-1; truck23 is at city9-2; truck22 is at city3-1; truck21 is at city1-1; truck20 is at city7-3; truck19 is at city4-3; truck18 is at city1-1; truck17 is at city4-3; truck16 is at city11-3; truck15 is at city6-2; truck14 is at city5-3; truck13 is at city5-1; truck12 is at city8-1; truck11 is at city8-1; truck10 is at city5-2; truck9 is at city8-3; truck8 is at city1-1; truck7 is at city8-2; truck6 is at city9-3; truck5 is at city10-2; truck4 is at city6-3; truck3 is at city11-1; truck2 is at city5-3; truck1 is at city5-2. |
| Reason | Replaces one plane and one truck example with all 13 airplane and 52 truck initial locations.<br>用全部 13 架飞机和 52 辆卡车的初始位置替换一个飞机和一个卡车示例。 |
| Golden PDDL evidence | golden_problem.pddl:lines 179-243: vehicle (AT ...) atoms |

### Change 3 - irregular_mapping / 补全不规则映射

| Field | Full content |
|---|---|
| Original text / 原文 | The packages are spread out in various locations as well; for instance, package1, package2, and package3 are all at city7-2, while package7 starts at city4-2. |
| Revised text / 改写文本 | The initial package locations are: package7 is at city4-2; package6 is at city4-1; package5 is at city11-2; package4 is at city2-2; package3 is at city7-2; package2 is at city7-2; package1 is at city7-2. |
| Reason | Replaces four package examples with the complete seven-package initial mapping.<br>用完整的七包裹初始映射替换四个包裹示例。 |
| Golden PDDL evidence | golden_problem.pddl:lines 244-250: package (AT ...) atoms |

### Change 4 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | By using the available trucks and airplanes strategically, each package must reach its destination safely and efficiently. |
| Revised text / 改写文本 | All seven listed package destinations must hold simultaneously. |
| Reason | Removes unsupported safety and efficiency objectives and makes the seven-way goal conjunction explicit.<br>删除未受支持的安全和效率目标，并明确七个目标同时成立。 |
| Golden PDDL evidence | golden_problem.pddl:lines 251-257: conjunctive seven-atom goal |


## p96 - 1 changes / 1 个改写点

Objects 49 · Init 98 · Goal 5 · Semantic items 152

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city has its corresponding trucks located at the general area. |
| Revised text / 改写文本 | For each integer i from 1 through 10, trucki is initially located at the general area of cityi, where each occurrence of i is replaced by the same integer. |
| Reason | The undefined word 'corresponding' did not uniquely pair the ten trucks with the ten cities' general locations.<br>未定义的“对应”一词没有唯一地将十辆卡车与十座城市的普通地点配对。 |
| Golden PDDL evidence | golden_problem.pddl:lines 25-34: (TRUCK TRUCK10) through (TRUCK TRUCK1) \| golden_problem.pddl:lines 93-102: (AT TRUCKi CITYi-1) for i=10..1 |


## p97 - 1 changes / 1 个改写点

Objects 26 · Init 52 · Goal 7 · Semantic items 85

### Change 1 - missing_rule / 补充缺失规则

| Field | Full content |
|---|---|
| Original text / 原文 | Each city has distinct locations, with city1 having locations city1-1 and city1-2, city2 having city2-1 and city2-2, and city3 containing city3-1 and city3-2. |
| Revised text / 改写文本 | Each city has distinct locations, with city1 having locations city1-1 and city1-2, city2 having city2-1 and city2-2, and city3 containing city3-1 and city3-2; city1-2, city2-2, and city3-2 are the airports. |
| Reason | Adds only the two missing airport classifications while retaining the complete city/location enumeration.<br>仅补充两个缺失的机场分类，并保留完整的城市/地点枚举。 |
| Golden PDDL evidence | golden_problem.pddl:line 30: (AIRPORT CITY3-2) \| golden_problem.pddl:line 32: (AIRPORT CITY2-2) \| golden_problem.pddl:line 34: (AIRPORT CITY1-2) |


## p98 - 2 changes / 2 个改写点

Objects 42 · Init 84 · Goal 6 · Semantic items 132

### Change 1 - ambiguity / 消除歧义

| Field | Full content |
|---|---|
| Original text / 原文 | Each city contains specific locations that may serve as destinations for the packages: locations such as cityX-1, cityX-2 for standard locations, and cityX-3 for airports, where 'X' corresponds to the city number. |
| Revised text / 改写文本 | Each city contains specific locations that may serve as destinations for the packages: locations cityX-1 and cityX-2, and the airport cityX-3, where 'X' corresponds to the city number. |
| Reason | Removes the open-ended “such as” wording and states the exact three-location suffix schema.<br>删除开放式的“例如”措辞，并明确精确的三地点后缀模式。 |
| Golden PDDL evidence | golden_problem.pddl:lines 6-8: exact location objects \| golden_problem.pddl:lines 36-70: location, airport, and in-city atoms |

### Change 2 - contradiction / 修正矛盾

| Field | Full content |
|---|---|
| Original text / 原文 | Our task is to use the available vehicles to achieve these delivery goals efficiently. |
| Revised text / 改写文本 | All six listed package destinations must hold simultaneously. |
| Reason | Removes the unsupported efficiency objective and explicitly states the six-way goal conjunction.<br>删除未受支持的效率目标，并明确六个目标同时成立。 |
| Golden PDDL evidence | golden_problem.pddl:lines 93-98: conjunctive six-atom goal |

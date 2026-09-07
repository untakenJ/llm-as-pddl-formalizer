# Natural Logistics Minimal Rewrite Audit

## Main finding

All 100 Natural Logistics problems were audited independently against their golden PDDL problem and domain files. 49 descriptions required a minimal evidence-completeness repair, while 51 descriptions were preserved verbatim because no rewrite was necessary. The final descriptions cover all 19,718 audited semantic items: 5,940 objects, 11,880 init atoms, and 1,898 goal atoms.

全部 100 道 Natural Logistics 题目均已分别对照 golden PDDL problem 和 domain 完成审计。其中 49 道需要进行最小化的证据完整性修复，51 道因无需改写而逐字保留原文。最终描述覆盖全部 19,718 个语义项目，包括 5,940 个对象、11,880 个 init 原子和 1,898 个 goal 原子。

## Audit status

| Measure | Result |
|---|---:|
| Problems audited | 100 / 100 |
| Rewrites required | 49 |
| Preserved verbatim | 51 |
| Semantic items verified | 19,718 / 19,718 |
| Final missing items | 0 |
| Final ambiguous items | 0 |
| Final contradictory items | 0 |
| Final over-generated items | 0 |

Before repair, agents recorded defects separately as missing, ambiguous, contradictory, or over-generated evidence. These diagnostic categories are not necessarily mutually exclusive at the sentence level and should not be added together as a count of unique PDDL atoms without consulting the per-case ledgers.

改写前的问题分别记录为缺失、歧义、矛盾或额外生成。由于同一文本片段可能同时触发多个诊断类别，在不查看逐题证据账本的情况下，不应将这些诊断数简单相加并解释为唯一 PDDL 原子数。

| Before-rewrite diagnostic | Count |
|---|---:|
| Missing | 970 |
| Ambiguous | 2,021 |
| Contradictory | 48 |
| Over-generated | 1,300 |

## Method

Each case was handled in a bounded independent agent context. The agent parsed every object, init atom, and goal atom; first decided whether rewriting was necessary; applied only necessary edits; and then produced a one-row-per-item evidence ledger for the complete final description. Deterministic rules were expanded during verification. A rule was accepted only when its bounds, identifier construction, index correspondence, and exceptions were unique and it generated exactly the golden items.

每道题均在受限的独立 agent 上下文中处理。Agent 解析全部对象、init 原子和 goal 原子，先判断是否确有改写必要，只实施必要修改，然后为完整的最终描述生成逐项目证据账本。验证阶段会实际展开确定性规则；只有范围、标识符构造、索引对应及例外均唯一，并且恰好生成 golden 项目时，规则才会被接受。

## Per-problem review table

| Case | Decision | Objects | Init | Goal | Before coverage (O/I/G) | Missing | Ambig. | Contra. | Over-gen. | Changes | Categories | Notes |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|---|
| p01 | Preserved | 15 | 30 | 4 | 15/15 · 30/30 · 4/4 | 0 | 0 | 0 | 0 | 0 | — | [p01 notes](p01/rewrite_notes.md) |
| p02 | Preserved | 15 | 30 | 6 | 15/15 · 30/30 · 6/6 | 0 | 0 | 0 | 0 | 0 | — | [p02 notes](p02/rewrite_notes.md) |
| p03 | Preserved | 22 | 44 | 7 | 22/22 · 44/44 · 7/7 | 0 | 0 | 0 | 0 | 0 | — | [p03 notes](p03/rewrite_notes.md) |
| p04 | Preserved | 22 | 44 | 7 | 22/22 · 44/44 · 7/7 | 0 | 0 | 0 | 0 | 0 | — | [p04 notes](p04/rewrite_notes.md) |
| p05 | Preserved | 22 | 44 | 8 | 22/22 · 44/44 · 8/8 | 0 | 0 | 0 | 0 | 0 | — | [p05 notes](p05/rewrite_notes.md) |
| p06 | Rewrite | 22 | 44 | 8 | 22/22 · 44/44 · 8/8 | 0 | 1 | 1 | 14 | 2 | ambiguity; contradiction | [p06 notes](p06/rewrite_notes.md) |
| p07 | Preserved | 22 | 44 | 9 | 22/22 · 44/44 · 9/9 | 0 | 0 | 0 | 0 | 0 | — | [p07 notes](p07/rewrite_notes.md) |
| p08 | Preserved | 22 | 44 | 9 | 22/22 · 44/44 · 9/9 | 0 | 0 | 0 | 0 | 0 | — | [p08 notes](p08/rewrite_notes.md) |
| p09 | Rewrite | 29 | 58 | 10 | 29/29 · 58/58 · 10/10 | 0 | 0 | 1 | 42 | 1 | contradiction | [p09 notes](p09/rewrite_notes.md) |
| p10 | Rewrite | 29 | 58 | 10 | 29/29 · 57/58 · 10/10 | 1 | 0 | 0 | 0 | 1 | missing_rule | [p10 notes](p10/rewrite_notes.md) |
| p11 | Rewrite | 29 | 58 | 11 | 29/29 · 51/58 · 11/11 | 0 | 7 | 0 | 0 | 1 | missing_rule | [p11 notes](p11/rewrite_notes.md) |
| p12 | Rewrite | 15 | 30 | 4 | 15/15 · 27/30 · 4/4 | 1 | 2 | 0 | 3 | 2 | ambiguity; missing_rule | [p12 notes](p12/rewrite_notes.md) |
| p13 | Preserved | 29 | 58 | 11 | 29/29 · 58/58 · 11/11 | 0 | 0 | 0 | 0 | 0 | — | [p13 notes](p13/rewrite_notes.md) |
| p14 | Preserved | 29 | 58 | 12 | 29/29 · 58/58 · 12/12 | 0 | 0 | 0 | 0 | 0 | — | [p14 notes](p14/rewrite_notes.md) |
| p15 | Preserved | 29 | 58 | 12 | 29/29 · 58/58 · 12/12 | 0 | 0 | 0 | 0 | 0 | — | [p15 notes](p15/rewrite_notes.md) |
| p16 | Rewrite | 37 | 74 | 13 | 37/37 · 61/74 · 13/13 | 0 | 10 | 3 | 3 | 2 | ambiguity; contradiction | [p16 notes](p16/rewrite_notes.md) |
| p17 | Preserved | 37 | 74 | 13 | 37/37 · 74/74 · 13/13 | 0 | 0 | 0 | 0 | 0 | — | [p17 notes](p17/rewrite_notes.md) |
| p18 | Rewrite | 37 | 74 | 14 | 37/37 · 71/74 · 14/14 | 0 | 4 | 1 | 4 | 3 | ambiguity; contradiction | [p18 notes](p18/rewrite_notes.md) |
| p19 | Rewrite | 37 | 74 | 14 | 37/37 · 70/74 · 14/14 | 4 | 0 | 0 | 0 | 1 | missing_rule | [p19 notes](p19/rewrite_notes.md) |
| p20 | Preserved | 37 | 74 | 15 | 37/37 · 74/74 · 15/15 | 0 | 0 | 0 | 0 | 0 | — | [p20 notes](p20/rewrite_notes.md) |
| p21 | Preserved | 37 | 74 | 15 | 37/37 · 74/74 · 15/15 | 0 | 0 | 0 | 0 | 0 | — | [p21 notes](p21/rewrite_notes.md) |
| p22 | Rewrite | 32 | 64 | 6 | 28/32 · 32/64 · 6/6 | 6 | 30 | 1 | 0 | 3 | ambiguity; contradiction; missing_rule | [p22 notes](p22/rewrite_notes.md) |
| p23 | Preserved | 15 | 30 | 4 | 15/15 · 30/30 · 4/4 | 0 | 0 | 0 | 0 | 0 | — | [p23 notes](p23/rewrite_notes.md) |
| p24 | Preserved | 49 | 98 | 5 | 49/49 · 98/98 · 5/5 | 0 | 0 | 0 | 0 | 0 | — | [p24 notes](p24/rewrite_notes.md) |
| p25 | Rewrite | 83 | 166 | 7 | 83/83 · 160/166 · 7/7 | 1 | 0 | 5 | 5 | 2 | contradiction; missing_rule | [p25 notes](p25/rewrite_notes.md) |
| p26 | Rewrite | 100 | 200 | 7 | 48/100 · 48/200 · 0/7 | 0 | 211 | 1 | 0 | 4 | ambiguity; irregular_mapping; missing_rule | [p26 notes](p26/rewrite_notes.md) |
| p27 | Rewrite | 44 | 88 | 16 | 44/44 · 84/88 · 16/16 | 4 | 0 | 1 | 35 | 2 | contradiction; missing_rule | [p27 notes](p27/rewrite_notes.md) |
| p28 | Rewrite | 44 | 88 | 16 | 44/44 · 82/88 · 16/16 | 0 | 7 | 0 | 35 | 2 | ambiguity | [p28 notes](p28/rewrite_notes.md) |
| p29 | Preserved | 44 | 88 | 17 | 44/44 · 88/88 · 17/17 | 0 | 0 | 0 | 0 | 0 | — | [p29 notes](p29/rewrite_notes.md) |
| p30 | Preserved | 44 | 88 | 17 | 44/44 · 88/88 · 17/17 | 0 | 0 | 0 | 0 | 0 | — | [p30 notes](p30/rewrite_notes.md) |
| p31 | Rewrite | 44 | 88 | 18 | 44/44 · 88/88 · 18/18 | 0 | 1 | 0 | 35 | 1 | ambiguity | [p31 notes](p31/rewrite_notes.md) |
| p32 | Preserved | 44 | 88 | 18 | 44/44 · 88/88 · 18/18 | 0 | 0 | 0 | 0 | 0 | — | [p32 notes](p32/rewrite_notes.md) |
| p33 | Rewrite | 51 | 102 | 19 | 51/51 · 102/102 · 19/19 | 0 | 1 | 1 | 42 | 1 | contradiction | [p33 notes](p33/rewrite_notes.md) |
| p34 | Preserved | 15 | 30 | 5 | 15/15 · 30/30 · 5/5 | 0 | 0 | 0 | 0 | 0 | — | [p34 notes](p34/rewrite_notes.md) |
| p35 | Rewrite | 51 | 102 | 19 | 51/51 · 102/102 · 19/19 | 0 | 0 | 1 | 0 | 1 | contradiction | [p35 notes](p35/rewrite_notes.md) |
| p36 | Preserved | 51 | 102 | 20 | 51/51 · 102/102 · 20/20 | 0 | 0 | 0 | 0 | 0 | — | [p36 notes](p36/rewrite_notes.md) |
| p37 | Rewrite | 51 | 102 | 20 | 51/51 · 95/102 · 20/20 | 0 | 7 | 0 | 0 | 1 | ambiguity | [p37 notes](p37/rewrite_notes.md) |
| p38 | Rewrite | 51 | 102 | 21 | 43/51 · 70/102 · 21/21 | 0 | 40 | 0 | 0 | 3 | missing_rule | [p38 notes](p38/rewrite_notes.md) |
| p39 | Rewrite | 51 | 102 | 21 | 38/51 · 46/102 · 6/21 | 22 | 55 | 1 | 42 | 5 | ambiguity; contradiction; irregular_mapping; missing_rule | [p39 notes](p39/rewrite_notes.md) |
| p40 | Preserved | 58 | 116 | 22 | 58/58 · 116/116 · 22/22 | 0 | 0 | 0 | 0 | 0 | — | [p40 notes](p40/rewrite_notes.md) |
| p41 | Preserved | 58 | 116 | 22 | 58/58 · 116/116 · 22/22 | 0 | 0 | 0 | 0 | 0 | — | [p41 notes](p41/rewrite_notes.md) |
| p42 | Rewrite | 58 | 116 | 23 | 43/58 · 69/116 · 23/23 | 1 | 61 | 0 | 2 | 4 | ambiguity; contradiction; missing_rule | [p42 notes](p42/rewrite_notes.md) |
| p43 | Rewrite | 58 | 116 | 23 | 58/58 · 100/116 · 23/23 | 0 | 16 | 0 | 0 | 2 | ambiguity | [p43 notes](p43/rewrite_notes.md) |
| p44 | Preserved | 58 | 116 | 24 | 58/58 · 116/116 · 24/24 | 0 | 0 | 0 | 0 | 0 | — | [p44 notes](p44/rewrite_notes.md) |
| p45 | Preserved | 15 | 30 | 5 | 15/15 · 30/30 · 5/5 | 0 | 0 | 0 | 0 | 0 | — | [p45 notes](p45/rewrite_notes.md) |
| p46 | Preserved | 58 | 116 | 24 | 58/58 · 116/116 · 24/24 | 0 | 0 | 0 | 0 | 0 | — | [p46 notes](p46/rewrite_notes.md) |
| p47 | Rewrite | 66 | 132 | 25 | 66/66 · 123/132 · 25/25 | 0 | 9 | 2 | 0 | 2 | contradiction | [p47 notes](p47/rewrite_notes.md) |
| p48 | Rewrite | 66 | 132 | 25 | 57/66 · 79/132 · 25/25 | 18 | 44 | 0 | 0 | 1 | missing_rule | [p48 notes](p48/rewrite_notes.md) |
| p49 | Preserved | 66 | 132 | 26 | 66/66 · 132/132 · 26/26 | 0 | 0 | 0 | 0 | 0 | — | [p49 notes](p49/rewrite_notes.md) |
| p50 | Preserved | 66 | 132 | 26 | 66/66 · 132/132 · 26/26 | 0 | 0 | 0 | 0 | 0 | — | [p50 notes](p50/rewrite_notes.md) |
| p51 | Rewrite | 66 | 132 | 27 | 60/66 · 90/132 · 27/27 | 0 | 48 | 0 | 115 | 3 | ambiguity; missing_rule | [p51 notes](p51/rewrite_notes.md) |
| p52 | Preserved | 66 | 132 | 27 | 66/66 · 132/132 · 27/27 | 0 | 0 | 0 | 0 | 0 | — | [p52 notes](p52/rewrite_notes.md) |
| p53 | Rewrite | 73 | 146 | 28 | 71/73 · 102/146 · 28/28 | 0 | 46 | 0 | 63 | 3 | ambiguity; missing_rule | [p53 notes](p53/rewrite_notes.md) |
| p54 | Rewrite | 73 | 146 | 28 | 71/73 · 77/146 · 28/28 | 7 | 64 | 0 | 63 | 4 | ambiguity; missing_rule | [p54 notes](p54/rewrite_notes.md) |
| p55 | Preserved | 73 | 146 | 29 | 73/73 · 146/146 · 29/29 | 0 | 0 | 0 | 0 | 0 | — | [p55 notes](p55/rewrite_notes.md) |
| p56 | Preserved | 15 | 30 | 5 | 15/15 · 30/30 · 5/5 | 0 | 0 | 0 | 0 | 0 | — | [p56 notes](p56/rewrite_notes.md) |
| p57 | Rewrite | 73 | 146 | 29 | 72/73 · 98/146 · 6/29 | 23 | 49 | 2 | 63 | 6 | ambiguity; contradiction; irregular_mapping; missing_rule | [p57 notes](p57/rewrite_notes.md) |
| p58 | Rewrite | 73 | 146 | 30 | 52/73 · 80/146 · 7/30 | 23 | 87 | 0 | 63 | 5 | ambiguity; irregular_mapping; missing_rule | [p58 notes](p58/rewrite_notes.md) |
| p59 | Preserved | 73 | 146 | 30 | 73/73 · 146/146 · 30/30 | 0 | 0 | 0 | 0 | 0 | — | [p59 notes](p59/rewrite_notes.md) |
| p60 | Preserved | 80 | 160 | 31 | 80/80 · 160/160 · 31/31 | 0 | 0 | 0 | 0 | 0 | — | [p60 notes](p60/rewrite_notes.md) |
| p61 | Rewrite | 80 | 160 | 31 | 80/80 · 160/160 · 31/31 | 0 | 0 | 0 | 70 | 1 | ambiguity | [p61 notes](p61/rewrite_notes.md) |
| p62 | Preserved | 80 | 160 | 32 | 80/80 · 160/160 · 32/32 | 0 | 0 | 0 | 0 | 0 | — | [p62 notes](p62/rewrite_notes.md) |
| p63 | Preserved | 80 | 160 | 32 | 80/80 · 160/160 · 32/32 | 0 | 0 | 0 | 0 | 0 | — | [p63 notes](p63/rewrite_notes.md) |
| p64 | Rewrite | 80 | 160 | 33 | 80/80 · 106/160 · 33/33 | 0 | 51 | 7 | 73 | 7 | ambiguity; contradiction; missing_rule | [p64 notes](p64/rewrite_notes.md) |
| p65 | Preserved | 80 | 160 | 33 | 80/80 · 160/160 · 33/33 | 0 | 0 | 0 | 0 | 0 | — | [p65 notes](p65/rewrite_notes.md) |
| p66 | Rewrite | 87 | 174 | 34 | 87/87 · 126/174 · 34/34 | 0 | 48 | 0 | 0 | 1 | ambiguity | [p66 notes](p66/rewrite_notes.md) |
| p67 | Preserved | 15 | 30 | 6 | 15/15 · 30/30 · 6/6 | 0 | 0 | 0 | 0 | 0 | — | [p67 notes](p67/rewrite_notes.md) |
| p68 | Rewrite | 87 | 174 | 34 | 62/87 · 89/174 · 7/34 | 27 | 110 | 0 | 78 | 6 | ambiguity; contradiction; irregular_mapping; missing_rule | [p68 notes](p68/rewrite_notes.md) |
| p69 | Rewrite | 87 | 174 | 35 | 47/87 · 63/174 · 5/35 | 54 | 127 | 0 | 78 | 7 | ambiguity; irregular_mapping; missing_rule | [p69 notes](p69/rewrite_notes.md) |
| p70 | Rewrite | 87 | 174 | 35 | 75/87 · 92/174 · 35/35 | 22 | 72 | 0 | 78 | 4 | ambiguity; contradiction; missing_rule | [p70 notes](p70/rewrite_notes.md) |
| p71 | Preserved | 87 | 174 | 36 | 87/87 · 174/174 · 36/36 | 0 | 0 | 0 | 0 | 0 | — | [p71 notes](p71/rewrite_notes.md) |
| p72 | Preserved | 87 | 174 | 36 | 87/87 · 174/174 · 36/36 | 0 | 0 | 0 | 0 | 0 | — | [p72 notes](p72/rewrite_notes.md) |
| p73 | Rewrite | 95 | 190 | 37 | 92/95 · 106/190 · 37/37 | 9 | 78 | 0 | 84 | 3 | ambiguity; missing_rule | [p73 notes](p73/rewrite_notes.md) |
| p74 | Preserved | 95 | 190 | 37 | 95/95 · 190/190 · 37/37 | 0 | 0 | 0 | 0 | 0 | — | [p74 notes](p74/rewrite_notes.md) |
| p75 | Rewrite | 95 | 190 | 38 | 91/95 · 105/190 · 38/38 | 0 | 89 | 0 | 84 | 3 | ambiguity; missing_rule | [p75 notes](p75/rewrite_notes.md) |
| p76 | Rewrite | 95 | 190 | 38 | 95/95 · 124/190 · 38/38 | 0 | 66 | 0 | 0 | 2 | missing_rule | [p76 notes](p76/rewrite_notes.md) |
| p77 | Rewrite | 95 | 190 | 39 | 75/95 · 96/190 · 3/39 | 36 | 114 | 0 | 14 | 3 | irregular_mapping; missing_rule | [p77 notes](p77/rewrite_notes.md) |
| p78 | Rewrite | 15 | 30 | 6 | 15/15 · 24/30 · 6/6 | 0 | 3 | 3 | 3 | 2 | ambiguity; contradiction | [p78 notes](p78/rewrite_notes.md) |
| p79 | Preserved | 95 | 190 | 39 | 95/95 · 190/190 · 39/39 | 0 | 0 | 0 | 0 | 0 | — | [p79 notes](p79/rewrite_notes.md) |
| p80 | Preserved | 102 | 204 | 40 | 102/102 · 204/204 · 40/40 | 0 | 0 | 0 | 0 | 0 | — | [p80 notes](p80/rewrite_notes.md) |
| p81 | Rewrite | 102 | 204 | 40 | 45/102 · 52/204 · 5/40 | 37 | 207 | 0 | 94 | 11 | ambiguity; contradiction; irregular_mapping; missing_rule | [p81 notes](p81/rewrite_notes.md) |
| p82 | Rewrite | 102 | 204 | 41 | 45/102 · 80/204 · 7/41 | 34 | 181 | 0 | 1 | 5 | ambiguity; contradiction; irregular_mapping | [p82 notes](p82/rewrite_notes.md) |
| p83 | Preserved | 102 | 204 | 41 | 102/102 · 204/204 · 41/41 | 0 | 0 | 0 | 0 | 0 | — | [p83 notes](p83/rewrite_notes.md) |
| p84 | Preserved | 15 | 30 | 6 | 15/15 · 30/30 · 6/6 | 0 | 0 | 0 | 0 | 0 | — | [p84 notes](p84/rewrite_notes.md) |
| p85 | Rewrite | 32 | 64 | 6 | 30/32 · 54/64 · 6/6 | 6 | 6 | 0 | 0 | 2 | ambiguity; missing_rule | [p85 notes](p85/rewrite_notes.md) |
| p86 | Preserved | 113 | 226 | 17 | 113/113 · 226/226 · 17/17 | 0 | 0 | 0 | 0 | 0 | — | [p86 notes](p86/rewrite_notes.md) |
| p87 | Rewrite | 48 | 96 | 8 | 46/48 · 57/96 · 8/8 | 24 | 17 | 0 | 0 | 4 | ambiguity; irregular_mapping; missing_rule | [p87 notes](p87/rewrite_notes.md) |
| p88 | Preserved | 204 | 408 | 5 | 204/204 · 408/408 · 5/5 | 0 | 0 | 0 | 0 | 0 | — | [p88 notes](p88/rewrite_notes.md) |
| p89 | Rewrite | 206 | 412 | 8 | 100/206 · 104/412 · 8/8 | 385 | 29 | 0 | 1 | 3 | contradiction; irregular_mapping; missing_rule | [p89 notes](p89/rewrite_notes.md) |
| p90 | Preserved | 117 | 234 | 19 | 117/117 · 234/234 · 19/19 | 0 | 0 | 0 | 0 | 0 | — | [p90 notes](p90/rewrite_notes.md) |
| p91 | Rewrite | 56 | 112 | 14 | 42/56 · 42/112 · 4/14 | 74 | 3 | 17 | 9 | 4 | contradiction; irregular_mapping; missing_rule | [p91 notes](p91/rewrite_notes.md) |
| p92 | Rewrite | 116 | 232 | 7 | 91/116 · 98/232 · 7/7 | 149 | 10 | 0 | 2 | 4 | contradiction; irregular_mapping; missing_rule | [p92 notes](p92/rewrite_notes.md) |
| p93 | Preserved | 81 | 162 | 8 | 81/81 · 162/162 · 8/8 | 0 | 0 | 0 | 0 | 0 | — | [p93 notes](p93/rewrite_notes.md) |
| p94 | Preserved | 25 | 50 | 3 | 25/25 · 50/50 · 3/3 | 0 | 0 | 0 | 0 | 0 | — | [p94 notes](p94/rewrite_notes.md) |
| p95 | Preserved | 21 | 42 | 3 | 21/21 · 42/42 · 3/3 | 0 | 0 | 0 | 0 | 0 | — | [p95 notes](p95/rewrite_notes.md) |
| p96 | Rewrite | 49 | 98 | 5 | 49/49 · 88/98 · 5/5 | 0 | 10 | 0 | 0 | 1 | missing_rule | [p96 notes](p96/rewrite_notes.md) |
| p97 | Rewrite | 26 | 52 | 7 | 26/26 · 50/52 · 7/7 | 2 | 0 | 0 | 0 | 1 | missing_rule | [p97 notes](p97/rewrite_notes.md) |
| p98 | Rewrite | 42 | 84 | 6 | 42/42 · 84/84 · 6/6 | 0 | 0 | 0 | 2 | 2 | ambiguity; contradiction | [p98 notes](p98/rewrite_notes.md) |
| p99 | Preserved | 53 | 106 | 5 | 53/53 · 106/106 · 5/5 | 0 | 0 | 0 | 0 | 0 | — | [p99 notes](p99/rewrite_notes.md) |
| p100 | Preserved | 77 | 154 | 21 | 77/77 · 154/154 · 21/21 | 0 | 0 | 0 | 0 | 0 | — | [p100 notes](p100/rewrite_notes.md) |

## Change categories

| Category | Recorded change points |
|---|---:|
| ambiguity | 46 |
| contradiction | 31 |
| irregular_mapping | 16 |
| missing_rule | 51 |

## Independent spot checks

Two independent read-only spot checks were performed after the case rewrites. The high-risk sample covered p25, p39, p57, p68, p77, p82, p89, and p91; the preserved-description sample covered p02, p20, p40, p55, p74, and p86. All 14 cases passed, reconciling 3,751/3,751 semantic items with their ledgers and golden PDDL. No spot-check agent edited a case artifact.

逐题改写结束后进行了两组独立只读抽查。高风险样本包括 p25、p39、p57、p68、p77、p82、p89 和 p91；原样保留样本包括 p02、p20、p40、p55、p74 和 p86。14 道题全部通过，共核对 3,751/3,751 个语义项目及其账本与 golden PDDL；抽查 agent 未修改任何逐题产物。

- [High-risk spot check](spot_checks/high_risk_spot_check.md)
- [Preserved-description spot check](spot_checks/preserved_random_spot_check.md)

## Artifact layout

Each `pXX/` directory contains the copied golden domain and problem, the original description, the complete final English description, a Chinese reference translation, bilingual rewrite notes, a structured result, and the atomic evidence ledger. `case_summary.csv` and `change_catalog.csv` provide machine-readable indexes across all cases.

每个 `pXX/` 目录均包含 golden domain 与 problem 副本、原始描述、完整的最终英文描述、中文参考译文、双语改写说明、结构化结果和逐原子证据账本。`case_summary.csv` 与 `change_catalog.csv` 提供覆盖全部题目的机器可读索引。

- [Complete rewrite explanations and evidence](rewrite_explanations_compendium.md)
- [Complete final descriptions](final_descriptions_compendium.md)

## Source preservation

No Natural Logistics source description was edited by this audit. All proposed descriptions and diagnostics reside under this output directory.

本次审计没有修改任何 Natural Logistics 原始描述。所有推荐描述和诊断材料均保存在本输出目录中。

# p66 audit and rewrite notes

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

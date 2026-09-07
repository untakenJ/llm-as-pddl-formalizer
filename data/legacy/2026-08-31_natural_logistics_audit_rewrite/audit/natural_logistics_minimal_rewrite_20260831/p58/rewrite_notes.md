# p58 audit and rewrite notes

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

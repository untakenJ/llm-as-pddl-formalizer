# Natural Logistics Minimal Rewrite and Atomic Audit Principles

## Purpose and scope

These principles apply to every problem in the Natural Logistics dataset. They
govern both the audit decision and any proposed rewrite of a natural-language
problem description against its golden PDDL problem and domain files.

The task is an evidence-completeness audit first and a rewriting task only when
the audit proves that a rewrite is necessary. The objective is not to translate
PDDL line by line, normalize prose across the dataset, or improve style for its
own sake. The objective is to preserve the existing description whenever it is
already correct and to make the smallest sufficient repair when it is not.

## Highest-priority rule: do not rewrite a correct description

Do not assume that every problem needs a rewrite.

Return `NO REWRITE REQUIRED` and preserve the original description verbatim if
all of the following hold:

- every golden PDDL object has a direct and unambiguous natural-language
  counterpart;
- every golden type fact, initial-state atom, and goal atom is supported by a
  direct statement or by a finite deterministic rule with a unique expansion;
- the natural description contains no statement that contradicts the golden
  PDDL;
- the natural description does not imply extra objects, relations, or goals
  absent from the golden PDDL; and
- a reader can recover the relevant objects and relations without consulting
  the PDDL or guessing an unstated convention.

Do not rewrite correct text merely to improve fluency, regularize style, change
paragraph structure, replace one correct formulation with another, expand a
clear rule into a long enumeration, or compress an already complete statement.

## Authoritative sources and scope boundaries

- The golden PDDL problem is authoritative for objects, the initial state, and
  the goal.
- The golden PDDL domain is authoritative for predicate meanings and action
  semantics. Use it to interpret the problem; do not restate the action model
  inside the problem description.
- Do not invent, delete, or change a golden fact.
- Do not add unnecessary metadata such as the PDDL problem name or a sentence
  announcing the domain unless the original dataset style genuinely requires
  it.
- Do not modify the source dataset while auditing. Write proposed descriptions
  and audit artifacts only to the designated output directory.

## Minimal-repair hierarchy

When a rewrite is required, preserve the original tone, organization, and all
unaffected wording. Use this order of preference:

1. Remove or replace only the weakening word that causes uncertainty, such as
   `like`, `some`, `various`, or an incomplete use of `for example`.
2. Add a missing finite bound, index correspondence, or exception to an existing
   rule.
3. Add one deterministic rule for a regular family of facts.
4. Add explicit mappings only for irregular facts or exceptions.
5. Rewrite a whole sentence only when a local edit cannot repair it.
6. Rewrite a whole paragraph only when its structure itself causes ambiguity or
   contradiction.

Every unchanged sentence and phrase should remain verbatim whenever practical.

## Acceptable evidence and deterministic compression

A single natural-language statement may support multiple PDDL items. Accept:

- direct statements, such as `apn1 is at apt1`;
- finite ranges, such as `the locations are pos1 through pos10`;
- ordered mappings using `respectively`;
- finite index rules whose bounds and substitution are explicit; and
- finite group rules followed by one or two illustrative examples.

A compressed rule is valid only if it states or makes unambiguously clear:

- the complete finite range;
- how every identifier is constructed;
- how indices on different sides of a relation correspond; and
- all exceptions.

The rule must expand to exactly the golden items: no omissions, contradictions,
or extra objects and atoms. Examples may illustrate a complete rule but may not
stand in for missing facts.

Do not credit vague placeholders such as `and so forth`, `and so on`,
`similarly`, `as outlined`, `various locations`, `distributed among`,
`corresponding locations` without a defined correspondence, or examples without
a preceding complete rule. Do not infer a pattern merely because several facts
happen to resemble one another.

Avoid pseudo-ranges that can over-generate identifiers. For example,
`obj11 through obj103` may suggest every integer label between the endpoints.
Replace it with a bounded construction rule if the actual object set follows a
grouped naming scheme.

## Objects, types, initial state, and goal

Every object and unary type fact must be recoverable from the description. One
sentence may support both an object declaration and its type fact.

Every initial-state atom must have either a direct statement or a uniquely
expandable finite rule. Clearly distinguish initial locations from goal
locations. Use rules for genuinely regular mappings and explicit statements for
irregular mappings and exceptions.

Treat the PDDL goal as a conjunction: every listed goal atom must hold
simultaneously. Use a deterministic rule only when the complete goal mapping is
truly regular and exception-free. Otherwise enumerate every object-destination
pair. Never replace irregular goals with examples or vague continuation phrases.

## Required audit and rewrite procedure

For each problem:

1. Parse every golden object declaration.
2. Parse every golden init atom, including unary type facts.
3. Parse every golden goal atom.
4. Map each item to its evidence in the existing natural description.
5. Classify each item as direct evidence, deterministic-rule evidence,
   ambiguous/incomplete evidence, missing evidence, or contradictory evidence.
6. Decide `NO REWRITE REQUIRED` or `REWRITE REQUIRED` before drafting.
7. If rewriting is required, change only the smallest text spans needed to fix
   every confirmed defect.
8. Re-parse and re-audit the complete proposed description independently against
   the golden PDDL.
9. Check for omissions, ambiguity, contradictions, and over-generation.

## Mandatory post-rewrite atomic verification

Completion requires a renewed item-by-item evidence check. For every golden
object or atom, record:

- the PDDL item;
- the exact natural-language sentence, phrase, or rule that supports it;
- whether the evidence is direct or rule-based;
- whether the correspondence is unique; and
- any relevant explanation of the rule expansion.

If evidence is rule-based, actually expand the rule and confirm that it produces
the item, produces every required sibling item, introduces no extra item, and
has no unstated exception or alternative interpretation.

A proposed rewrite passes only when all of the following are true:

- object coverage equals total objects over total objects;
- init coverage equals total init atoms over total init atoms;
- goal coverage equals total goal atoms over total goal atoms;
- missing count is zero;
- ambiguous count is zero;
- contradictory count is zero; and
- over-generated count is zero.

If any golden item still requires guessing, the rewrite is not complete.

## Required per-problem artifacts

Each problem audit must retain:

- a copy of the golden domain file;
- a copy of the golden problem file;
- the original natural problem description;
- the complete proposed description, or an exact copy of the original when no
  rewrite is required;
- a rewrite explanation listing every changed text span, the reason for the
  change, and supporting golden PDDL evidence; and
- an atomic evidence ledger covering every golden object, init atom, and goal
  atom after the decision or rewrite.

The explanation must also report what was deliberately preserved, before/after
coverage counts, and the final omission, ambiguity, contradiction, and
over-generation counts.

## Final quality standard

The result must be minimally changed, semantically complete, directly auditable,
compact where deterministic compression is safe, explicit where mappings are
irregular, free of vague placeholders, free of invented facts, and uniquely
recoverable without access to the PDDL.


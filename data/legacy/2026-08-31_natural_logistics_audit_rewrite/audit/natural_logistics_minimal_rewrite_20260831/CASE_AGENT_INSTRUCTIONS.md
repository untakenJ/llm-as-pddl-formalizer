# Case-agent instructions

Read `.cache/reporting/NATURAL_LOGISTICS_MINIMAL_REWRITE_PRINCIPLES.md` in full
before working on any case. Those principles are mandatory.

## Write boundary

For an assigned case `pXX`, write only inside:

`output/audit/natural_logistics_minimal_rewrite_20260831/pXX/`

Do not edit `data/`, tracked files, another case directory, the top-level audit
summary, or the principles document.

## Required work for each case

1. Read `golden_domain.pddl`, `golden_problem.pddl`, and
   `natural_original.txt` from the case directory.
2. Parse every object, init atom, and goal atom from the golden problem.
3. Audit the original description under the principles, including deterministic
   rule expansion, contradiction checks, and over-generation checks.
4. Decide `NO REWRITE REQUIRED` or `REWRITE REQUIRED` before drafting.
5. Put the complete final English description in `natural_rewritten.txt`. For a
   no-rewrite decision it must be byte-for-byte identical to
   `natural_original.txt`.
6. Put a faithful Chinese reference translation of the final English description
   in `natural_rewritten_zh_reference.txt`.
7. Write `rewrite_notes.md` with the required structure below.
8. Write `evidence_ledger.csv` with exactly one data row per golden object, init
   atom, and goal atom after the decision/rewrite.
9. Write `audit_result.json` using the schema below.
10. Re-check all files and report only a concise completion summary to the parent
    agent.

## `rewrite_notes.md` structure

- Title with the case ID.
- Decision: `NO REWRITE REQUIRED` or `REWRITE REQUIRED`.
- English finding followed immediately by a Chinese reference translation.
- Source inventory and exact object/init/goal totals.
- Before-rewrite coverage and defect counts.
- A complete change table with one row for every changed span. Columns:
  `#`, `Original text`, `Revised text`, `Reason / 原因`, and
  `Golden PDDL evidence`.
- A short list of material text deliberately preserved and why.
- Post-rewrite verification counts.
- Final assertion that missing, ambiguous, contradictory, and over-generated
  counts are all zero, or an explicit blocker if they are not.

For `NO REWRITE REQUIRED`, the change table must explicitly say that no text was
changed and explain why the original already passes.

Golden evidence must identify the exact PDDL atom or object and its line number
or line span in `golden_problem.pddl`. Use the domain file when predicate/action
semantics are relevant.

## `evidence_ledger.csv`

Use the existing header exactly:

`section,pddl_item,evidence,evidence_kind,unique,status,notes`

Requirements:

- `section` is `objects`, `init`, or `goal`.
- `pddl_item` is the normalized object name or full normalized PDDL atom.
- `evidence` is the exact sentence, phrase, or complete deterministic rule from
  `natural_rewritten.txt`.
- `evidence_kind` is `direct` or `deterministic_rule`.
- `unique` must be `true` for a passing result.
- `status` must be `covered` for a passing result.
- `notes` explains rule expansion when useful.
- Do not use one row to stand in for several items: expand deterministic rules
  into one ledger row per golden item while repeating the supporting rule.

## `audit_result.json` schema

```json
{
  "case": "pXX",
  "status": "COMPLETE",
  "decision": "NO REWRITE REQUIRED or REWRITE REQUIRED",
  "counts": {
    "objects": 0,
    "init": 0,
    "goal": 0,
    "semantic_items": 0
  },
  "before": {
    "objects_covered": 0,
    "init_covered": 0,
    "goal_covered": 0,
    "missing": 0,
    "ambiguous": 0,
    "contradictory": 0,
    "over_generated": 0
  },
  "after": {
    "objects_covered": 0,
    "init_covered": 0,
    "goal_covered": 0,
    "missing": 0,
    "ambiguous": 0,
    "contradictory": 0,
    "over_generated": 0
  },
  "changes": [
    {
      "id": 1,
      "category": "ambiguity, missing_rule, irregular_mapping, or contradiction",
      "original_text": "...",
      "revised_text": "...",
      "reason_en": "...",
      "reason_zh": "...",
      "golden_evidence": ["golden_problem.pddl:line: (ATOM ...)"]
    }
  ],
  "preserved": ["brief description of deliberately unchanged material"],
  "verification": {
    "ledger_rows": 0,
    "all_items_covered": true,
    "all_correspondences_unique": true,
    "no_over_generation": true
  }
}
```

The totals must satisfy:

- `semantic_items = objects + init + goal`;
- `ledger_rows = semantic_items`;
- all after-coverage counts equal their corresponding totals; and
- all four after-defect counts equal zero.

Do not mark a case complete if those invariants fail.

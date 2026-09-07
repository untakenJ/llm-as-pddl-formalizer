# Pre-DATA-001 and targeted Logistics fixes backup

Created after the `20260831-132155` sweep completed and before applying the
dataset corrections requested on 2026-08-31.

This archive preserves the exact textual datasets used by that completed
study:

- `textual_barman/Heavily_Templated_Barman-100/` — 100 domain descriptions
  and 100 problem descriptions.
- `textual_logistics/Natural_Logistics-100/` — 100 domain descriptions and
  100 problem descriptions, including the earlier audited rewrites present in
  the working tree.

The golden PDDL datasets are not duplicated because this revision does not
modify them. The authoritative golden files remain in
`data/textual_barman/Barman-100_PDDL/` and
`data/textual_logistics/Logistics-100_PDDL/`.

Verification performed immediately after copying:

- Recursive byte comparison: no differences for either dataset.
- Barman content-hash multiset: `da42078b9276994654212ca0177975520727dd4ee268de8706930791a6b60d92`.
- Logistics content-hash multiset: `26ad9b834c81696733a896adfc6693c15c7fd97129024a6e01792c75168eb767`.

Do not edit this directory; it is the legacy input snapshot for the completed
`20260831-132155` study.

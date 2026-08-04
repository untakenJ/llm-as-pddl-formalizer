# PDDL Domain Equivalence Checker

This package checks two increasingly permissive forms of structural equivalence
between PDDL domain files:

1. **Level 1 — fixed-symbol alpha/ABI equivalence.** Type, predicate, action, and
   domain-constant correspondences are fixed by identical names or by a supplied
   mapping. Local variable names, declaration order, conjunction order, and consistent
   action/predicate parameter permutations are ignored.
2. **Level 2 — schema isomorphism.** The checker searches for a global bijection over
   types, predicates, actions, domain constants, and signature parameter positions. A
   discovered mapping is accepted only after it passes the level-one checker.

Level 2 therefore covers Level 1 for the supported language:

```text
fixed symbol mapping + exact structure
                  ⊆
unknown bijective symbol mapping + exact structure
```

This is a domain-only checker. It does not compare problem objects, initial states,
goals, or plans.

## Quick start

The package lives under `source/` and uses NetworkX, which is declared in the root
project dependencies:

```bash
PYTHONPATH=source uv run python -m pddl_domain_equivalence \
  data/textual_blocksworld/BlocksWorld-100_PDDL/domain.pddl \
  data/textual_mystery_blocksworld/Mystery_BlocksWorld-100_PDDL/domain.pddl
```

The command above reports `schema_isomorphic`: Mystery BlocksWorld is a systematic
renaming of the ordinary BlocksWorld domain.

Select a level explicitly:

```bash
PYTHONPATH=source uv run python -m pddl_domain_equivalence \
  left-domain.pddl right-domain.pddl --level 1

PYTHONPATH=source uv run python -m pddl_domain_equivalence \
  left-domain.pddl right-domain.pddl --level 2 --json
```

`--level auto` is the default. It first tries Level 1 and then Level 2.

Exit codes are:

- `0`: equivalent at the requested level;
- `1`: both inputs were supported, but no equivalence was found;
- `2`: malformed input, unsupported PDDL, or malformed mapping JSON.

A well-formed mapping whose symbols do not cover the two domains is a failed
equivalence claim and returns `1`.

## Level-one mappings

Without a mapping file, Level 1 fixes every global symbol by its case-insensitive PDDL
name. A JSON mapping can provide renamed symbols. Unspecified symbols fall back to an
identically named symbol on the right:

```json
{
  "types": {
    "block": "item"
  },
  "predicates": {
    "on": "above"
  },
  "actions": {
    "stack": "place"
  },
  "constants": {},
  "predicate_parameters": {
    "on": [1, 0]
  },
  "action_parameters": {
    "stack": [1, 0]
  }
}
```

Parameter arrays are zero-based and map each left position to a right position. They
are optional: when omitted, the checker infers a consistent permutation while keeping
the supplied global symbol mapping fixed.

Use a mapping with:

```bash
PYTHONPATH=source uv run python -m pddl_domain_equivalence \
  left-domain.pddl right-domain.pddl --level 1 --mapping mapping.json
```

## Python API

```python
from pddl_domain_equivalence import compare_domains

result = compare_domains("left.pddl", "right.pddl", level="auto")
if result.equivalent:
    print(result.relation)
    print(result.mapping.to_dict())
else:
    print(result.reason)
```

The main entry points are:

- `compare_level_one(left, right, mapping=None)`;
- `compare_level_two(left, right)`;
- `compare_domains(left, right, level="auto", mapping=None)`;
- `parse_domain(text)` and `parse_domain_file(path)`.

## Algorithm

The checker parses each domain into an immutable STRIPS-oriented model and constructs
a directed, edge-labelled semantic graph inspired by the Lifted Domain Model Graph
(LDMG) of Chrpa et al. The graph contains:

- type nodes and type-parent edges;
- predicate and predicate-parameter-position nodes;
- action and action-parameter nodes;
- separate positive-precondition, negative-precondition, add-effect, and delete-effect
  occurrence nodes;
- binding nodes connecting every literal argument to both its predicate position and
  its action parameter or domain constant.

Expanding argument bindings into graph nodes lets a standard NetworkX
`DiGraphMatcher` search for a complete labelled isomorphism and recover parameter
permutations. Level 1 applies unique pins to the fixed symbol pairs before matching.
Level 2 leaves symbols unpinned, extracts a mapping certificate, and reruns Level 1
with that certificate.

Names are deliberately absent from unconstrained graph colors. Node kinds, edge kinds,
type hierarchy, arity, literal role, and argument binding are preserved.

## Supported PDDL

The parser currently supports the conservative fragment needed by the repository's
classical benchmark domains:

- `:strips`;
- `:typing`, including single-inheritance type hierarchies;
- `:negative-preconditions`;
- typed and untyped predicates;
- typed and untyped action parameters;
- conjunctions of literals;
- positive and negative preconditions;
- add and delete effects;
- domain constants.

PDDL is case-insensitive. Domain names, comments, requirement ordering, section
ordering, action/predicate declaration ordering, conjunction ordering, and local
variable names are not semantically significant.

The checker rejects an input instead of silently ignoring a construct it cannot model.

## Not supported and not applicable

The current checker is **not applicable** to domains using:

- disjunction, implication, existential or universal quantification;
- conditional effects;
- equality or inequality;
- derived predicates;
- numeric fluents, functions, or action costs;
- durative actions, temporal conditions/effects, preferences, or trajectory
  constraints;
- nondeterministic effects;
- PDDL+ processes or events.

It is also not a functional or behavioural equivalence checker. In particular, it will
reject structurally non-bijective but potentially valid reformulations such as:

- one generic action versus several type-specialized actions;
- one action versus a macro sequence;
- one predicate versus several predicates split by disjoint types;
- PDDL types versus static unary type predicates;
- auxiliary-state compilations.

Those cases belong to a future **Level 3 — controlled compilation equivalence** layer.
`transforms.py` reserves a transformation interface and map-back certificate type, but
no non-identity transformation is currently registered or accepted.

An extra macro action, even when behaviourally redundant, also makes the domains
non-isomorphic. Conversely, a small structural difference is not evidence that two
domains are behaviourally close. This package should not be used as a replacement for
plan validation, reachability analysis, or problem-file equivalence.

Graph isomorphism can be expensive in the worst case. The intended inputs are
human-sized lifted planning domains, not fully grounded state-transition systems.

## Tests

Run the isolated test suite from the repository root:

```bash
PYTHONPATH=source uv run python -m unittest discover \
  -s tests/domain_equivalence_checker -v
```

The tests include constructed positive/negative examples, all four official repository
domains, the real BlocksWorld/Mystery BlocksWorld schema-isomorphism pair, a real
agent-generated Natural BlocksWorld domain accepted with mappings such as
`arm-empty -> handempty`, and a real agent-generated Natural Logistics domain that is
correctly rejected at Level 2 because it requires non-bijective
type/action/predicate compilation.

## References and provenance

The representation and reduction from strong domain equivalence to labelled graph
isomorphism are based on the JELIA 2023 work by Chrpa et al. This implementation does
not copy their ASP source: it extends the published graph idea with explicit type,
signature-position, literal-occurrence, and binding nodes and uses NetworkX's VF2
directed graph matcher.

Full bibliographic records and notes on what was reused are in
[`REFERENCES.md`](REFERENCES.md).

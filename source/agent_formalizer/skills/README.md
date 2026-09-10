# Experimental skill library

This directory stores **opt-in experimental skills**, not the harnesses' bundled
skills. Adding a package does not enable it. The default baseline retains the
current pinned, benchmark-filtered official
skills/configuration of each harness; this feature does not restore disabled
official skills or change any native discovery settings.

## Available skills

- [`simulate-and-check-plan`](simulate-and-check-plan/SKILL.md): Write a simulator
  using the Python standard library, then replay and inspect a PDDL-style plan
  against the task descriptions. Diagnose errors and restart after repairs.

To make this skill available, set
`condition_profile.overrides.experiment_skills` to `["simulate-and-check-plan"]`
in a separate experiment profile. The agent chooses whether to read and use it.
User-editable profiles are centralized in
[`../configs/benchmark_profiles/`](../configs/benchmark_profiles/README.md);
see the [configuration guide](../configs/README.md) for selection and path rules.

## Package format

Create a directory named with lowercase letters/digits and hyphens (up to 64
characters), with a UTF-8 `SKILL.md` containing YAML frontmatter:

```text
source/agent_formalizer/skills/<skill-name>/
  SKILL.md
  scripts/       # optional
  references/    # optional
  assets/        # optional
```

```markdown
---
name: example-skill
description: Briefly describe what this skill does and when it is useful.
---

Instructions for using the skill. Refer to supporting files with paths relative
to this directory. Write generated files outside the read-only skill directory.
```

The frontmatter name must match the directory name. The description is included
in the common task prompt, but the instruction body and resources are not loaded
into context automatically. Other frontmatter fields are retained and hashed but
do not create tools or grant permissions. All files in a selected package are
included, including scripts, references, and assets; do not store credentials,
case-specific answers, caches, personal state, or unreviewed files here. Symlinks
and special files are rejected, including symlink directories. Scripts are not
automatically executed and dependencies are not installed by this mechanism.

## Selecting an ablation condition

Copy the desired benchmark profile and edit its existing
`condition_profile.overrides` (preserve all unrelated fields):

```json
{
  "skills_mode": "official",
  "experiment_skills": ["example-skill", "another-skill"]
}
```

Use that profile with the existing `--benchmark-config` option of
`run_formalizer_agent.py` or `sweep_agent_pipeline.py`. This is a **condition**
setting, not an operational setting. The example names above are placeholders,
not installed packages. Selection is explicit; there is no wildcard/all mode.

| Condition | `experiment_skills` | Official baseline |
| --- | --- | --- |
| Baseline | omitted or `[]` | unchanged |
| A | `["skill-a"]` | unchanged |
| B | `["skill-b"]` | unchanged |
| A + B | `["skill-a", "skill-b"]` | unchanged |

`skills_mode: "none"` remains the separate existing official-skills ablation;
it does not disable explicitly selected experimental skills. Do not use it when
the intention is to retain the current official baseline. Selection order is
normalized alphabetically and duplicate or unknown names fail before execution.
Use a new study/output for a changed selection or changed selected content.

## Equal availability, on-demand consumption

OpenClaw, Hermes, Nanobot, Generic, and ZeroClaw receive the **same additional
catalog text** (name, description, absolute entrypoint) and the same selected
files at `/workspace/.benchmark-skills/<skill-name>/SKILL.md`, mounted read-only.
Only selected packages are mounted, never the entire library or other cases.
Agents read the instructions/resources with their existing native file/shell
tools when they decide to do so. Reading, reasoning about, and executing copied
skill code consumes the normal native tool/action budgets and active time.

This delivery mode is `on-demand-catalog-v1`: a common experimental prompt/file
intervention, **not** integration with five different native skill registries.
It does not force skill use, inject full instructions, add native tools, alter
official skills or memory, change retry clocks, or equalize harness success rates.
Native tools can still differ in how they read files and execute scripts.
The host-only `minimum` adapter lacks file tools and rejects nonempty selection.

## Identity, snapshots, and resume

The resolved condition includes the delivery version, sorted selection,
descriptions, entrypoints, and every selected file's bytes/SHA-256 and executable
flag. Selected content changes the resolved hash/output label. Unselected library
files do not enter that hash or the adapter-code hash. The loader's implementation
does enter the adapter-code hash, as do other implementation changes. With no
selected skills, the canonical prompt and resolved semantic config are unchanged;
this does not waive the existing runtime-identity rules for resuming old studies.

The sweep runner freezes selected packages under `study_skills/<bundle-sha256>/`
and pins their hash in `study_benchmark_profile.json`. Resume using that frozen
profile; it no longer depends on mutable library files. Modified frozen content
is rejected. For an individual runner process, resolution captures immutable
bytes in memory. Each execution stores only its selected packages under
`experiment_skills/`, plus `experiment_skills_manifest.json`; provenance includes
the manifest and hash alongside the existing official-skills evidence. Isolation
preflight verifies both the snapshot and the read-only mount. Availability is not
proof of usage: actual consumption must be established from native tool/session
traces, whose existing evidence limitations still apply.

For an alternative or frozen library location, a profile may optionally include
the following **top-level** source locator (normally generated by the sweep):

```json
"experiment_skill_library": {
  "path": "study_skills/<bundle-sha256>",
  "sha256": "<64-character bundle SHA-256>"
}
```

Relative paths are resolved against the profile's directory. The source path is
not semantic identity; selected content is. `sha256` is optional for authoring
profiles and required in sweep-generated snapshots. Without this locator the
library is this directory in the running code copy. Keep frozen campaign code
and profiles untouched; adding support or packages to the working tree does not
hot-update an already frozen campaign.

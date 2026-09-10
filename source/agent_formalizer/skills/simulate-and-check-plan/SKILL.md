---
name: simulate-and-check-plan
description: Build a Python simulator from planning task descriptions to replay a PDDL-style plan, inspect intermediate states and goals, and diagnose formalization or simulator errors.
---

# Simulate and check a plan

Write and run a task-specific simulator using only the Python standard library.
Use the supplied domain description, problem description, generated PDDL files,
and plan. No domain-specific knowledge or reference solution is bundled here.

## Phase 1: Write the simulator

1. Read the descriptions. Define action and predicate semantics strictly from the
   domain description, and objects, initial state, and goals from the problem
   description. Identify the constraints to inspect during simulation.
2. Consult the generated domain/problem files for names, structure, and possible
   formalization differences. The descriptions remain authoritative. Do not add
   restrictions based only on everyday intuition.
3. Write Python code that reads PDDL-style plan actions and executes state
   transitions. Normalize case; check action names, argument counts, objects,
   types, and preconditions. Reject malformed or unsupported input explicitly.
   For sequential STRIPS actions, check preconditions against the pre-action
   state, then apply effects as `(state - deletes) | adds`.
4. Make the simulator expose the initial state, each action's resulting state,
   and the final goal-check results for inspection. Include automatic checks for
   the identified constraints and return a nonzero exit status on failure.

If a problem is found during this phase, resolve it before entering Phase 2.
Correct simulator implementation errors against the descriptions. If generated
PDDL conflicts with the descriptions, identify the affected file and rule, and
fix it within the authorized scope or state the proposed correction. If wording
is ambiguous, record the ambiguity and your interpretation, and decide whether
a PDDL change is warranted. Do not silently choose rules to make the plan pass.
If faithful implementation remains impossible, report the unresolved issue.

After any PDDL modification, obtain a new plan through the existing solver
workflow. Enter Phase 2 only with a simulator ready for inspection and a plan
corresponding to the current PDDL files.

## Phase 2: Execute and inspect

1. Start from the described initial state and inspect it for inconsistencies.
2. Execute the plan step by step. Inspect the world state after every action,
   checking for violated task constraints and states forbidden by the
   descriptions. Use both the automatic checks and your review of the exposed
   states; a successful program exit alone is insufficient.
3. After the last action, inspect the final state for the same issues and verify
   every goal condition against the problem description.

If any execution or inspection reveals a problem:

1. Stop the current simulation or review immediately. Preserve the first failure,
   its action index (or initial/final inspection), relevant states, and evidence.
2. Compare the descriptions, generated PDDL, and simulator code. Determine whether
   the cause is a domain-file error, problem-file error, simulator error, or a
   plan/file mismatch. Do not assume the solver or simulator must be correct.
3. Return to Phase 1 to correct the relevant implementation within the authorized
   scope. Explain the fix using the descriptions or execution semantics. Never
   weaken a constraint merely to accept the plan. If PDDL changes, obtain a new
   plan; if only the simulator changes, the existing matching plan may be reused.
4. Restart Phase 2 from the initial state after the fix. Do not resume from the
   failed step or retain state from the previous run. If the issue cannot be
   resolved, stop and report incomplete validation without claiming success.

Report success only after all stepwise inspections and final checks pass.
Preserve the simulator and inspection results; summarize failures, fixes, and
limitations. A successful replay supports this plan under the encoded semantics;
it does not prove complete PDDL correctness or domain equivalence.

# Optional agent tools

Condition profiles enable tools with:

```json
"condition_profile": {
  "id": "solver-as-tool",
  "overrides": { "agent_tools": ["pddl_solver"] }
}
```

Each subdirectory is one tool. Register new tools in `__init__.py`
(`KNOWN_AGENT_TOOLS`) so workspace mounting, prompt selection, and schema
validation stay centralized.

| Tool id | Package | Agent surface |
|---|---|---|
| `pddl_solver` | `tools/solver/` | `/usr/local/bin/pddl-solver` + `solver-gateway` |

Benchmark study profiles that enable tools live under
`benchmark_profiles/` (not inside each tool package), so study identity stays
separate from tool implementation.

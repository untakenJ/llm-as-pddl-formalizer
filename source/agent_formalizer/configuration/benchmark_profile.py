"""Strict layered configuration for agent-harness benchmark runs."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Any

from .skill_library import SkillBundle, bundle_for_profile, validate_selection, validate_source
from . import CONFIGS_DIR


BENCHMARK_PROFILES_DIR = CONFIGS_DIR / "benchmark_profiles"
DEFAULT_PROFILE_PATH = BENCHMARK_PROFILES_DIR / "native_baseline_v1.json"
KNOWN_HARNESSES = {
    "openclaw",
    "hermes",
    "nanobot",
    "zeroclaw",
    "generic",
    "minimum",
}
NETWORK_MODES = {"model_only", "controlled_web"}
SOLVER_BACKENDS = {"public", "local", "public_then_local"}
MODEL_RESPONSE_DELIVERY_MODES = {"buffered_atomic", "native_streaming"}
VALIDATION_PRESETS = {
    "runtime-lock",
    "network-model-only",
    "environment-isolation",
    "action-step-guard",
    "state-isolation",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _keys(
    value: dict[str, Any],
    *,
    required: set[str] = frozenset(),
    optional: set[str] = frozenset(),
    path: str,
) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise ValueError(f"{path} is missing fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{path} has unknown fields: {', '.join(unknown)}")


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{path} must be a positive integer")
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path} must be a non-negative integer")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _validate_budget(value: Any, path: str, *, comparable_field: bool = False) -> None:
    row = _object(value, path)
    optional = {"cross_harness_comparable"} if comparable_field else set()
    _keys(row, required={"limit", "role", "scope"}, optional=optional, path=path)
    _positive_int(row["limit"], f"{path}.limit")
    if row["role"] not in {"native_limit", "safety_guard", "experimental_budget"}:
        raise ValueError(f"{path}.role is not supported")
    _string(row["scope"], f"{path}.scope")
    if "cross_harness_comparable" in row and not isinstance(
        row["cross_harness_comparable"], bool
    ):
        raise ValueError(f"{path}.cross_harness_comparable must be boolean")


def _validate_profile(raw: dict[str, Any], path: Path) -> None:
    _keys(
        raw,
        required={
            "schema_version",
            "profile_id",
            "native_clean",
            "benchmark_envelope",
            "condition_profile",
            "sampling",
            "infra_retry",
            "providers",
            "harness_overrides",
        },
        optional={"experiment_skill_library"},
        path=str(path),
    )
    if "experiment_skill_library" in raw:
        validate_source(raw["experiment_skill_library"])
    if raw["schema_version"] != 3:
        raise ValueError(f"Unsupported benchmark profile schema: {raw['schema_version']}")
    _string(raw["profile_id"], "profile_id")

    native = _object(raw["native_clean"], "native_clean")
    _keys(native, required={"id", "mode"}, path="native_clean")
    _string(native["id"], "native_clean.id")
    _string(native["mode"], "native_clean.mode")

    envelope = _object(raw["benchmark_envelope"], "benchmark_envelope")
    _keys(
        envelope,
        required={
            "id",
            "control_model",
            "safety_guards",
            "network",
            "model_error_routing",
            "interaction",
            "state_isolation",
            "environment",
            "container_resources",
            "artifact_contract",
            "validations",
            "required_evidence",
        },
        optional={"model_response_delivery"},
        path="benchmark_envelope",
    )
    _string(envelope["id"], "benchmark_envelope.id")
    if "/" not in _string(envelope["control_model"], "control_model"):
        raise ValueError("benchmark_envelope.control_model must use provider/model form")

    guards = _object(envelope["safety_guards"], "safety_guards")
    _keys(
        guards,
        required={
            "harness_execution_timeout_seconds",
            "control_model_request_attempts",
            "action_steps",
        },
        path="benchmark_envelope.safety_guards",
    )
    _validate_budget(
        guards["harness_execution_timeout_seconds"],
        "safety_guards.harness_execution_timeout_seconds",
    )
    _validate_budget(
        guards["control_model_request_attempts"],
        "safety_guards.control_model_request_attempts",
    )
    _validate_budget(
        guards["action_steps"],
        "safety_guards.action_steps",
        comparable_field=True,
    )
    if (
        guards["control_model_request_attempts"]["limit"]
        > guards["action_steps"]["limit"]
    ):
        raise ValueError(
            "control_model_request_attempts.limit cannot exceed action_steps.limit"
        )

    network = _object(envelope["network"], "benchmark_envelope.network")
    _keys(
        network,
        required={"mode", "controlled_web_allowlist"},
        path="benchmark_envelope.network",
    )
    if network["mode"] not in NETWORK_MODES:
        raise ValueError(f"Unsupported network mode: {network['mode']}")
    if not isinstance(network["controlled_web_allowlist"], list) or not all(
        isinstance(item, str) and item for item in network["controlled_web_allowlist"]
    ):
        raise ValueError("controlled_web_allowlist must be a list of strings")
    if network["mode"] == "controlled_web" and not network["controlled_web_allowlist"]:
        raise ValueError("controlled_web requires a non-empty allowlist")

    routing = _object(
        envelope["model_error_routing"], "benchmark_envelope.model_error_routing"
    )
    _keys(
        routing,
        required={
            "id",
            "max_retries",
            "backoff_seconds",
            "max_retry_after_seconds",
            "retryable_http_statuses",
        },
        path="benchmark_envelope.model_error_routing",
    )
    _string(routing["id"], "model_error_routing.id")
    _positive_int(routing["max_retries"], "model_error_routing.max_retries")
    if not isinstance(routing["backoff_seconds"], list) or not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
        for value in routing["backoff_seconds"]
    ):
        raise ValueError("model_error_routing.backoff_seconds must be non-negative numbers")
    if len(routing["backoff_seconds"]) != routing["max_retries"]:
        raise ValueError(
            "model_error_routing.backoff_seconds must contain one value per retry"
        )
    if (
        isinstance(routing["max_retry_after_seconds"], bool)
        or not isinstance(routing["max_retry_after_seconds"], (int, float))
        or routing["max_retry_after_seconds"] < 0
    ):
        raise ValueError(
            "model_error_routing.max_retry_after_seconds must be non-negative"
        )
    statuses = routing["retryable_http_statuses"]
    if not isinstance(statuses, list) or not statuses or not all(
        isinstance(status, int)
        and not isinstance(status, bool)
        and 400 <= status <= 599
        for status in statuses
    ):
        raise ValueError(
            "model_error_routing.retryable_http_statuses must be HTTP error codes"
        )
    if len(set(statuses)) != len(statuses):
        raise ValueError("model_error_routing.retryable_http_statuses must be unique")

    delivery = envelope.get(
        "model_response_delivery",
        {
            "mode": "buffered_atomic",
            "first_event_commit": False,
            "action_step_admission": "exact_complete_batch",
        },
    )
    delivery = _object(delivery, "benchmark_envelope.model_response_delivery")
    _keys(
        delivery,
        required={"mode", "first_event_commit", "action_step_admission"},
        path="benchmark_envelope.model_response_delivery",
    )
    if delivery["mode"] not in MODEL_RESPONSE_DELIVERY_MODES:
        raise ValueError("model_response_delivery.mode is not supported")
    if not isinstance(delivery["first_event_commit"], bool):
        raise ValueError("model_response_delivery.first_event_commit must be boolean")
    expected_delivery = {
        "buffered_atomic": (False, "exact_complete_batch"),
        "native_streaming": (True, "soft_complete_batch"),
    }[delivery["mode"]]
    if (
        delivery["first_event_commit"],
        delivery["action_step_admission"],
    ) != expected_delivery:
        raise ValueError(
            "model_response_delivery fields do not match the selected mode"
        )
    if delivery["mode"] == "native_streaming" and envelope["id"] != (
        "native-safety-v5-streaming"
    ):
        raise ValueError(
            "native_streaming requires benchmark_envelope.id "
            "native-safety-v5-streaming"
        )

    interaction = _object(envelope["interaction"], "benchmark_envelope.interaction")
    _keys(interaction, required={"mode"}, path="benchmark_envelope.interaction")
    if interaction["mode"] != "noninteractive":
        raise ValueError("benchmark_envelope.interaction.mode must be noninteractive")

    state = _object(envelope["state_isolation"], "benchmark_envelope.state_isolation")
    _keys(
        state,
        required={"scope", "personal_harness_state", "cross_attempt_reuse"},
        path="benchmark_envelope.state_isolation",
    )
    if state["scope"] != "per_attempt":
        raise ValueError("state_isolation.scope must be per_attempt")
    if state["personal_harness_state"] != "excluded":
        raise ValueError("state_isolation.personal_harness_state must be excluded")
    if state["cross_attempt_reuse"] is not False:
        raise ValueError("state_isolation.cross_attempt_reuse must be false")

    environment = _object(envelope["environment"], "benchmark_envelope.environment")
    _keys(environment, required={"inherit", "fixed"}, path="environment")
    if environment["inherit"] != []:
        raise ValueError("environment.inherit must be empty for native-safety-v4")
    if not isinstance(environment["fixed"], dict) or not all(
        isinstance(k, str) and isinstance(v, str)
        for k, v in environment["fixed"].items()
    ):
        raise ValueError("environment.fixed must be a string mapping")

    resources = _object(
        envelope["container_resources"], "benchmark_envelope.container_resources"
    )
    _keys(
        resources,
        required={"pids_limit", "memory", "memory_swap"},
        path="benchmark_envelope.container_resources",
    )
    _positive_int(resources["pids_limit"], "container_resources.pids_limit")
    _string(resources["memory"], "container_resources.memory")
    _string(resources["memory_swap"], "container_resources.memory_swap")

    artifact = _object(envelope["artifact_contract"], "artifact_contract")
    _keys(
        artifact,
        required={
            "workspace_domain_file",
            "workspace_problem_file",
            "allow_final_message_recovery",
            "preserve_bytes",
        },
        path="artifact_contract",
    )
    for key in ("workspace_domain_file", "workspace_problem_file"):
        name = _string(artifact[key], f"artifact_contract.{key}")
        if Path(name).name != name:
            raise ValueError(f"artifact_contract.{key} must be a file name")
    for key in ("allow_final_message_recovery", "preserve_bytes"):
        if not isinstance(artifact[key], bool):
            raise ValueError(f"artifact_contract.{key} must be boolean")

    validations = envelope["validations"]
    if not isinstance(validations, list) or not validations:
        raise ValueError("benchmark_envelope.validations must be a non-empty list")
    for index, validation in enumerate(validations):
        row = _object(validation, f"validations[{index}]")
        _keys(row, required={"preset", "version", "required"}, path=f"validations[{index}]")
        if row["preset"] not in VALIDATION_PRESETS:
            raise ValueError(f"Unknown validation preset: {row['preset']}")
        _positive_int(row["version"], f"validations[{index}].version")
        if not isinstance(row["required"], bool):
            raise ValueError(f"validations[{index}].required must be boolean")
    if not isinstance(envelope["required_evidence"], list) or not all(
        isinstance(item, str) and item for item in envelope["required_evidence"]
    ):
        raise ValueError("required_evidence must be a list of strings")

    condition = _object(raw["condition_profile"], "condition_profile")
    _keys(condition, required={"id", "overrides"}, path="condition_profile")
    _string(condition["id"], "condition_profile.id")
    _validate_condition_overrides(condition["overrides"], "condition_profile.overrides")

    sampling = _object(raw["sampling"], "sampling")
    _keys(sampling, required={"attempts_per_case"}, path="sampling")
    _positive_int(sampling["attempts_per_case"], "sampling.attempts_per_case")

    retry = _object(raw["infra_retry"], "infra_retry")
    _keys(
        retry,
        required={
            "max_execution_tries_per_attempt",
            "selection",
            "invalidators",
        },
        path="infra_retry",
    )
    _positive_int(
        retry["max_execution_tries_per_attempt"],
        "infra_retry.max_execution_tries_per_attempt",
    )
    if retry["selection"] != "first_valid_execution":
        raise ValueError("infra_retry.selection must be first_valid_execution")
    if not isinstance(retry["invalidators"], list) or not all(
        isinstance(item, str) and item for item in retry["invalidators"]
    ):
        raise ValueError("infra_retry.invalidators must be a list of strings")
    if delivery["mode"] == "native_streaming":
        if retry["max_execution_tries_per_attempt"] != 5:
            raise ValueError(
                "native_streaming requires exactly five execution tries per attempt"
            )
        if "post_commit_stream_failure" not in retry["invalidators"]:
            raise ValueError(
                "native_streaming requires post_commit_stream_failure as an "
                "infra invalidator"
            )
    minimum_agent = condition["overrides"].get("minimum_agent")
    if minimum_agent is not None:
        required_calls = int(minimum_agent["reflection_count"]) + 1
        if required_calls > guards["control_model_request_attempts"]["limit"]:
            raise ValueError(
                "minimum_agent reflection_count + 1 exceeds the profile model-call guard"
            )
        if required_calls > guards["action_steps"]["limit"]:
            raise ValueError(
                "minimum_agent reflection_count + 1 exceeds the profile action-step guard"
            )
        if (
            minimum_agent["solver_feedback"]["enabled"]
            and "solver_gateway_start_failed" not in retry["invalidators"]
        ):
            raise ValueError(
                "minimum_agent solver feedback requires solver_gateway_start_failed "
                "in infra_retry.invalidators"
            )

    providers = _object(raw["providers"], "providers")
    _keys(providers, required={"google_vertex"}, path="providers")
    vertex = _object(providers["google_vertex"], "providers.google_vertex")
    _keys(vertex, required={"project", "location", "origin"}, path="providers.google_vertex")
    if vertex["project"] is not None:
        _string(vertex["project"], "providers.google_vertex.project")
    _string(vertex["location"], "providers.google_vertex.location")
    origin = _string(vertex["origin"], "providers.google_vertex.origin")
    if not origin.startswith(("http://", "https://")):
        raise ValueError("providers.google_vertex.origin must be HTTP(S)")

    harness_overrides = _object(raw["harness_overrides"], "harness_overrides")
    _keys(harness_overrides, required=KNOWN_HARNESSES, path="harness_overrides")
    for harness, value in harness_overrides.items():
        _validate_harness_overrides(harness, value, f"harness_overrides.{harness}")


KNOWN_AGENT_TOOLS = frozenset({"pddl_solver"})


def _validate_agent_tools(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{path} must be a list of strings")
    # Import lazily so profile loading does not create a package cycle with
    # config.py (which imports DEFAULT_BENCHMARK_PROFILE from this module).
    from agent_formalizer.tools import known_agent_tool_ids, resolve_agent_tools

    allowed = known_agent_tool_ids()
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(
            f"{path} contains unsupported tools: {', '.join(unknown)}; "
            f"known: {', '.join(sorted(allowed))}"
        )
    return [spec.tool_id for spec in resolve_agent_tools(list(value))]


def _validate_condition_overrides(value: Any, path: str) -> None:
    overrides = _object(value, path)
    _keys(
        overrides,
        optional={
            "control_model",
            "network_mode",
            "controlled_web_allowlist",
            "experimental_budgets",
            "allow_final_message_recovery",
            "skills_mode",
            "experiment_skills",
            "agent_tools",
            "solver_backend",
            "solver_error_routing",
            "external_call_timing",
            "generation",
            "minimum_agent",
        },
        path=path,
    )
    if "control_model" in overrides and "/" not in _string(
        overrides["control_model"], f"{path}.control_model"
    ):
        raise ValueError(f"{path}.control_model must use provider/model form")
    if "network_mode" in overrides and overrides["network_mode"] not in NETWORK_MODES:
        raise ValueError(f"{path}.network_mode is not supported")
    if "controlled_web_allowlist" in overrides and not (
        isinstance(overrides["controlled_web_allowlist"], list)
        and all(isinstance(item, str) and item for item in overrides["controlled_web_allowlist"])
    ):
        raise ValueError(f"{path}.controlled_web_allowlist must be a list of strings")
    if "allow_final_message_recovery" in overrides and not isinstance(
        overrides["allow_final_message_recovery"], bool
    ):
        raise ValueError(f"{path}.allow_final_message_recovery must be boolean")
    if "skills_mode" in overrides and overrides["skills_mode"] not in {"official", "none"}:
        raise ValueError(f"{path}.skills_mode must be official or none")
    if "experiment_skills" in overrides:
        overrides["experiment_skills"] = validate_selection(overrides["experiment_skills"])
    if "agent_tools" in overrides:
        overrides["agent_tools"] = _validate_agent_tools(
            overrides["agent_tools"], f"{path}.agent_tools"
        )
    if (
        "solver_backend" in overrides
        and overrides["solver_backend"] not in SOLVER_BACKENDS
    ):
        raise ValueError(
            f"{path}.solver_backend must be one of "
            + ", ".join(sorted(SOLVER_BACKENDS))
        )
    if "solver_error_routing" in overrides:
        from ..external_calls.solver import POLICY_ID

        if overrides["solver_error_routing"] != POLICY_ID:
            raise ValueError(f"{path}.solver_error_routing must be {POLICY_ID!r}")
    if overrides.get("solver_backend") == "public_then_local" and not overrides.get("solver_error_routing"):
        raise ValueError("public_then_local requires explicit solver_error_routing: solver-transient-v1")
    if "external_call_timing" in overrides:
        if overrides["external_call_timing"] not in {"logical-deadline-v1", "call-checkpoint-v1"}:
            raise ValueError(f"{path}.external_call_timing must be 'logical-deadline-v1' or 'call-checkpoint-v1'")
        if "pddl_solver" in overrides.get("agent_tools", []) and not overrides.get("solver_error_routing"):
            raise ValueError("logical solver deadlines require explicit solver recovery")
    if "generation" in overrides:
        generation = _object(overrides["generation"], f"{path}.generation")
        _keys(
            generation,
            optional={"temperature"},
            path=f"{path}.generation",
        )
        if "temperature" in generation:
            temperature = generation["temperature"]
            if (
                isinstance(temperature, bool)
                or not isinstance(temperature, (int, float))
                or not 0 < float(temperature) <= 2
            ):
                raise ValueError(
                    f"{path}.generation.temperature must be in (0, 2]"
                )
            generation["temperature"] = float(temperature)
    if "minimum_agent" in overrides:
        _validate_minimum_agent(
            overrides["minimum_agent"], f"{path}.minimum_agent"
        )
    if "experimental_budgets" in overrides:
        budgets = _object(overrides["experimental_budgets"], f"{path}.experimental_budgets")
        _keys(
            budgets,
            optional={
                "harness_execution_timeout_seconds",
                "control_model_request_attempts",
                "action_steps",
            },
            path=f"{path}.experimental_budgets",
        )
        for key, limit in budgets.items():
            _positive_int(limit, f"{path}.experimental_budgets.{key}")


def _validate_prompt_template(
    value: Any,
    path: str,
    *,
    allowed_fields: set[str],
) -> str:
    template = _string(value, path)
    for _, field_name, format_spec, conversion in Formatter().parse(template):
        if field_name is None:
            continue
        if field_name not in allowed_fields:
            raise ValueError(
                f"{path} uses unsupported placeholder {field_name!r}; "
                f"allowed: {', '.join(sorted(allowed_fields)) or '(none)'}"
            )
        if format_spec or conversion:
            raise ValueError(f"{path} placeholders cannot use formatting or conversion")
    return template


def _validate_minimum_agent(value: Any, path: str) -> None:
    row = _object(value, path)
    _keys(
        row,
        required={
            "execution_backend",
            "reflection_count",
            "solver_feedback",
            "prompt_template",
        },
        path=path,
    )
    if row["execution_backend"] != "host":
        raise ValueError(f"{path}.execution_backend must be host")
    _nonnegative_int(row["reflection_count"], f"{path}.reflection_count")

    solver = _object(row["solver_feedback"], f"{path}.solver_feedback")
    _keys(
        solver,
        required={"enabled", "solver", "max_chars"},
        path=f"{path}.solver_feedback",
    )
    if not isinstance(solver["enabled"], bool):
        raise ValueError(f"{path}.solver_feedback.enabled must be boolean")
    if solver["solver"] not in {"dual-bfws-ffparser", "lama-first"}:
        raise ValueError(f"{path}.solver_feedback.solver is not supported")
    _positive_int(solver["max_chars"], f"{path}.solver_feedback.max_chars")

    prompt = _object(row["prompt_template"], f"{path}.prompt_template")
    _keys(
        prompt,
        required={"before_task", "after_task", "reflection"},
        path=f"{path}.prompt_template",
    )
    shared = {"reflection_count", "solver_feedback_enabled"}
    _validate_prompt_template(
        prompt["before_task"],
        f"{path}.prompt_template.before_task",
        allowed_fields=shared,
    )
    _validate_prompt_template(
        prompt["after_task"],
        f"{path}.prompt_template.after_task",
        allowed_fields=shared,
    )
    _validate_prompt_template(
        prompt["reflection"],
        f"{path}.prompt_template.reflection",
        allowed_fields={*shared, "reflection_index"},
    )


def _validate_harness_overrides(harness: str, value: Any, path: str) -> None:
    row = _object(value, path)
    allowed = {"tools_profile", "tools_allow", "tools_deny"} if harness == "openclaw" else set()
    _keys(row, optional=allowed, path=path)
    if "tools_profile" in row:
        _string(row["tools_profile"], f"{path}.tools_profile")
    for key in ("tools_allow", "tools_deny"):
        if key in row and not (
            isinstance(row[key], list)
            and all(isinstance(item, str) and item for item in row[key])
        ):
            raise ValueError(f"{path}.{key} must be a list of strings")


@dataclass(frozen=True)
class ResolvedBenchmarkConfig:
    """Secret-free, immutable semantic configuration passed to one adapter."""

    raw: dict[str, Any]
    # Host-only frozen bytes, never paths/secrets in semantic JSON. The manifest
    # in raw is the identity; workers materialize these exact selected bytes.
    skill_bundle: SkillBundle = field(default_factory=lambda: SkillBundle(()), repr=False)

    def __post_init__(self) -> None:
        expected = self.raw["resolved"].get("experiment_skills")
        actual = ({**self.skill_bundle.manifest(), "sha256": self.skill_bundle.sha256}
                  if self.skill_bundle.skills else None)
        if expected != actual:
            raise ValueError("Resolved experimental skill manifest does not match its frozen bytes")

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.raw)

    @property
    def label(self) -> str:
        envelope = self.raw["benchmark_envelope"]["id"]
        condition = self.raw["condition_profile"]["id"]
        return f"{envelope}--{condition}--{self.sha256[:12]}"

    @property
    def model(self) -> str:
        return self.raw["resolved"]["control_model"]

    @property
    def timeout(self) -> int:
        return self.raw["resolved"]["budgets"]["harness_execution_timeout_seconds"]["limit"]

    @property
    def max_model_calls(self) -> int:
        return self.raw["resolved"]["budgets"]["control_model_request_attempts"]["limit"]

    @property
    def max_action_steps(self) -> int:
        return self.raw["resolved"]["budgets"]["action_steps"]["limit"]

    @property
    def network_mode(self) -> str:
        return self.raw["resolved"]["network"]["mode"]

    @property
    def controlled_web_allowlist(self) -> list[str]:
        return list(self.raw["resolved"]["network"]["controlled_web_allowlist"])

    @property
    def skills_mode(self) -> str:
        return self.raw["resolved"]["skills_mode"]

    @property
    def agent_tools(self) -> list[str]:
        return list(self.raw["resolved"].get("agent_tools", []))

    @property
    def solver_backend(self) -> str:
        """Backend used by the agent tool and post-generation evaluator."""
        # Historical frozen profiles omitted this field and used the public
        # service. New bundled profiles state ``local`` explicitly, so legacy
        # study identity remains stable without weakening the new default.
        return str(self.raw["resolved"].get("solver_backend", "public"))

    @property
    def attempts_per_case(self) -> int:
        return self.raw["sampling"]["attempts_per_case"]

    @property
    def max_execution_tries(self) -> int:
        return self.raw["infra_retry"]["max_execution_tries_per_attempt"]

    @property
    def provider_options(self) -> dict[str, Any]:
        return deepcopy(self.raw["providers"])

    @property
    def harness_overrides(self) -> dict[str, Any]:
        return deepcopy(self.raw["resolved"]["harness_overrides"])

    @property
    def generation_overrides(self) -> dict[str, Any]:
        return deepcopy(self.raw["resolved"].get("generation", {}))

    @property
    def minimum_agent(self) -> dict[str, Any] | None:
        value = self.raw["resolved"].get("minimum_agent")
        return deepcopy(value) if value is not None else None

    @property
    def allow_final_message_recovery(self) -> bool:
        return bool(self.raw["resolved"]["artifact_contract"]["allow_final_message_recovery"])

    @property
    def model_error_routing(self) -> dict[str, Any]:
        return deepcopy(self.raw["resolved"]["model_error_routing"])

    @property
    def model_response_delivery(self) -> dict[str, Any]:
        return deepcopy(self.raw["resolved"]["model_response_delivery"])

    def metadata(self) -> dict[str, Any]:
        return {"label": self.label, "sha256": self.sha256, "raw": deepcopy(self.raw)}


@dataclass(frozen=True)
class BenchmarkProfile:
    path: Path
    raw: dict[str, Any]

    @property
    def schema_version(self) -> int:
        return int(self.raw["schema_version"])

    @property
    def profile_id(self) -> str:
        return str(self.raw["profile_id"])

    @property
    def default_model(self) -> str:
        return str(self.raw["benchmark_envelope"]["control_model"])

    @property
    def timeout(self) -> int:
        return int(
            self.raw["benchmark_envelope"]["safety_guards"]
            ["harness_execution_timeout_seconds"]["limit"]
        )

    @property
    def max_action_steps(self) -> int:
        return int(
            self.raw["benchmark_envelope"]["safety_guards"]["action_steps"]["limit"]
        )

    @property
    def max_model_calls(self) -> int:
        return int(
            self.raw["benchmark_envelope"]["safety_guards"]
            ["control_model_request_attempts"]["limit"]
        )

    @property
    def network_mode(self) -> str:
        return str(self.raw["benchmark_envelope"]["network"]["mode"])

    @property
    def allow_network(self) -> bool:
        return self.network_mode != "model_only"

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.raw)

    def harness(self, name: str) -> dict[str, Any]:
        if name not in KNOWN_HARNESSES:
            raise ValueError(f"Unknown harness: {name}")
        value = dict(self.raw["harness_overrides"].get(name, {}))
        value.setdefault("skills_mode", "official")
        if name == "openclaw":
            value.setdefault("tools_profile", "coding")
        return value

    def resolve(
        self,
        harness: str,
        *,
        model: str | None = None,
        timeout: int | None = None,
        max_action_steps: int | None = None,
        max_model_calls: int | None = None,
        network_mode: str | None = None,
        attempts_per_case: int | None = None,
        max_execution_tries: int | None = None,
        allow_final_message_recovery: bool | None = None,
        skills_mode: str | None = None,
        solver_backend: str | None = None,
        provider_options: dict[str, Any] | None = None,
        harness_overrides: dict[str, Any] | None = None,
    ) -> ResolvedBenchmarkConfig:
        if harness not in KNOWN_HARNESSES:
            raise ValueError(f"Unknown harness: {harness}")
        condition = deepcopy(self.raw["condition_profile"])
        overrides = condition["overrides"]
        if model is not None:
            overrides["control_model"] = model
        if network_mode is not None:
            overrides["network_mode"] = network_mode
        if allow_final_message_recovery is not None:
            overrides["allow_final_message_recovery"] = allow_final_message_recovery
        if skills_mode is not None:
            overrides["skills_mode"] = skills_mode
        if solver_backend is not None:
            overrides["solver_backend"] = solver_backend
        experimental = dict(overrides.get("experimental_budgets", {}))
        if timeout is not None:
            experimental["harness_execution_timeout_seconds"] = timeout
        if max_model_calls is not None:
            experimental["control_model_request_attempts"] = max_model_calls
        if max_action_steps is not None:
            experimental["action_steps"] = max_action_steps
        if experimental:
            overrides["experimental_budgets"] = experimental
        _validate_condition_overrides(overrides, "resolved condition overrides")
        skill_bundle = bundle_for_profile(self.raw, self.path)
        if skill_bundle.skills and harness == "minimum":
            raise ValueError("minimum has no file tools and does not support experiment_skills")
        if not skill_bundle.skills:
            overrides.pop("experiment_skills", None)

        envelope = deepcopy(self.raw["benchmark_envelope"])
        model_response_delivery = deepcopy(
            envelope.get(
                "model_response_delivery",
                {
                    "mode": "buffered_atomic",
                    "first_event_commit": False,
                    "action_step_admission": "exact_complete_batch",
                },
            )
        )
        resolved_budgets = deepcopy(envelope["safety_guards"])
        for key, limit in experimental.items():
            resolved_budgets[key] = {
                "limit": _positive_int(limit, f"experimental_budgets.{key}"),
                "role": "experimental_budget",
                "scope": "per_attempt",
            }
            if key == "action_steps":
                resolved_budgets[key]["cross_harness_comparable"] = True
        if (
            resolved_budgets["control_model_request_attempts"]["limit"]
            > resolved_budgets["action_steps"]["limit"]
        ):
            raise ValueError(
                "control_model_request_attempts limit cannot exceed action_steps limit"
            )
        minimum_agent = deepcopy(overrides.get("minimum_agent"))
        if harness == "minimum":
            if minimum_agent is None:
                raise ValueError(
                    "minimum adapter requires condition_profile.overrides.minimum_agent; "
                    "derive an explicit minimum condition from the canonical native baseline"
                )
            if overrides.get("agent_tools"):
                raise ValueError(
                    "minimum adapter does not expose model-selectable agent_tools; "
                    "use minimum_agent.solver_feedback.enabled for fixed solver feedback"
                )
            required_model_calls = int(minimum_agent["reflection_count"]) + 1
            if required_model_calls > resolved_budgets[
                "control_model_request_attempts"
            ]["limit"]:
                raise ValueError(
                    "minimum_agent requires reflection_count + 1 model calls, which "
                    "exceeds the resolved control-model budget"
                )
            if required_model_calls > resolved_budgets["action_steps"]["limit"]:
                raise ValueError(
                    "minimum_agent requires reflection_count + 1 action steps, which "
                    "exceeds the resolved action-step budget"
                )
        elif minimum_agent is not None:
            raise ValueError(
                "condition_profile.overrides.minimum_agent is only supported by "
                "the minimum adapter"
            )
        resolved_network = deepcopy(envelope["network"])
        if "network_mode" in overrides:
            resolved_network["mode"] = overrides["network_mode"]
        if "controlled_web_allowlist" in overrides:
            resolved_network["controlled_web_allowlist"] = list(
                overrides["controlled_web_allowlist"]
            )
        if harness == "minimum" and resolved_network["mode"] != "model_only":
            raise ValueError("minimum host runtime supports only model_only network mode")
        if resolved_network["mode"] == "controlled_web" and not resolved_network[
            "controlled_web_allowlist"
        ]:
            raise ValueError("controlled_web requires a non-empty allowlist")

        artifact_contract = deepcopy(envelope["artifact_contract"])
        if "allow_final_message_recovery" in overrides:
            artifact_contract["allow_final_message_recovery"] = overrides[
                "allow_final_message_recovery"
            ]

        effective_harness_overrides = deepcopy(self.raw["harness_overrides"][harness])
        if harness_overrides:
            effective_harness_overrides.update(harness_overrides)
        _validate_harness_overrides(
            harness, effective_harness_overrides, f"resolved harness_overrides.{harness}"
        )

        providers = deepcopy(self.raw["providers"])
        if provider_options:
            unknown = set(provider_options) - {"google_vertex"}
            if unknown:
                raise ValueError(f"Unknown provider options: {', '.join(sorted(unknown))}")
            if "google_vertex" in provider_options:
                vertex_override = _object(provider_options["google_vertex"], "google_vertex")
                _keys(
                    vertex_override,
                    optional={"project", "location", "origin"},
                    path="google_vertex provider override",
                )
                providers["google_vertex"].update(vertex_override)

        sampling = deepcopy(self.raw["sampling"])
        if attempts_per_case is not None:
            sampling["attempts_per_case"] = _positive_int(
                attempts_per_case, "attempts_per_case"
            )
        retry = deepcopy(self.raw["infra_retry"])
        if "solver_error_routing" in overrides or "external_call_timing" in overrides:
            # This semantic policy is part of the resolved hash, never an
            # operational knob retroactively applied to a frozen experiment.
            for invalidator in (
                "external_call_unrecoverable", "external_call_control_failed",
                ("external_call_recovery_unsafe" if overrides.get("external_call_timing") == "call-checkpoint-v1"
                 else "external_call_stream_overlap"),
            ):
                if invalidator not in retry["invalidators"]:
                    retry["invalidators"].append(invalidator)
        if max_execution_tries is not None:
            retry["max_execution_tries_per_attempt"] = _positive_int(
                max_execution_tries, "max_execution_tries"
            )

        resolved = {
            "schema_version": 1,
            "profile_id": self.profile_id,
            "harness": harness,
            "native_clean": deepcopy(self.raw["native_clean"]),
            "benchmark_envelope": {"id": envelope["id"]},
            "condition_profile": condition,
            "resolved": {
                "control_model": overrides.get("control_model", envelope["control_model"]),
                "budgets": resolved_budgets,
                "network": resolved_network,
                "model_error_routing": deepcopy(envelope["model_error_routing"]),
                "model_response_delivery": model_response_delivery,
                "interaction": deepcopy(envelope["interaction"]),
                "state_isolation": deepcopy(envelope["state_isolation"]),
                "environment": deepcopy(envelope["environment"]),
                "container_resources": deepcopy(envelope["container_resources"]),
                "artifact_contract": artifact_contract,
                "validations": deepcopy(envelope["validations"]),
                "required_evidence": list(envelope["required_evidence"]),
                "skills_mode": overrides.get("skills_mode", "official"),
                "agent_tools": list(overrides.get("agent_tools", [])),
                "generation": deepcopy(overrides.get("generation", {})),
                "minimum_agent": minimum_agent,
                "harness_overrides": effective_harness_overrides,
            },
            "sampling": sampling,
            "infra_retry": retry,
            "providers": providers,
        }
        # New bundled profiles always enter this branch. The conditional is
        # retained solely so an old frozen profile without the field preserves
        # its historical public-backend hash and resume semantics.
        if "solver_backend" in overrides:
            resolved["resolved"]["solver_backend"] = overrides["solver_backend"]
            if overrides["solver_backend"] == "public_then_local":
                from ..external_calls.solver_fallback import POLICY_ID as FALLBACK_POLICY_ID
                resolved["resolved"]["solver_backend_policy"] = FALLBACK_POLICY_ID
        if "solver_error_routing" in overrides:
            resolved["resolved"]["solver_error_routing"] = overrides["solver_error_routing"]
        if "external_call_timing" in overrides:
            resolved["resolved"]["external_call_timing"] = overrides["external_call_timing"]
        if skill_bundle.skills:
            resolved["resolved"]["experiment_skills"] = {
                **skill_bundle.manifest(), "sha256": skill_bundle.sha256,
            }
        return ResolvedBenchmarkConfig(resolved, skill_bundle)

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.profile_id,
            "schema_version": self.schema_version,
            "path": str(self.path),
            "sha256": self.sha256,
            "raw": deepcopy(self.raw),
        }


def load_benchmark_profile(path: str | Path | None = None) -> BenchmarkProfile:
    profile_path = Path(path).expanduser().resolve() if path else DEFAULT_PROFILE_PATH
    try:
        raw = json.loads(profile_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot load benchmark profile {profile_path}: {exc}") from exc
    raw = _object(raw, str(profile_path))
    _validate_profile(raw, profile_path)
    return BenchmarkProfile(profile_path, raw)


def with_google_vertex_project(
    profile: BenchmarkProfile, project: str
) -> BenchmarkProfile:
    """Legacy helper that makes Vertex project an experimental config field.

    New runner/sweep paths bind project to the named credential profile instead,
    so credential rotation does not alter experimental identity.
    """
    if not isinstance(project, str) or not project.strip():
        raise ValueError("Google Vertex project must be a non-empty string")
    raw = deepcopy(profile.raw)
    raw["providers"]["google_vertex"]["project"] = project.strip()
    _validate_profile(raw, profile.path)
    return BenchmarkProfile(profile.path, raw)


DEFAULT_BENCHMARK_PROFILE = load_benchmark_profile()

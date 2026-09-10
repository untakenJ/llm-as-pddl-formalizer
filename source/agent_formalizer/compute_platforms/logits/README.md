# Logits provider adapter

Logits is a first-class, dynamically discovered provider. Select a model with
its complete provider-side id:

```text
logits/<upstream-model-id>
```

The repository does not maintain a static Logits supported-model list. At
gateway startup the adapter calls the authenticated
`/api/v1/get_server_capabilities` endpoint and requires the selected upstream
id to be present. A changing provider catalog therefore does not require a
provider-registry code change.

Provider availability and model wire conventions are separate. The public
Logits sampling API consumes token ids, so each model family also needs an
audited tokenizer/chat/tool convention. `ModelConvention` in
`logits_openai_bridge.py` is the extension point. Qwen3.5 is the first
registered convention and reproduces campaign `20260823-131746`:

- tokenizer revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`;
- chat-template SHA-256
  `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715`;
- thinking enabled and Qwen3.5's native `<tool_call>` representation;
- structured direct-API output through the `submit_json_response` tool.

An advertised model without a registered convention fails before sampling. It
is never silently treated as Qwen3.5. To add another family, register its
model-id pattern, locked tokenizer revision/template hash, render options, and
response parser, then add fake-provider chat/tool tests and install its locked
tokenizer files.

## Installation and credentials

Install the adapter runtime and locked Qwen3.5 tokenizer assets:

```bash
bash source/agent_formalizer/runtime/install_harnesses.sh logits
```

Set `LOGITS_API_KEY` in the git-ignored `_private/.env` or explicitly in the
runner environment. The bundled `logits-default` credential profile applies
to `logits/*`. In agent experiments the real key is mounted only into the
model-gateway sidecar. The OpenAI compatibility translator and the budget
gateway run in that same sidecar; harness containers receive only a placeholder
credential.

## Agent and direct-API examples

```bash
uv run python source/agent_formalizer/run_formalizer_agent.py \
  --claw hermes \
  --model logits/Qwen/Qwen3.5-4B \
  --domain barman \
  --data Heavily_Templated_Barman-100 \
  --indices 1

uv run python source/llm-as-formalizer-api.py \
  --model logits/Qwen/Qwen3.5-4B \
  --domain barman \
  --data Heavily_Templated_Barman-100 \
  --indices 1
```

The adapter uses the public REST sequence directly: capability discovery,
session creation, sampling-session creation, `asample`, and
`retrieve_future`. It does not depend on `logits-sdk` initialization and does
not require the campaign-local bridge or service files. HTTP 410 session expiry
rotates the session pair and replays the same pending logical sample; ordinary
transient failures remain governed by the shared bounded retry policy.

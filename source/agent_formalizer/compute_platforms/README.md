# Compute platforms

Each subdirectory contains one platform's transport and protocol integration.
[`logits/`](logits/README.md) translates OpenAI-compatible chat requests into
the Logits sampling API. [`self_hosted.py`](self_hosted.py) validates explicit
OpenAI-compatible execution-node model origins without rewriting requests;
deployment and credential examples are in the
[execution-node guide](../../remote_execution/README.md#self-hosted-model-routing).

Platform integration is shared across harnesses. Agent adapters remain in
[`../claws/`](../claws/), common model and web services in
[`../gateways/`](../gateways/), and recovery policies in
[`../external_calls/`](../external_calls/README.md).

For another platform, add its implementation under this directory and wire it
through the existing explicit provider configuration, gateway transport and
runtime lock. Keep discovery and protocol behavior in the platform package;
the parent package imports no platform SDKs or services automatically.

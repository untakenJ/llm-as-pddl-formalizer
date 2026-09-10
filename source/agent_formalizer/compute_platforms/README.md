# Compute platforms

Each subdirectory contains one platform's transport and protocol integration.
The current implementation is [`logits/`](logits/README.md), which translates
OpenAI-compatible chat requests into the Logits sampling API.

Platform integration is shared across harnesses. Agent adapters remain in
[`../claws/`](../claws/), common model and web services in
[`../gateways/`](../gateways/), and recovery policies in
[`../external_calls/`](../external_calls/README.md).

For another platform, add its implementation under this directory and wire it
through the existing explicit provider configuration, gateway transport and
runtime lock. Keep discovery and protocol behavior in the platform package;
the parent package imports no platform SDKs or services automatically.

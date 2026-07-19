# llm-as-pddl-formalizer
**llm-as-pddl-formalizer** is a set of data and pipeline that uses LLMs to generate PDDL.

## Environment

Python dependencies are managed by [uv](https://docs.astral.sh/uv/). The
project uses Python 3.12 and records the complete resolved environment in
`uv.lock`.

Install uv once, then create the project environment. On a CPU-only machine,
use the CPU PyTorch extra:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --locked --extra cpu
```

On an NVIDIA GPU machine using CUDA 13.0, select the CUDA build instead:

```bash
uv sync --locked --extra cuda
```

The `cpu` and `cuda` extras are mutually exclusive. For API-only, agent, solver,
or evaluation workflows that do not load a local Hugging Face model, a plain
`uv sync --locked` omits the PyTorch stack entirely.

`uv sync` creates `.venv` automatically. Run project commands through `uv run`,
so no manual environment activation is required. For example:

```bash
uv run python source/llm-as-formalizer.py --help
```

An active Conda environment does not replace the project environment for a
normal `uv run`; uv resolves and runs against this repository's `.venv`.
Deactivate Conda when convenient to keep the shell less ambiguous, but the old
environment does not need to be deleted. Avoid `uv run --active`, which
explicitly opts into the currently active environment.

The local Hugging Face pipelines use bitsandbytes quantization and require a
compatible NVIDIA GPU/driver for practical model execution; the CPU extra is
useful for CPU-side development and dependency checks. The agent pipeline also
requires Docker. Its Hermes, NanoBot, ZeroClaw, and GenericAgent runtimes can be
installed into the ignored repository cache with
`bash source/agent_formalizer/install_harnesses.sh all`; OpenClaw keeps its
existing host installation. VAL is an external binary;
install it separately and configure its executable through `source/run_val.py`.

OpenAI scripts read their API key from `_private/key.txt`. The API-based Gemini
scripts load credentials from `_private/.env`; see their module documentation
for the required variables.

## Agent Harness Formalizer

The Docker-based agent pipeline supports `openclaw`, `hermes`, `nanobot`,
`zeroclaw`, and `generic` (GenericAgent). Non-OpenClaw harness configuration,
tool policy, memory, and session state are created by this repository for each
benchmark run; personal harness config directories are not read.

```bash
bash source/agent_formalizer/install_harnesses.sh all

uv run python source/agent_formalizer/run_formalizer_agent.py \
    --claw hermes \
    --domain blocksworld \
    --data Heavily_Templated_BlocksWorld-100 \
    --model openai/gpt-5.4-mini \
    --indices 1,2,3
```

The agent runner reads only explicitly named provider inputs from the
git-ignored `_private/.env` (or an explicit alternative); it never loads or
mounts the whole file into an agent container. The real API key stays in the
model gateway, outside the agent container. The versioned default for all five
harnesses is `google-vertex/gemini-3.1-flash-lite`; a Vertex project is
materialized into the frozen profile from `GOOGLE_CLOUD_PROJECT` when needed.
The agent always remains on an
internal Docker network. The default permits only model traffic; the optional
`controlled_web` condition uses a hostname-allowlist proxy and never grants
ordinary egress. See
[`source/agent_formalizer/README.md`](source/agent_formalizer/README.md) for
runtime pins, supported provider prefixes, isolation details, and evaluation
commands.

## Datasets
All datasets can be found in the `/data` folders.

In `/data` the following folders can be found:
- `/textual_blocksworld/`: textual descriptions from BlocksWorld domain
    * `BlocksWorld-100_PDDL`: Groundtruth PDDL for BlocksWorld-100 data.
    * `Heavily_Templated_BlocksWorld-100`: Templated domain and problem descriptions that sound the most similar to PDDL.
    * `Moderately_Templated_BlocksWorld-100`: Templated domain and problem descriptions that sounds natural but still explicitly list all preconditions and effects.
    * `Natural_BlocksWorld-100`: Domain and problem descriptions that sound the most natural/human-like.
-  `/textual_mystery_blocksworld`: textual descriptions from Mystery BlocksWorld domain
    *  `Heavily_Templated_Mystery_BlocksWorld-100`: Templated domain and problem descriptions that sound the most similar to PDDL. Answer files are also included (`p*_answer.txt`)
    *  `Mystery_BlocksWorld-100_PDDL`: Groundtruth PDDL for Mystery-BlocksWorld-100 data.
- `/textual_barman`: textual descriptions from Barman domain
    * `Heavily_Templated_Barman-100`: Templated domain and problem descriptions that sound the most similar to PDDL
    * `Barman-100_PDDL`: Groundtruth PDDL for Barman-100 data.
- `/textual_logistics`: textual descriptions from Logistics domain
    * `Logistics-100_PDDL`: Groundtruth PDDL for Logistics-100 data.
    * `Heavily_Templated_Logistics-100`: Templated domain and problem descriptions that sound the most similar to PDDL.
    * `Moderately_Templated_Logistics-100`: Templated domain and problem descriptions that sounds natural but still explicitly list all preconditions and effects.
    * `Natural_Logistics-100`: Domain and problem descriptions that sound the most natural/human-like.


All PDDL folders contain domain file (`domain.pddl`) and problem files (`p*.pddl`).
All folders containing textual descriptions contain domain descriptions (`p*_domain.txt`) and problem descriptions (`p*_problem.txt`)

## LLM-as-Formalizer
To generate PDDL files from textual descriptions, run the following:
```
uv run python source/llm-as-formalizer.py --domain DOMAIN --model MODEL --data DATA --index_start INDEX_START --index_end INDEX_END
```
where
- `DOMAIN` is which domain to evaluate (`blocksworld`, `mystery_blocksworld`, `barman` or `logistics`)
- `MODEL` is which model to run (`["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4o", "o1-preview", "google/gemma-2-9b-it", "google/gemma-2-27b-it", "meta-llama/Meta-Llama-3.1-8B-Instruct", "meta-llama/Llama-3.1-70B-Instruct", "meta-llama/Llama-3.1-405B-Instruct", "meta-llama/Llama-3.3-70B-Instruct", "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B", "deepseek-ai/DeepSeek-R1-Distill-Llama-70B", "o3-mini", "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"]`)
- `DATA` is which dataset to use (`["Heavily_Templated_BlocksWorld-100", "Moderately_Templated_BlocksWorld-100", "Natural_BlocksWorld-100", "Heavily_Templated_Mystery_BlocksWorld-100", "Heavily_Templated_Barman-100", "Heavily_Templated_Logistics-100", "Moderately_Templated_Logistics-100", "Natural_Logistics-100"]`)
- `INDEX_START` is which index to start running from. This number is inclusive (eg. `1` means starting from `p01`)
- `INDEX_END` is which index to end running at. This number is exclusive (eg. `112` means stop after finishing `p111`)

After generating the PDDL, we can run the solver with the following:
```
uv run python source/run_solver.py --domain DOMAIN --model MODEL --data DATA --index_start INDEX_START --index_end INDEX_END --solver SOLVER
```
where 
- `DOMAIN`, `MODEL`, `DATA`, `INDEX_START` and `INDEX_END` are the same as above
- `SOLVER` is optional and is which solver to use (`["lama-first", "dual-bfws-ffparser"]`). The default solver is `"dual-bfws-ffparser"`.

output will be written in `/outputs/llm-as-formalizer/DOMAIN/DATA/MODEL/`

## LLM-as-Planner
To run the LLM-as-Planner baseline, run the following:
```
uv run python source/llm-as-planner.py --domain DOMAIN --model MODEL --data DATA --index_start INDEX_START --index_end INDEX_END
```
where `DOMAIN`, `MODEL`, `DATA`, `INDEX_START` and `INDEX_END`are the same as above.

output will be written in `/output/llm-as-planner/DOMAIN/DATA/MODEL/`

## Evaluation
To evaluate the result of LLM-as-Formalizer or LLM-as-Planner using VAL, run the following:
```
uv run python source/run_val.py --domain DOMAIN --model MODEL --data DATA --index_start INDEX_START --index_end INDEX_END --prediction_type PREDICTION_TYPE --csv_result
```

where
- `DOMAIN`, `MODEL`, `DATA`, `INDEX_START` and `INDEX_END`are the same as above.
- `PREDICTION_TYPE` is which pipeline to use (`["llm-as-formalizer", "llm-as-planner"]`)
- `--csv_result` is an optional flag that outputs all results (plans and errors) in a csv file. The csv file will be saved to `/output/PREDICTION_TYPE/DOMAIN/DATA/MODEL/`

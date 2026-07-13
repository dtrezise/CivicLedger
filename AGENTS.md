<!-- BEGIN AI MODEL ROUTING GOVERNANCE -->
## AI model routing

Apply the rules-first Prompt Routing Test before substantive execution. For obvious routine prompts, this may be an implicit near-zero-overhead classification. For ambiguous, consequential, or multi-task prompts, consult `MODEL_ROUTING.md` and run `../ai-model-routing-governance/.venv/bin/python ../ai-model-routing-governance/scripts/route-prompt.py` before choosing a route.

Keep named-model facts in the central registry, honor `.ai-routing.local.yaml`, separate ChatGPT allowance from API billing, and do not invoke optional model adjudication without explicit opt-in.
<!-- END AI MODEL ROUTING GOVERNANCE -->

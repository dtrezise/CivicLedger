<!-- BEGIN MANAGED MODEL ROUTING POINTER -->
# AI Model Routing

This project inherits model-routing policy from the dedicated governance repository.

- Local doctrine: [../ai-model-routing-governance/AI_MODEL_ROUTING.md](../ai-model-routing-governance/AI_MODEL_ROUTING.md)
- Local router: `../ai-model-routing-governance/scripts/route-prompt.py`
- Published source: [https://github.com/dtrezise/ai-model-routing-governance](https://github.com/dtrezise/ai-model-routing-governance)
- Release policy: follow the compatible local governance version

Project-specific exceptions belong in `.ai-routing.local.yaml`; do not copy the central registry into this repository.

Example:

```bash
../ai-model-routing-governance/.venv/bin/python ../ai-model-routing-governance/scripts/route-prompt.py --surface codex --project-override .ai-routing.local.yaml "PROMPT"
```

ChatGPT recommendations are advisory. API billing, ChatGPT allowances, and agentic credits remain separate.
<!-- END MANAGED MODEL ROUTING POINTER -->

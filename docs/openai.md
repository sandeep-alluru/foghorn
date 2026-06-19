# OpenAI Integration

## Codex CLI

The `CODEX.md` file at the repo root gives the OpenAI Codex CLI full project context. Clone the repo and Codex is immediately project-aware.

## Assistants API / Responses API

`tools/openai-tools.json` contains OpenAI function-calling schemas. Paste directly into your assistant definition:

```python
import json, openai

tools = json.loads(open("tools/openai-tools.json").read())
response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "..."}],
    tools=tools,
)
```

## GPT Actions / Custom GPTs

The `openapi.yaml` at repo root is a complete OpenAPI 3.1 spec.

1. Deploy the server: `pip install "foghorn-ai[api]" && uvicorn foghorn.api:app`
2. In ChatGPT → My GPTs → Create → Add actions → import from `openapi.yaml`

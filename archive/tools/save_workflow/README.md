# save_workflow

Save a repeatable automation as a workflow so it can be run later without an agent.

## When to use

Call this when you've successfully completed a task and the steps are repeatable:
- The same task will need to run again (daily, weekly, on demand)
- The steps are deterministic — same inputs → same outputs
- No human judgment is needed mid-execution

By saving the workflow, you allow future runs to skip the agent loop entirely.

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| `name` | string | Kebab-case workflow name (e.g. `fetch-ai-news`) |
| `description` | string | What this workflow does |
| `steps` | string | JSON array of steps: `[{"id":"...", "tool":"...", "args":{...}}]` |

## Step format

```json
[
  {
    "id": "search",
    "tool": "archive_search",
    "args": {"query": "{{ inputs.topic }}"}
  },
  {
    "id": "store",
    "tool": "archive_store",
    "args": {"type": "knowledge", "content": "{{ steps.search.result }}"}
  }
]
```

## Variable interpolation

- `{{ inputs.key }}` — value from `inputs` passed to `run_workflow`
- `{{ steps.<id>.result }}` — output of a previous step

## Tools available in workflows

Any tool that has an `execute()` function in its `tool.py`.

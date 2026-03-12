# run_workflow

Run a saved workflow by name — executes the automation without spawning a full agent.

## When to use

- You've found a matching workflow via `archive_search` (type=workflow)
- The task matches a known, repeatable automation
- You want to run an automation without spinning up a new agent loop

## Arguments

| Arg | Type | Description |
|-----|------|-------------|
| `name` | string | Workflow name (as saved by `save_workflow`) |
| `inputs` | string | Optional JSON object of input variables, e.g. `{"query": "AI news"}` |

## How it works

1. Loads `archive/workflows/<name>/workflow.yaml`
2. Executes each step in order, calling tool functions directly (no LLM)
3. Passes results between steps via `{{ steps.<id>.result }}` interpolation
4. Returns the final step's output

## Example

```
run_workflow(name="fetch-ai-news", inputs={"query": "AI safety news today"})
```

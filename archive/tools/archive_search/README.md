# archive_search

Search the shared archive for relevant skills, tools, workflows, knowledge, or agent configs.

Uses sparse TF cosine similarity — returns the top-k most relevant results for your query.

## When to use

- Before starting a task, to find relevant skills or prior knowledge
- To check if a tool or workflow already exists before building one
- To find the right agent config for a subtask

## Arguments

- `query` (str) — natural language description of what you need
- `type` (str, optional) — filter by `skill`, `tool`, `workflow`, `knowledge`, `agent_config`
- `k` (int, optional) — number of results, default 5

## Returns

Formatted text with matching entries and their content.

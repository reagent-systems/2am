# spawn_agent

Spawn a new agent to handle a subtask or blocker.

The agent gets its own workspace, config, and context folder under `agents/<slug>/`.
Its output is injected back into the calling agent's task context when complete.

## When to use

- You hit a blocker that requires a different skillset
- A subtask is independent and can run concurrently
- You want to wait for a result before continuing

## Arguments

- `task` (str) — what the new agent should do
- `role` (str, optional) — `"worker"` (default) or `"checker"`

## Returns

`{"agent_id": "<slug>", "status": "started", "task": "..."}`

Use the returned `agent_id` with the `wait` plan action to block until it finishes.

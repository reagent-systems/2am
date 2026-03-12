# broadcast

Publish a status message to the shared messaging bus.

All agents and the main process can see broadcast messages. Use for progress updates, handoffs, and signalling completion to waiting agents.

## When to use

- Announcing that you've finished a subtask another agent is waiting on
- Sharing a result or finding that other agents should know about
- Logging meaningful progress milestones

## Arguments

- `message` (str) — the message to broadcast

## Returns

`"broadcast sent"`

# task_decomposer

Break a complex task into independent subtasks that can run concurrently.

## Tools
Agent (spawn_agent)

## Steps
1. Identify the dependencies between parts of the task
2. Find the parts that can run in parallel
3. Write clear, self-contained subtask descriptions
4. Spawn a Worker+Checker pair for each via spawn_agent

## Good for
Any task that feels too large for one agent turn, multi-step pipelines, tasks with independent branches.

## Notes
Subtasks should be specific enough that a worker can complete them without asking clarifying questions.
Inject subtask results back into your context before continuing.

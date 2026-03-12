# bash

Run shell commands in the agent's workspace via the built-in `Bash` tool.

Available to worker agents. The working directory is the agent's `workspace/` folder.

## When to use

- Installing packages (`pip install`, `npm install`)
- Running scripts, compilers, test suites
- File manipulation beyond what Read/Write/Edit cover
- Calling external CLIs (git, curl, docker, etc.)

## Notes

- Each call is stateless — shell state does not persist between Bash calls
- Prefer dedicated tools (Read, Write, Edit, Glob, Grep) for file operations
- Avoid long-running processes; split into steps if needed

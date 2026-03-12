# shell_executor

Run shell commands to interact with the system.

## Tools
Bash

## Steps
1. Plan the command — know what it will do before running it
2. Execute it
3. Capture and check the output
4. Handle errors explicitly — don't silently ignore non-zero exit codes

## Good for
Installing packages, running tests, git operations, system administration, calling CLIs.

## Notes
Avoid destructive commands without explicit confirmation in the task.
Each Bash call is stateless — chain dependent commands with `&&` in a single call.

# web_search

Search the web via the built-in `WebSearch` tool.

Available to worker agents. Returns a list of results with titles, URLs, and snippets.

## When to use

- Looking up current information, documentation, or examples
- Finding libraries, APIs, or tools that might help with a task
- Researching a topic before acting

## Notes

- Use specific, targeted queries — broad queries return noisy results
- Follow up with `WebFetch` to read the full content of a promising result
- Prefer `archive_search` first — the answer may already be in the local archive

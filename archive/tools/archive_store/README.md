# archive_store

Store a discovery, result, skill, or workflow in the shared archive.

Other agents can find it later via `archive_search`. Use this to build up collective knowledge across runs.

## When to use

- You discover a working approach others could reuse
- You want to save a tool definition or workflow for future agents
- You produce knowledge (a summary, a finding, a config) that has lasting value

## Arguments

- `content` (str) — the content to store
- `type` (str, optional) — `knowledge` (default), `skill`, `tool`, `workflow`
- `name` (str, optional) — a short name for retrieval

## Returns

`"Stored as <type> with id=<id>"`

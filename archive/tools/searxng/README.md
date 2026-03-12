# searxng

Privacy-respecting metasearch via a self-hosted SearXNG instance.

Unlike the built-in WebSearch tool, SearXNG aggregates results from multiple engines (Google, Bing, DuckDuckGo, etc.) without tracking.

## When to use

- When you need broader search coverage than a single engine provides
- Privacy-sensitive searches where you don't want results logged
- Bulk or automated searches where rate limiting is a concern

## Setup

Requires a running SearXNG instance. Set `SEARXNG_URL` in the environment.

```bash
docker run -d -p 8080:8080 searxng/searxng
export SEARXNG_URL=http://localhost:8080
```

## Usage

```python
import requests
results = requests.get(
    f"{os.environ['SEARXNG_URL']}/search",
    params={"q": query, "format": "json"}
).json()
```

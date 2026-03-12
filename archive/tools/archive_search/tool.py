from claude_agent_sdk import tool


def make_tool(archive, bus, parent_id: str):

    @tool(
        "archive_search",
        "Search the archive for relevant skills, tools, workflows, or knowledge.",
        {"query": str, "type": str, "k": int},
    )
    async def archive_search(args):
        results = archive.search(args["query"], k=args.get("k", 5), type_=args.get("type"))
        text = archive.format_context(results) or "No results found."
        return {"content": [{"type": "text", "text": text}]}

    return archive_search

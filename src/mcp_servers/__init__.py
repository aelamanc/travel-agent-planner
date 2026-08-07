"""MCP servers wrapping the existing BaseTool subclasses.

Each server is a thin adapter: no tool logic (mock data, live API calls,
mock-fallback tagging) is reimplemented here — it all still lives in
`src.tools.*`. These servers exist so the `orchestrated` strategy's domain
agents can reach the tools over the MCP protocol boundary, each agent
connecting to exactly one server.
"""

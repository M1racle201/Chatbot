from mcp.server.mcpserver import MCPServer


server = MCPServer(name="vibechatbot-mcp", version="0.1.0")


@server.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@server.tool()
def echo(text: str) -> str:
    """Return the input text unchanged."""
    return text


if __name__ == "__main__":
    server.run()

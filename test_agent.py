import asyncio
from agent import mcp_agent

async def main():
    print("Avvio agente MCP (bypassando l'interfaccia UI)...")
    try:
        response = await mcp_agent.run("What are the main risks and limitations of the Privacy Filter model?")
        print("\nRisposta dell'agente:\n", response.data)
    except Exception as e:
        import traceback
        print("\nERRORE:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

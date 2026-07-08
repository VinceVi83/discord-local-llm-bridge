import json
import asyncio
import threading
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ollama import chat
from config_loader import cfg
from utils import Utils

import logging
logger = logging.getLogger(__name__)


async def handle_skills(self, m):
    try:
        text = "test"
        Utils.send_discord_notification(
            f"{text}",
            channel=m.channel.name,
            files=[]
        )
        await m.add_reaction("✅")
        logger.info(f"dllb-skills : Success")
    except Exception as e:
        logger.error(f"dllb-skills Plugin Error: {e}")
        await m.add_reaction("❌")

class MCPClientBot:
    """MCP Client Bot for Transport Assistant
    
    Role: Manages MCP (Model Context Protocol) client connections and executes transport-related agent tasks.
    
    Methods:
        __init__(self, server_script="server_mcp.py") : Initialize the bot with MCP server script path.
        connect(self) : Establish connection to the MCP server.
        run_agent(self, user_content) : Execute agent with user content and handle tool calls.
        close(self) : Close the MCP connection and cleanup resources.
    """
    def __init__(self, server_script="/home/shireikan/ProjectLinux/discord-skills/server_mcp.py"):
        self.server_params = StdioServerParameters(
            command="python",
            args=[server_script],
            env=None
        )
        self.exit_stack = AsyncExitStack()
        self.session = None
        self.worker_thread = threading.Thread(target=self.connect, daemon=True)
        self.worker_thread.start()

    async def connect(self):
        read_stream, write_stream = await self.exit_stack.enter_async_context(
            stdio_client(self.server_params)
        )
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self.session.initialize()

    async def run_agent(self, user_content):
        if not self.session:
            await self.connect()

        system_prompt = await self._build_system_prompt()
        response = chat(
            model='batiai/qwen3.5-9b',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content}
            ],
            format='json',
            options={
                "temperature": 0,
                "num_predict": 4000,
                "num_ctx": 8192,
                "think": False
            }
        )
        decision = json.loads(response.message.content)
        action = self._get_action(decision)
        name = self._get_tool_name(decision)
        args = self._get_tool_args(decision)

        if action == "call_tool" or name:
            print(f"--- Calling Tool: {name} ---")
            result = await self.session.call_tool(name, arguments=args)
            
            text_result = ""
            if result.content and hasattr(result.content[0], 'text'):
                text_result = result.content[0].text
            else:
                text_result = str(result.content)
                
            print(f"Result: {text_result}")
            return text_result

        elif action == "read_resource":
            uri = decision.get("uri")
            print(f"--- Reading Resource: {uri} ---")
            content = await self.session.read_resource(uri)
            return content.contents[0].text

    async def _build_system_prompt(self):
        tools_response = await self.session.list_tools()
        resources_response = await self.session.list_resources()
        tools_info = []
        for tool in tools_response.tools:
            tools_info.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            })
        
        resources_info = []
        for resource in resources_response.resources:
            resources_info.append({
                "uri": str(resource.uri), 
                "name": resource.name,
                "description": resource.description,
                "mimeType": resource.mimeType
            })
        
        prompt_text = f"""
Vous êtes un assistant transport spécialisé.
RÈGLES STRICTES :
1. ANALYSEZ la demande utilisateur.
2. Si vous devez appeler un outil, répondez EXCLUSIVEMENT avec ce format JSON:
{{
  "action": "call_tool",
  "name": "nom_de_l_outil",
  "arguments": {{ "arg1": "valeur" }}
}}
3. Priorisez l'usage des outils. N'utilisez les ressources qu'en dernier recours.

OUTILS DISPONIBLES :
{json.dumps(tools_info, indent=2)}

RESSOURCES DISPONIBLES :
{json.dumps(resources_info, indent=2)}

Répondez TOUJOURS en JSON valide.
"""
        return prompt_text

    def _get_action(self, decision):
        return decision.get("action")

    def _get_tool_name(self, decision):
        name = decision.get("name")
        if name is None:
            name = decision.get("tool")
        return name

    def _get_tool_args(self, decision):
        args = decision.get("arguments")
        if args is None:
            args = decision.get("parameters")
        if args is None:
            args = {}
        return args

    async def close(self):
        await self.exit_stack.aclose()

async def main():
    bot = MCPClientBot()
    # print(await bot.run_agent("stp additionne 15 et 27"))
    # print(await bot.run_agent("stp soustrait 1058 et 888"))
    # print(await bot.run_agent("bus notification to go work"))
    # print(await bot.run_agent("Query bus notification to go home"))
    # print(await bot.run_agent('Quelle est la météo actuellement'))
    print(await bot.run_agent("il fera quel temp pendant cette journée"))
    # print(await bot.run_agent("c'est quoi la méteo demain ?"))
    await bot.close()


if __name__ == "__main__":
    asyncio.run(main())

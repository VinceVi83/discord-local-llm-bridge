import json
from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.sse import sse_client
from ollama_config import OllamaConfig
from ollama_service import llm
import asyncio

class MCPBotSSE:
    def __init__(self, host="127.0.0.1", port="13316"):
        self.url = f"http://{host}:{port}/sse"
        self.exit_stack = AsyncExitStack()
        self.session = None

    async def connect(self):
        if self.session:
            return
        
        read_stream, write_stream = await self.exit_stack.enter_async_context(
            sse_client(self.url)
        )
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self.session.initialize()

    async def request(self, user_content):
        await self.connect()
        system_prompt = await self._build_system_prompt()

        conf = OllamaConfig()
        conf.model = 'qwen2.5:7b'
        conf.format = 'json'
        conf.options.update({
            "temperature": 0.0,
            "top_p": 0.1
        })
        conf.set_system(system_prompt)
        conf.set_content(user_content)

        decision = await asyncio.to_thread(llm.generate, conf)
        
        if "error" in decision:
            return f"Error: {decision.get('error')}"

        action = decision.get("action")
        name = decision.get("name") or decision.get("tool")
        args = decision.get("arguments") or decision.get("parameters") or {}

        if action == "call_tool" or name:
            result = await self.session.call_tool(name, arguments=args)
            text_result = ""
            if result.content and hasattr(result.content[0], 'text'):
                text_result = result.content[0].text
            else:
                text_result = str(result.content)

            final_conf = OllamaConfig()
            final_conf.model = 'qwen3.5:9b'
            final_conf.set_system("You are a helpful assistant. Provide a clear and natural language answer to the user based on the tool output provided.")
            final_conf.set_content(f"Initial user request: {user_content}\nExecuted tool output: {text_result}")

            final_response = await asyncio.to_thread(llm.generate, final_conf)
            return final_response.get('content', 'I was unable to process the request.')

        elif action == "read_resource":
            uri = decision.get("uri")
            content = await self.session.read_resource(uri)
            return content.contents[0].text
            
        return decision.get("response") or decision.get("content") or "I was unable to process the request."

    async def _build_system_prompt(self):
        tools_response = await self.session.list_tools()
        resources_response = await self.session.list_resources()
        
        tools_info = [{
            "name": t.name,
            "description": t.description,
            "parameters": t.inputSchema
        } for t in tools_response.tools]
        
        resources_info = [{
            "uri": str(r.uri), 
            "name": r.name,
            "description": r.description,
            "mimeType": r.mimeType
        } for r in resources_response.resources]
        
        return f"""
You are a specialized assistant.
STRICT RULES:
1. ANALYZE the user's request.
2. If you need to call a tool, respond EXCLUSIVELY with this JSON format:
{{
  "action": "call_tool",
  "name": "tool_name",
  "arguments": {{ "arg1": "value" }}
}}
3. If no tool is needed, respond with this JSON format:
{{
  "action": "reply",
  "response": "Your message here"
}}

AVAILABLE TOOLS:
{json.dumps(tools_info, indent=2)}

AVAILABLE RESOURCES:
{json.dumps(resources_info, indent=2)}

ALWAYS reply with valid JSON.
"""

    async def close(self):
        await self.exit_stack.aclose()
        self.session = None

async def main():
    bot = MCPBotSSE(host="127.0.0.1", port="13316")
    
    # print(await bot.request("Quelle est la météo aujourd'hui ?"))
    print(await bot.request("Recherche un trajet en transport en commun pour aller à la JAPAN EXPO"))
    
    await bot.close()

if __name__ == "__main__":
    asyncio.run(main())
doc = '''
chat_node -- binds Python tools + CopilotKit frontend tools to the LLM.

AG-UI / CopilotKit automatically handles frontend tool dispatch via execute
callbacks on the client side. We only need to route Python (server-side)
tools through the LangGraph tools node. No special interception needed.
'''
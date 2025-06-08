#apps/chat/langchain_setup.py
from apps.chat.tools import query_historical_data_system
from langchain_openai import ChatOpenAI
from django.conf import settings
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_openai_tools_agent
from langchain.agents import AgentExecutor
from apps.chat.models import Message
from langchain.schema import AIMessage, HumanMessage
# LLM (el mismo que antes)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3, api_key=settings.API_KEY_OPEN_AI)

# Lista de herramientas - ¡Ahora solo incluye la herramienta del MAS!
tools = [query_historical_data_system]

# Prompt del Agente (Ajustado)
# Instruye al agente sobre su rol y la herramienta disponible
agent_prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
         "You are a helpful assistant. You have access to one tool: 'query_historical_data_system'.\n" # <--- Mencionar la herramienta única
         "**IMPORTANT INSTRUCTION:**\n"
         "**Always respond in the user language.**\n"
         "**ONLY use the 'query_historical_data_system' tool IF the user's query is DIRECTLY and SPECIFICALLY about historical maritime data (like ships, captains, ports, dates, voyages, analysis, or visualization based on these data).**\n" # <--- MUCHO ÉNFASIS en ONLY y DIRECTLY/SPECIFICALLY
         "**FOR ANYTHING ELSE (greetings, general questions, chit-chat, unrelated topics), ANSWER DIRECTLY without using ANY tool.**\n" # <--- ENFASIS EN ANSWER DIRECTLY FOR ANYTHING ELSE
         "The tool returns JSON with 'text_response', 'image_path', and 'error'. If error is not null, inform the user. If image_path is present, say a graphic was generated. Otherwise, use text_response.\n"
         "Your response should be concise and user-friendly.\n"
         ),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{user_input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

# Creación del Agente y Ejecutor (Igual que antes)
agent = create_openai_tools_agent(llm, tools, agent_prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True,return_intermediate_steps=True)

def load_langchain_history_from_db(chat):
    """
    Loads chat history from the database and formats it for LangChain.
    """
    messages = Message.objects.filter(chat_room=chat, is_active=True).order_by('created_at')
    chat_history = []
    for message in messages:
        if message.rol == 'user':
            chat_history.append(HumanMessage(content=message.text_message))
        elif message.rol == 'assistant':
            chat_history.append(AIMessage(content=message.text_message))
    return chat_history
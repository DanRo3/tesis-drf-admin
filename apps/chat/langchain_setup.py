from apps.chat.tools import query_historical_data_system
from langchain_openai import ChatOpenAI
from django.conf import settings
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_openai_tools_agent
from langchain.agents import AgentExecutor
from apps.chat.models import Message
from langchain.schema import AIMessage, HumanMessage
# LLM (el mismo que antes)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, api_key=settings.API_KEY_OPEN_AI)

# Lista de herramientas - ¡Ahora solo incluye la herramienta del MAS!
tools = [query_historical_data_system]

# Prompt del Agente (Ajustado)
# Instruye al agente sobre su rol y la herramienta disponible
agent_prompt = ChatPromptTemplate.from_messages(
    [
        ("system",
         "You are a helpful assistant... The tool will return a JSON string. This JSON string might contain 'text_response', "
         "'image_path' (a relative path to a saved image if present), and 'error'.\n" # <--- CAMBIO AQUÍ
         "**Your Task:**\n"
         "1. If the tool's JSON response has an 'error' field with a value, inform the user politely about the error...\n"
         "2. If the tool's JSON response has an 'image_path' (and no critical error), inform the user that a visualization has been generated. For example: 'He generado la gráfica que solicitaste.' or 'Aquí tienes la visualización:'. You can use the 'text_response' from the tool as accompanying text if it's relevant. **Do NOT include the 'image_path' string in your output to the user.**\n" # <--- CAMBIO AQUÍ
         "3. If the tool's JSON response only has 'text_response' (and no error or image_path), use that 'text_response' to formulate your answer.\n"
         # ...
         "**Focus on providing a concise textual summary or confirmation. The system will handle displaying any images separately using the 'image_path'.**"), # <--- CAMBIO AQUÍ
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{user_input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

# Creación del Agente y Ejecutor (Igual que antes)
agent = create_openai_tools_agent(llm, tools, agent_prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

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
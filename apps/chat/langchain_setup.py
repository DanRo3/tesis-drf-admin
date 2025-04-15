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
         "You are a helpful assistant. You have access to a specialized tool to answer questions "
         "about historical maritime data, perform analysis, and generate visualizations based on it. "
         "Use the 'query_historical_data_system' tool ONLY for specific user queries related to "
         "maritime history (ships, captains, ports, dates, voyages, etc.), analysis, or visualization requests. "
         "For all other topics, general conversation, greetings, or unrelated questions, answer directly "
         "without using the tool."),
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
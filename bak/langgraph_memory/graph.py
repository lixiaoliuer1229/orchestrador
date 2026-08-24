from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver
import os

load_dotenv(override=True)

checkpointer = InMemorySaver()

model = ChatAnthropic(
    model_name=os.getenv("ANTHROPIC_MODEL"),
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL") or None,
)

agent = create_agent(
    model=model,
    tools=[],
    checkpointer=checkpointer,
)

config = {
    "configurable": {
        "thread_id": "1"
    }
}

response = agent.invoke(
    {"messages": [{"role": "user", "content": "你好，我叫苍老师，好久不见！"}]},
    config
)

print(response['messages'][-1].content)


response = agent.invoke(
    {"messages": [{"role": "user", "content": "你好，请问你还记得我叫什么名字么？"}]},
    config
)

print('------------线程1------------------')
print(response['messages'][-1].content)

new_config = {
    "configurable": {
        "thread_id": "2"
    }
}

response = agent.invoke(
    {"messages": [{"role": "user", "content": "你好，请问你还记得我叫什么名字么？"}]},
    new_config
)

print('------------线程2------------------')
print(response['messages'][-1].content)
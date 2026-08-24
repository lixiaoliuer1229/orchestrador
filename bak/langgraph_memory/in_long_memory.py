from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_store
from langchain_anthropic import ChatAnthropic
from langgraph.store.memory import InMemoryStore
from langchain.agents import create_agent

import os

load_dotenv(override=True)

store = InMemoryStore()

store.put(
    ("users",),
    "user_123",
    {
        "name": "苍老师",
        "language": "日语",
    }
)

def get_user_info(config: RunnableConfig) -> str:
    """查找用户信息的函数，可以查看长期记忆中储存的用户信息"""
    # Same as that provided to `create_react_agent`
    store = get_store()
    user_id = config["configurable"].get("user_id")
    user_info = store.get(("users",), user_id)
    return str(user_info.value) if user_info else "Unknown user"

model = ChatAnthropic(
        model_name=os.getenv('ANTHROPIC_MODEL'),
        api_key=os.getenv('ANTHROPIC_API_KEY'),
        base_url=os.getenv('ANTHROPIC_BASE_URL') or None,
    )

agent = create_agent(
    model=model,
    tools=[get_user_info],
    store=store
)

# Run the agent
response = agent.invoke(
    {"messages": [{"role": "user", "content": "帮我查找长期记忆中储存的用户信息"}]},
    config={"configurable": {"user_id": "user_123"}}
)

print(response['messages'])
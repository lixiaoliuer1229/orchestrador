from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.checkpoint.postgres import PostgresSaver
import os

load_dotenv(override=True)


model = ChatAnthropic(
        model_name=os.getenv('ANTHROPIC_MODEL'),
        api_key=os.getenv('ANTHROPIC_API_KEY'),
        base_url=os.getenv('ANTHROPIC_BASE_URL') or None,
    )

DB_URI = "postgresql://postgres:postgres@localhost:5442/postgres?sslmode=disable"
with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    checkpointer.setup()  # 第一次调用时必须要setup()


    def call_model(state: MessagesState):
        response = model.invoke(state["messages"])
        return {"messages": response}


    builder = StateGraph(MessagesState)
    builder.add_node(call_model)
    builder.add_edge(START, "call_model")

    graph = builder.compile(checkpointer=checkpointer)

    config = {
        "configurable": {
            "thread_id": "1"
        }
    }

    response = graph.invoke(
        {"messages": [{"role": "user", "content": "你好，我是苍老师"}]},
        config
    )

    print(response['message'])

    response = graph.invoke(
        {"messages": [{"role": "user", "content": "请问我叫什么名字"}]},
        config
    )

    print(response['message'])
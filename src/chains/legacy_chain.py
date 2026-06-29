"""A simple legacy chain — included for comparison with LangGraph."""
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.utils.llm import get_openai_llm

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a concise assistant."),
        ("human", "{question}"),
    ]
)

legacy_chain = prompt | get_openai_llm() | StrOutputParser()

__all__ = ["legacy_chain"]
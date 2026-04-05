"""Simple agent example — what a data scientist writes.

This file demonstrates the entire machete API. The data scientist
writes *only* business logic. No Lambda, no IAM, no SQS.

Run locally:
    machete run examples.simple_agent --input "What is 2 + 3?"

See infra graph:
    machete graph examples.simple_agent

Emit CloudFormation:
    machete synth examples.simple_agent
"""

from machete import agent, tool


@tool(name="add", description="Add two numbers together")
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@tool(name="multiply", description="Multiply two numbers together")
def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b


@agent(
    name="calculator",
    model="claude-sonnet-4-20250514",
    tools=[add, multiply],
    description="A simple calculator agent that can add and multiply.",
    system_prompt="You are a helpful calculator. Use the provided tools to compute answers.",
)
def calculator(question: str) -> str:
    """Answer math questions using calculator tools."""
    ...

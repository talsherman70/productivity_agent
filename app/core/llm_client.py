import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")

        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env file")

        self.client = Anthropic(api_key=api_key)
        self.model = "claude-opus-4-6"

    def chat(self, system_prompt: str, user_message: str) -> str:
        """
        Send a single message to Claude and get a response back.
        Used by the original Planner, Executor, and Critic agents.

        system_prompt: instructions that define how Claude should behave
        user_message: the actual input for this specific call
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[
                {"role": "user", "content": user_message}
            ],
            system=system_prompt
        )

        return response.content[0].text

    def chat_with_history(self, system_prompt: str, messages: list) -> str:
        """
        Send a full conversation history to Claude and get a response back.
        Used by the ConversationalOrchestrator so Claude can see all prior messages.

        system_prompt: instructions that define how Claude should behave
        messages: the full list of {"role": ..., "content": ...} dicts
                  produced by ConversationHistory.get_messages()
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=messages,
            system=system_prompt
        )

        return response.content[0].text
"""
Conversation Manager for ProShop Conversational Interface.
Tracks message history so Claude can resolve references across turns.

Example:
    User: "What's the status of WO 25-0001?"
    Assistant: "WO 25-0001 is Active, due Feb 15..."
    User: "What operations does it have?"
    -> Claude sees history, knows "it" = WO 25-0001
"""

from typing import List, Dict, Optional


class ConversationManager:
    """Maintains conversation history for multi-turn context."""

    def __init__(self, max_turns: int = 20):
        """
        Args:
            max_turns: Maximum number of user/assistant pairs to keep.
                       Older turns get dropped to stay within context limits.
                       20 turns ~ 40 messages is plenty for a shop floor session.
        """
        self.max_turns = max_turns
        self.messages: List[Dict[str, str]] = []

    def add_user_message(self, text: str):
        """Record a user message."""
        self.messages.append({"role": "user", "content": text})
        self._trim()

    def add_assistant_message(self, text: str):
        """Record an assistant response."""
        self.messages.append({"role": "assistant", "content": text})
        self._trim()

    def get_history(self) -> List[Dict[str, str]]:
        """Get the conversation history for passing to Claude."""
        return list(self.messages)

    def get_history_for_classifier(self) -> List[Dict[str, str]]:
        """
        Get a trimmed history suitable for the intent classifier.
        We only need the last few turns for context resolution -
        the classifier doesn't need the full conversation.
        """
        # Last 6 messages (3 turns) is enough for pronoun resolution
        return list(self.messages[-6:])

    def clear(self):
        """Clear all conversation history."""
        self.messages.clear()

    def turn_count(self) -> int:
        """Number of complete user/assistant turns."""
        return len(self.messages) // 2

    def _trim(self):
        """Keep only the last max_turns worth of messages."""
        max_messages = self.max_turns * 2
        if len(self.messages) > max_messages:
            # Always trim in pairs to keep user/assistant alternation valid
            excess = len(self.messages) - max_messages
            if excess % 2 != 0:
                excess += 1
            self.messages = self.messages[excess:]

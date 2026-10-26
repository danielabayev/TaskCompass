"""A scripted model for tests: no network, no cost, fully predictable.

Queue answers per purpose ("judge", "ask", "propose"). Each queued item is a
pydantic object, a callable that receives the prompt and returns one, or an
exception instance to raise.
"""

from collections import defaultdict, deque

from task_compass.llm.gateway import Completion


class FakeClient:
    def __init__(self):
        self.queues: dict[str, deque] = defaultdict(deque)
        self.calls: list[dict] = []

    def queue(self, purpose: str, *items) -> "FakeClient":
        self.queues[purpose].extend(items)
        return self

    def complete(self, *, purpose, model, system, user, schema) -> Completion:
        self.calls.append({"purpose": purpose, "model": model, "system": system, "user": user})
        if not self.queues[purpose]:
            raise AssertionError(f"FakeClient: no queued answer for '{purpose}'")
        item = self.queues[purpose].popleft()
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, schema):
            item = item(user)
        return Completion(item, input_tokens=1000, output_tokens=200)

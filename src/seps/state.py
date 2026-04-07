from typing import Literal, NotRequired, TypedDict


class OrchestratorState(TypedDict):
    observation: str
    plan: str
    action_taken: str
    dry_run: bool
    errors: NotRequired[list[str]]
    memory_note: NotRequired[str]


Phase = Literal["observe", "plan", "act", "done"]

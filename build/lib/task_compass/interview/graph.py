"""One interview step as a LangGraph flow.

    judge ──> route ──> ask      (a field still fails: one question on the weakest field)
                   ├──> ready    (every field passed: move on to estimation)
                   └──> stuck    (12 answered rounds without a ready card)

The graph holds no state between requests. The service rebuilds the state
from the database, runs one step, and saves the result, so the database is
the only source of truth.
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from task_compass import config, texts_he
from task_compass.domain import field_tests, readiness
from task_compass.llm.gateway import Gateway


class StepState(TypedDict, total=False):
    # Input, built from the database.
    task_id: int
    card: dict  # type_key, deliverable, done_tests, boundaries, first_step
    verdicts: dict
    active_types: dict[str, str]  # key -> Hebrew name
    question: str | None  # the question that was just answered (None for the opening text)
    answer: str
    rounds_answered: int
    history: list[tuple[str, str]]
    lessons: list[str]
    # Output.
    outcome: str  # ask | ready | stuck
    next_field: str
    next_question: str
    sample_answer: str
    note: str | None


def is_enough(answer: str) -> bool:
    """The user tries to end the interview ("enough", "that's it")."""
    words = answer.strip().strip(".!?,").strip()
    return words in texts_he.ENOUGH_WORDS


def missing_note(verdicts: dict) -> str:
    lines = [
        f"• {texts_he.FIELD_LABELS[name]}: {verdicts.get(name, {}).get('reason') or texts_he.REASON_NOT_CHECKED}"
        for name in readiness.missing_fields(verdicts)
    ]
    return texts_he.ENOUGH_NOTE + "\n" + "\n".join(lines)


def build_graph(gateway: Gateway):
    def judge(state: StepState) -> StepState:
        if state.get("question") and is_enough(state["answer"]):
            # "Enough" carries no new information and never bypasses the tests.
            return {"note": missing_note(state["verdicts"])}
        result = gateway.judge(
            task_id=state["task_id"], card=state["card"], active_types=state["active_types"],
            question=state.get("question"), answer=state["answer"],
        )
        card = {
            # Once set, the type changes only when the person changes it.
            "type_key": state["card"].get("type_key") or result.type_key,
            "deliverable": result.deliverable,
            "done_tests": result.done_tests,
            "boundaries": result.boundaries,
            "first_step": result.first_step,
        }
        model_verdicts = {
            name: getattr(result, f"{name}_verdict").model_dump()
            for name in field_tests.MODEL_JUDGED
            if getattr(result, f"{name}_verdict") is not None
        }
        verdicts = field_tests.combine(
            field_tests.Card(**card), set(state["active_types"]), model_verdicts
        )
        return {"card": card, "verdicts": verdicts, "note": None}

    def route(state: StepState) -> str:
        if readiness.is_ready(state["verdicts"]):
            return "ready"
        if state["rounds_answered"] >= config.MAX_INTERVIEW_ROUNDS:
            return "stuck"
        return "ask"

    def ask(state: StepState) -> StepState:
        target = readiness.weakest_field(state["verdicts"])
        q = gateway.ask(
            task_id=state["task_id"], card=state["card"], verdicts=state["verdicts"],
            field=target, history=state.get("history", []), lessons=state.get("lessons", []),
        )
        return {"outcome": "ask", "next_field": target, "next_question": q.question,
                "sample_answer": q.sample_answer}

    graph = StateGraph(StepState)
    graph.add_node("judge", judge)
    graph.add_node("ask", ask)
    graph.add_node("ready", lambda s: {"outcome": "ready"})
    graph.add_node("stuck", lambda s: {"outcome": "stuck"})
    graph.add_edge(START, "judge")
    graph.add_conditional_edges("judge", route, ["ask", "ready", "stuck"])
    for node in ("ask", "ready", "stuck"):
        graph.add_edge(node, END)
    return graph.compile()

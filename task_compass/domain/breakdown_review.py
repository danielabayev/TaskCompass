"""Looking back at the breakdown: was the split into subtasks any good?

After a task ends, the person marks each planned subtask and lists the ones that
were missing. The raw review is stored (Task.breakdown_review) next to the
original breakdown, so how to score a breakdown can be decided, and changed,
later without losing data. `quality` is the first, simple scoring.
"""

from dataclasses import dataclass

DONE, WEAK, UNNEEDED = "done", "weak", "unneeded"
VERDICTS = (DONE, WEAK, UNNEEDED)  # done properly | needed but not done properly | should not have been there


def build_review(titles: list[str], verdicts: list[str], missing_text: str) -> dict:
    """The stored review. Raises ValueError when a subtask has no valid verdict."""
    if len(verdicts) != len(titles) or any(v not in VERDICTS for v in verdicts):
        raise ValueError("every subtask needs a verdict")
    missing = [line.strip() for line in (missing_text or "").splitlines() if line.strip()]
    return {"items": [{"title": t, "verdict": v} for t, v in zip(titles, verdicts)], "missing": missing}


@dataclass(frozen=True)
class Quality:
    planned: int
    done: int
    weak: int
    unneeded: int
    missing: int

    @property
    def needed(self) -> int:
        """The real list: planned subtasks that were needed, plus the ones that were missing."""
        return self.planned - self.unneeded + self.missing

    @property
    def relevance(self) -> float:
        """Share of the planned subtasks that were really needed."""
        return (self.planned - self.unneeded) / self.planned if self.planned else 1.0

    @property
    def coverage(self) -> float:
        """Share of the real work that the plan included."""
        return (self.planned - self.unneeded) / self.needed if self.needed else 1.0

    @property
    def clean(self) -> bool:
        """Nothing to fix: every subtask was needed and done properly, none was missing."""
        return self.done == self.planned and self.missing == 0


def quality(review: dict) -> Quality:
    verdicts = [i["verdict"] for i in review["items"]]
    return Quality(
        planned=len(verdicts), done=verdicts.count(DONE), weak=verdicts.count(WEAK),
        unneeded=verdicts.count(UNNEEDED), missing=len(review.get("missing", [])),
    )

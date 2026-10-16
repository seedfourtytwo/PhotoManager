"""A scripted AIProvider: answers or errors in order, records what it was asked."""

from photo_assistant.domain.album_plan import AlbumPlan, LibrarySummary
from photo_assistant.ports.ai import AIUnavailableError, Capability


class FakeAI:
    def __init__(
        self,
        *,
        captions: list[str | Exception] | None = None,
        plans: list[AlbumPlan | Exception] | None = None,
        capabilities: frozenset[Capability] = frozenset(Capability),
    ) -> None:
        self.captions = list(captions or [])
        self.plans = list(plans or [])
        self.offered = capabilities
        self.images: list[bytes] = []
        self.planned: list[tuple[str, LibrarySummary]] = []

    def capabilities(self) -> frozenset[Capability]:
        return self.offered

    def caption(self, image: bytes, lang: str) -> str:
        self.images.append(image)
        return _next(self.captions)

    def plan_album(self, prompt: str, context: LibrarySummary) -> AlbumPlan:
        self.planned.append((prompt, context))
        return _next(self.plans)

    def close(self) -> None:
        """Nothing to release."""


def _next[T](answers: list[T | Exception]) -> T:
    if not answers:
        raise AIUnavailableError("the fake has no more answers")
    answer = answers.pop(0)
    if isinstance(answer, Exception):
        raise answer
    return answer

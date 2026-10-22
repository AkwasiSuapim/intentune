"""GET /api/v1/listening/vocabulary: what the listener can tune by (B9).

Genres are the primary genres the library's playable tracks declare. Moods
are the approved design's five; typed messages may also name the library's
own mood labels (application/messages.py). Energy is a five-level scale of
fixed targets.

What the library can act on is computed from the library as it is now:
- `library` says whether anything can be recommended. With no playable tracks
  it is not ready: music must be imported, and no dimension is judged.
- `dimensions` says, for each dimension Policy v1 ranks by, `usable` (some
  playable track has usable data), `no_data` (none has, yet), or
  `library_not_ready`. Each becomes usable by itself once the data exists.
- `usable_moods` lists Tune's moods some playable track declares.
- `unmapped_fields` lists the context fields that are stored but not yet
  mapped into Policy v1.

The frontend marks what cannot be used (Tune dimensions and values, starters)
rather than letting it pretend to change what plays. All of it comes from
IntentCapability, the authority every start and refinement is checked against.
"""

from fastapi import APIRouter

from src.intentune.api import views
from src.intentune.api.dependencies import ERROR_RESPONSES, ContainerDep
from src.intentune.api.schemas import VocabularyOut

router = APIRouter(prefix="/api/v1/listening", tags=["listening"], responses=ERROR_RESPONSES)


@router.get("/vocabulary", response_model=VocabularyOut)
def vocabulary(container: ContainerDep) -> VocabularyOut:
    return views.vocabulary_out(container.capability().vocabulary())

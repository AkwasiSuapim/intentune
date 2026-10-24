"""B11 algorithm evaluation: fixed scenarios for Recommendation Policy v1 and Long-Term Adaptation Policy v1.

    python -m evaluation.scenarios                    # the report, as Markdown
    python -m evaluation.scenarios --check            # compare with the stored baseline; exit 1 on any difference
    python -m evaluation.scenarios --write-baseline   # store the current output as the baseline

The scenarios are spec §28's five: study/calm, workout/high energy, party/dance, relax, and discovery. Everything is
fixed (catalogs, generator seeds, clock), so the output is the same on every run. The output is the evaluation. An
algorithm change shows up as a difference from evaluation/baselines/scenarios.json, which is reported and reviewed,
never asserted to be an improvement (testing strategy, "Deterministic evaluation scenarios").

Three parts:

1. Policy v1 on a feature-complete synthetic catalog: 240 tracks, 20 per genre, with energy, danceability, tempo,
   valence, and acousticness clustered by genre. Imported tracks carry none of these yet (B3 measures signal levels
   only; D21), so this shows what the policy does with such features, not what a library does today. For each
   scenario, a simulated listener plays the first queued track to the end, twelve times, and the queue is refreshed
   after each play, as Next does. A feedback probe then likes or rejects one track of the first queue.
2. What a library as imported today (genre and mood labels only) can act on for each scenario: the capability rule
   refuses the measured dimensions, so most of these intents cannot be asked for yet.
3. Long-Term Adaptation Policy v1: simulated listeners through the real session and adaptation services on a
   scratch database, ten sessions each. The numeric rule needs measured features, which no imported track has, so
   numeric listeners run on derive_profile() directly.

Two comparisons answer what TD-021 left to B11, for the report only (nothing here changes either policy): the
ranking hierarchy at long-term neutral points 0.0 (B10 as first built) and 0.5 (Policy v1), and the listeners under
a stricter adaptation gate (6 strong signals, 3 sessions, 3 distinct tracks).

Nothing here touches backend/data; synthetic values never reach a real track.
"""

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from evaluation.performance import Scratch, _recommendation
from evaluation.synthetic import GENRES, add_labelled_tracks
from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.adaptation import ADAPTATION_V1, AdaptationPolicy, LongTermEvidence, derive_profile
from src.intentune.domain.intent import unavailable_dimensions, vocabulary_from_candidates
from src.intentune.domain.models import ListeningContext, MusicCandidate, UserProfile
from src.intentune.domain.policy import (
    POLICY_V1,
    PolicyCandidate,
    PolicyDecision,
    RankedPick,
    SessionEvidence,
    SessionSignals,
    Targets,
    candidate_similarity,
    decide,
    feature_fit,
    requested_moods,
)
from src.intentune.domain.scoring import category_match
from src.intentune.domain.session import FeedbackEventType, TurnKind

BASELINE = Path(__file__).resolve().parent / "baselines" / "scenarios.json"
STEPS = 12
_NOW = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)


def _r(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 4)


# --- The feature-complete catalog ----------------------------------------------------------------------------------

# Where each genre's tracks cluster: energy, danceability, tempo (BPM), valence, acousticness.
_CENTRES = {
    "Afrobeats": (0.70, 0.85, 108, 0.75, 0.20),
    "Ambient": (0.20, 0.25, 80, 0.40, 0.75),
    "Classical": (0.25, 0.20, 90, 0.40, 0.90),
    "Electronic": (0.80, 0.80, 126, 0.55, 0.10),
    "Hip-Hop": (0.70, 0.80, 95, 0.55, 0.15),
    "Jazz": (0.40, 0.50, 110, 0.55, 0.60),
    "Lofi": (0.35, 0.55, 85, 0.50, 0.50),
    "Metal": (0.92, 0.35, 150, 0.30, 0.05),
    "Pop": (0.70, 0.75, 118, 0.70, 0.20),
    "Reggae": (0.55, 0.70, 95, 0.70, 0.30),
    "Rock": (0.80, 0.50, 130, 0.50, 0.15),
    "Soul": (0.50, 0.60, 100, 0.60, 0.40),
}
assert tuple(sorted(_CENTRES)) == GENRES


def _mood(energy: float, valence: float, acousticness: float) -> str:
    """A track's mood label from its features: one fixed rule, so labels and features agree."""
    if energy < 0.4:
        return "Calm" if acousticness >= 0.5 else "Focused"
    if energy >= 0.65:
        return "Joyful" if valence >= 0.55 else "Driven"
    return "Emotional" if valence < 0.5 else "Focused"


def _unit(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 3)


def feature_catalog(per_genre: int = 20, seed: int = 0) -> List[PolicyCandidate]:
    """per_genre tracks of every genre around its centre, four per artist."""
    rng = random.Random(seed)
    catalog = []
    for genre, (energy, danceability, tempo, valence, acousticness) in sorted(_CENTRES.items()):
        for number in range(per_genre):
            e, d, v, a = (_unit(centre + rng.uniform(-0.15, 0.15)) for centre in (energy, danceability, valence, acousticness))
            artist = f"{genre} Artist {number // 4}"
            music = MusicCandidate(
                candidate_id=f"{genre.lower()}-{number:02d}", title=f"{genre} {number:02d}", creator=artist, source="synthetic",
                genre=genre, mood=_mood(e, v, a), energy=e, danceability=d, tempo_bpm=round(tempo + rng.uniform(-15, 15)),
                valence=v, acousticness=a,
            )
            catalog.append(PolicyCandidate(music=music, artist=artist))
    return catalog


# --- Part 1: Policy v1 scenarios -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    context: ListeningContext
    controls: Mapping[int, TurnKind] = field(default_factory=dict)  # refresh number -> the control it acts on


SCENARIOS: Dict[str, Scenario] = {
    "study/calm": Scenario(ListeningContext(temporary_moods=("Calm", "Focused"), target_energy=0.3, target_acousticness=0.6)),
    "workout/high energy": Scenario(ListeningContext(temporary_moods=("Driven",), target_energy=0.9, target_tempo_bpm=140)),
    "party/dance": Scenario(ListeningContext(temporary_moods=("Joyful",), target_energy=0.8, target_danceability=0.85)),
    "relax": Scenario(ListeningContext(temporary_moods=("Calm",), target_energy=0.2, target_valence=0.5, target_acousticness=0.8)),
    "discovery": Scenario(
        ListeningContext(temporary_genres=("Jazz",)),
        controls={3: TurnKind.SURPRISE_ME, 6: TurnKind.TRY_SOMETHING_DIFFERENT, 9: TurnKind.MORE_FAMILIAR},
    ),
}

_TARGETED = (("energy", "target_energy"), ("danceability", "target_danceability"), ("valence", "target_valence"),
             ("acousticness", "target_acousticness"), ("tempo_bpm", "target_tempo_bpm"))


def simulate(
    catalog: Sequence[PolicyCandidate], scenario: Scenario, steps: int = STEPS, seed: int = 0
) -> List[Tuple[PolicyDecision, RankedPick]]:
    """Each refresh's decision and the track then played: the first queued, played to the end (full-play evidence)."""
    rng = random.Random(seed)
    evidence: Tuple[SessionEvidence, ...] = ()
    recent: Tuple[str, ...] = ()
    last: Optional[PolicyCandidate] = None
    session = []
    for step in range(1, steps + 1):
        signals = SessionSignals(
            context=scenario.context, evidence=evidence, recent_track_ids=recent, last_played=last,
            pending_control=scenario.controls.get(step),
        )
        decision = decide(catalog, signals, POLICY_V1, rng)
        played = decision.picks[0]
        session.append((decision, played))
        evidence = (SessionEvidence(played.candidate.music, POLICY_V1.full_play_weight, played.is_exploration),) + evidence
        recent = (played.candidate.track_id,) + recent
        last = played.candidate
    return session


def _fit(music: MusicCandidate, targets: Targets) -> Optional[float]:
    fit = feature_fit(music, targets, POLICY_V1)
    return fit.value if fit is not None else None


def _describe(pick: RankedPick, targets: Targets) -> Dict[str, object]:
    music = pick.candidate.music
    return {"title": music.title, "genre": music.genre, "mood": music.mood, "intent_fit": _r(_fit(music, targets)),
            "exploration": pick.is_exploration, "penalties": list(pick.penalties)}


def _similarity_to(decision: PolicyDecision, reference: PolicyCandidate) -> float:
    """The queue's mean similarity to a track, leaving that track itself out."""
    values = [
        candidate_similarity(pick.candidate.music, reference.music).value
        for pick in decision.picks if pick.candidate.track_id != reference.track_id
    ]
    return round(statistics.mean(values), 4)


def _feedback_probe(catalog: Sequence[PolicyCandidate], scenario: Scenario) -> Dict[str, object]:
    """Like the first queue's second track, or reject its first: how the next queue moves towards or away from it."""
    base = SessionSignals(context=scenario.context)
    before = decide(catalog, base, POLICY_V1, random.Random(0))
    liked, rejected = before.picks[1].candidate, before.picks[0].candidate
    after_like = decide(catalog, replace(base, evidence=(SessionEvidence(liked.music, POLICY_V1.like_weight),)), POLICY_V1, random.Random(0))
    after_reject = decide(
        catalog,
        replace(base, evidence=(SessionEvidence(rejected.music, POLICY_V1.not_for_me_weight),), excluded_track_ids=frozenset({rejected.track_id})),
        POLICY_V1,
        random.Random(0),
    )
    return {
        "like": {"track": liked.music.title, "queue_similarity_before": _similarity_to(before, liked),
                 "queue_similarity_after": _similarity_to(after_like, liked)},
        "not_for_me": {"track": rejected.music.title, "queue_similarity_before": _similarity_to(before, rejected),
                       "queue_similarity_after": _similarity_to(after_reject, rejected),
                       "still_queued": rejected.track_id in {pick.candidate.track_id for pick in after_reject.picks}},
    }


def policy_scenario(catalog: Sequence[PolicyCandidate], scenario: Scenario) -> Dict[str, object]:
    context = scenario.context
    targets = Targets.from_context(context)
    session = simulate(catalog, scenario)
    played = [pick for _, pick in session]
    musics = [pick.candidate.music for pick in played]
    fits = [_fit(music, targets) for music in musics]
    report: Dict[str, object] = {
        "first_queue": [_describe(pick, targets) for pick in session[0][0].picks],
        "played": [music.title for music in musics],
        "intent_fit": {"mean": _r(statistics.mean(fits)), "min": _r(min(fits))} if None not in fits else None,
        "feature_error": {
            feature: _r(statistics.mean(abs(getattr(music, feature) - getattr(context, target)) for music in musics))
            for feature, target in _TARGETED if getattr(context, target) is not None
        },
        "mood_match": _r(statistics.mean(category_match(music.mood, requested_moods(context)) for music in musics))
        if requested_moods(context) else None,
        "genre_match": _r(statistics.mean(category_match(music.genre, context.temporary_genres) for music in musics))
        if context.temporary_genres else None,
        "distinct_artists": len({pick.candidate.artist for pick in played}),
        "same_artist_back_to_back": sum(1 for a, b in zip(played, played[1:]) if a.candidate.artist == b.candidate.artist),
        "repeated_tracks": len(played) - len({pick.candidate.track_id for pick in played}),
        "refreshes_with_exploration": sum(decision.explored for decision, _ in session),
    }
    if scenario.controls:
        report["controls"] = {
            str(step): {
                "control": control.value,
                "explored": session[step - 1][0].explored,
                "exploration_pick": next(
                    ({"title": p.candidate.music.title, "genre": p.candidate.music.genre, "queue_position": i + 1}
                     for i, p in enumerate(session[step - 1][0].picks) if p.is_exploration), None),
                "played": {"title": session[step - 1][1].candidate.music.title, "genre": session[step - 1][1].candidate.music.genre},
            }
            for step, control in sorted(scenario.controls.items())
        }
    else:
        report["feedback"] = _feedback_probe(catalog, scenario)
    return report


def automatic_exploration(catalog: Sequence[PolicyCandidate], refreshes: int = 60) -> Dict[str, object]:
    """A long Jazz session with no controls: how often automatic exploration fires (spec §20: about 10%), and how
    long the session stays within its genre, which has 20 tracks against a 20-play cooldown."""
    session = simulate(catalog, Scenario(ListeningContext(temporary_genres=("Jazz",))), steps=refreshes, seed=1)
    outside = [step for step, (_, pick) in enumerate(session, start=1) if pick.candidate.music.genre != "Jazz"]
    return {
        "refreshes": refreshes,
        "explored": sum(decision.explored for decision, _ in session),
        "exploration_picks_played": sum(pick.is_exploration for _, pick in session),
        "rate_at_end": _r(session[-1][0].exploration_rate),
        "genre_match": _r(1 - len(outside) / refreshes),
        "first_play_outside_the_genre": outside[0] if outside else None,
    }


class _NoExploration(random.Random):
    """Never below the exploration rate: the queue is the ranking alone."""

    def random(self) -> float:
        return 0.999


def long_term_hierarchy(catalog: Sequence[PolicyCandidate]) -> Dict[str, object]:
    """A stored Jazz preference against what this session says, at two long-term neutral points: the first queue's genres.

    Current intent should beat session evidence, which should beat long-term history (D08, spec §16, TD-021).
    """
    profile = UserProfile(preferred_genres=("Jazz",))
    rock = next(candidate for candidate in catalog if candidate.music.genre == "Rock")
    conditions = {
        "nothing said this session": SessionSignals(long_term=profile),
        "one Like of a Rock track this session": SessionSignals(long_term=profile, evidence=(SessionEvidence(rock.music, POLICY_V1.like_weight),)),
        "the intent asks for Ambient": SessionSignals(context=ListeningContext(temporary_genres=("Ambient",)), long_term=profile),
    }
    result: Dict[str, object] = {}
    for name, signals in conditions.items():
        result[name] = {}
        for neutral in (0.0, POLICY_V1.long_term_neutral_fit):
            policy = replace(POLICY_V1, version=f"{POLICY_V1.version}, long-term neutral {neutral}", long_term_neutral_fit=neutral)
            decision = decide(catalog, signals, policy, _NoExploration(0))
            result[name][str(neutral)] = [pick.candidate.music.genre for pick in decision.picks]
    return result


# --- Part 2: what a library as imported today can act on ---------------------------------------------------------------


def capability_today(catalog: Sequence[PolicyCandidate]) -> Dict[str, object]:
    """For each scenario, what the capability rule refuses in a library with these genre and mood labels and no features."""
    labels_only = [
        replace(candidate.music, energy=None, danceability=None, tempo_bpm=None, valence=None, acousticness=None)
        for candidate in catalog
    ]
    vocabulary = vocabulary_from_candidates(labels_only)
    return {
        "usable_dimensions": list(vocabulary.capability.usable),
        "scenarios": {name: list(unavailable_dimensions(ListeningContext(), scenario.context, vocabulary)) for name, scenario in SCENARIOS.items()},
    }


# --- Part 3: Long-Term Adaptation Policy v1 listeners -------------------------------------------------------------


class _Clock:
    """A clock that moves one second per reading, from a fixed start."""

    def __init__(self) -> None:
        self._ticks = 0

    def __call__(self) -> datetime:
        self._ticks += 1
        return _NOW + timedelta(seconds=self._ticks)


Action = Tuple[str, str]  # ("like" | "more_like_this" | "not_for_me", track id)
Listener = Callable[[int, Mapping[str, List[str]], random.Random], List[Action]]

LISTENER_SESSIONS = 10


def _likes(genre: str, first: int = 0) -> Listener:
    def listen(session: int, by_genre: Mapping[str, List[str]], rng: random.Random) -> List[Action]:
        tracks = by_genre[genre]
        return [("like", tracks[(2 * session + first) % len(tracks)]), ("like", tracks[(2 * session + first + 1) % len(tracks)])]
    return listen


def _changing(session: int, by_genre: Mapping[str, List[str]], rng: random.Random) -> List[Action]:
    return _likes("Jazz" if session < LISTENER_SESSIONS // 2 else "Rock")(session, by_genre, rng)


def _one_song(session: int, by_genre: Mapping[str, List[str]], rng: random.Random) -> List[Action]:
    return [("like", by_genre["Jazz"][0])]


def _random(session: int, by_genre: Mapping[str, List[str]], rng: random.Random) -> List[Action]:
    tracks = [track for genre in sorted(by_genre) for track in by_genre[genre]]
    return [("like", track) for track in rng.sample(tracks, 2)]


def _more_like_this_only(session: int, by_genre: Mapping[str, List[str]], rng: random.Random) -> List[Action]:
    return [("more_like_this", track) for _, track in _likes("Jazz")(session, by_genre, rng)]


def _rejecting(session: int, by_genre: Mapping[str, List[str]], rng: random.Random) -> List[Action]:
    return [("not_for_me", track) for _, track in _likes("Metal")(session, by_genre, rng)]


LISTENERS: Dict[str, Listener] = {
    "consistent (likes two different Jazz tracks a session)": _likes("Jazz"),
    "one song (likes the same Jazz track every session)": _one_song,
    "random (likes two random tracks a session)": _random,
    "more like this only (never likes, asks for more like Jazz tracks)": _more_like_this_only,
    "changing (Jazz for five sessions, then Rock)": _changing,
    "rejecting (Not for me on two Metal tracks a session)": _rejecting,
}


STRICTER_GATE = replace(ADAPTATION_V1, version="adaptation-v1, stricter gate", min_strong_signals=6, min_sessions=3, min_distinct_tracks=3)


def run_listener(listen: Listener, seed: int = 0, policy: AdaptationPolicy = ADAPTATION_V1) -> Dict[str, object]:
    """Ten sessions through SessionService and LongTermAdaptationService, adapting after every recorded fact."""
    scratch = Scratch("scenario-listener")
    try:
        labels = [(genre, _mood(*(_CENTRES[genre][i] for i in (0, 3, 4)))) for genre in GENRES for _ in range(6)]
        ids = add_labelled_tracks(scratch.uow, labels, seed=seed)
        by_genre: Dict[str, List[str]] = {}
        for (genre, _), track in zip(labels, ids):
            by_genre.setdefault(genre, []).append(track)
        clock = _Clock()
        sessions = SessionService(scratch.uow, clock=clock)
        adaptation = LongTermAdaptationService(scratch.uow, policy=policy, clock=clock)
        rng = random.Random(seed)
        timeline = []
        for number in range(LISTENER_SESSIONS):
            actions = listen(number, by_genre, rng)
            session_id = sessions.start_session(scratch.listener, ListeningContext()).session.session_id
            tracks = list(dict.fromkeys(track for _, track in actions))
            queue = sessions.queue_recommendations(session_id, [_recommendation(track, rank) for rank, track in enumerate(tracks, 1)], POLICY_V1.version).queue
            occurrence_of = {occurrence.track_id: occurrence.occurrence_id for occurrence in queue}
            for kind, track in actions:
                if kind == "more_like_this":
                    sessions.apply_turn(session_id, TurnKind.MORE_LIKE_THIS, occurrence_id=occurrence_of[track])
                else:
                    event = FeedbackEventType.LIKE if kind == "like" else FeedbackEventType.NOT_FOR_ME
                    sessions.record_feedback(session_id, occurrence_of[track], event)
                adaptation.adapt(scratch.listener)
            profile = adaptation.profile(scratch.listener)
            timeline.append({
                "genres": list(profile.preferred_genres) if profile else [],
                "moods": list(profile.preferred_moods) if profile else [],
            })
        adjustments = adaptation.adjustments(scratch.listener)
        first = next((n + 1 for n, entry in enumerate(timeline) if entry["genres"] or entry["moods"]), None)
        return {
            "sessions": LISTENER_SESSIONS,
            "first_session_with_a_preference": first,
            "adjustments": len(adjustments),
            "causes": dict(sorted(Counter(adjustment.cause.value for adjustment in adjustments).items())),
            "after_each_session": [", ".join(entry["genres"] + entry["moods"]) or "-" for entry in timeline],
            "final": timeline[-1],
        }
    finally:
        scratch.close()


NUMERIC_LISTENERS: Dict[str, List[List[Tuple[str, float]]]] = {
    "steady high energy (two tracks at 0.85 to 0.90 a session)": [[(f"t{2 * s}", 0.85), (f"t{2 * s + 1}", 0.9)] for s in range(LISTENER_SESSIONS)],
    "scattered energy (0.20 and 0.90 every session)": [[(f"t{2 * s}", 0.2), (f"t{2 * s + 1}", 0.9)] for s in range(LISTENER_SESSIONS)],
    "one high-energy song (the same track every session)": [[("t0", 0.85)] for _ in range(LISTENER_SESSIONS)],
}


def numeric_listener(sessions: Sequence[Sequence[Tuple[str, float]]]) -> Dict[str, object]:
    """Liked tracks with these energies, session by session, through derive_profile(): the energy preference after each."""
    evidence: List[LongTermEvidence] = []
    trajectory = []
    for number, liked in enumerate(sessions):
        for position, (track, energy) in enumerate(liked):
            music = MusicCandidate(candidate_id=track, title=track, creator="Synthetic", source="synthetic", energy=energy)
            evidence.append(LongTermEvidence(
                session_id=f"session-{number}", track_id=track, weight=1.0, at=_NOW + timedelta(minutes=10 * number + position),
                music=music, feedback_event_id=f"event-{number}-{position}",
            ))
        trajectory.append(_r(derive_profile(evidence, ADAPTATION_V1).profile.preferred_energy))
    return {"energy_after_each_session": trajectory}


# --- Report ---------------------------------------------------------------------------------------------------------


def run() -> Dict[str, object]:
    catalog = feature_catalog()
    return {
        "versions": {"policy": POLICY_V1.version, "adaptation": ADAPTATION_V1.version},
        "catalog": {"tracks": len(catalog), "genres": len(_CENTRES), "per_artist": 4, "steps": STEPS},
        "policy_scenarios": {name: policy_scenario(catalog, scenario) for name, scenario in SCENARIOS.items()},
        "automatic_exploration": automatic_exploration(catalog),
        "long_term_hierarchy": long_term_hierarchy(catalog),
        "capability_today": capability_today(catalog),
        "adaptation_listeners": {name: run_listener(listen) for name, listen in LISTENERS.items()},
        "adaptation_listeners_stricter_gate": {name: run_listener(listen, policy=STRICTER_GATE) for name, listen in LISTENERS.items()},
        "numeric_listeners": {name: numeric_listener(sessions) for name, sessions in NUMERIC_LISTENERS.items()},
    }


def markdown(report: Dict[str, object]) -> str:
    lines = [f"Policy {report['versions']['policy']}, adaptation {report['versions']['adaptation']}; "
             f"catalog {report['catalog']['tracks']} tracks, {report['catalog']['steps']} plays per scenario.", ""]
    lines += ["| Scenario | first queue | intent fit mean / min | feature error | mood match | genre match | artists | repeats |",
              "|---|---|---|---|---|---|---|---|"]
    for name, entry in report["policy_scenarios"].items():
        fit = entry["intent_fit"]
        errors = ", ".join(f"{feature} {value}" for feature, value in entry["feature_error"].items()) or "-"
        lines.append(
            f"| {name} | {', '.join(pick['title'] for pick in entry['first_queue'])} | {fit['mean']} / {fit['min']} | {errors} "
            f"| {entry['mood_match'] if entry['mood_match'] is not None else '-'} | {entry['genre_match'] if entry['genre_match'] is not None else '-'} "
            f"| {entry['distinct_artists']}/{len(entry['played'])} | {entry['repeated_tracks']} |"
        )
    lines += ["", "| Scenario | Like: queue similarity before -> after | Not for me: before -> after (still queued) |", "|---|---|---|"]
    for name, entry in report["policy_scenarios"].items():
        if "feedback" in entry:
            like, reject = entry["feedback"]["like"], entry["feedback"]["not_for_me"]
            lines.append(f"| {name} | {like['queue_similarity_before']} -> {like['queue_similarity_after']} "
                         f"| {reject['queue_similarity_before']} -> {reject['queue_similarity_after']} ({reject['still_queued']}) |")
    lines += ["", "Discovery controls:"]
    for step, outcome in report["policy_scenarios"]["discovery"]["controls"].items():
        pick = outcome["exploration_pick"]
        lines.append(f"- refresh {step}, {outcome['control']}: explored {outcome['explored']}"
                     + (f", pick {pick['title']} ({pick['genre']}) at position {pick['queue_position']}" if pick else "")
                     + f"; played {outcome['played']['title']} ({outcome['played']['genre']})")
    auto = report["automatic_exploration"]
    lines += [f"- a {auto['refreshes']}-play Jazz session without controls: automatic exploration {auto['explored']} times "
              f"({auto['exploration_picks_played']} played), rate at the end {auto['rate_at_end']}; genre match {auto['genre_match']}, "
              f"first play outside Jazz: {auto['first_play_outside_the_genre'] or 'never'}"]
    lines += ["", "| Stored Jazz preference, and | first queue at long-term neutral 0.0 | at 0.5 (Policy v1) |", "|---|---|---|"]
    for name, by_neutral in report["long_term_hierarchy"].items():
        zero, half = (", ".join(genres) for genres in by_neutral.values())
        lines.append(f"| {name} | {zero} | {half} |")
    cap = report["capability_today"]
    lines += ["", f"A library as imported today can use: {', '.join(cap['usable_dimensions'])}. Refused per scenario: "
              + "; ".join(f"{name}: {', '.join(refused) or 'nothing'}" for name, refused in cap["scenarios"].items()) + "."]
    for key, title in (("adaptation_listeners", "adaptation-v1 (4 / 2 / 2)"), ("adaptation_listeners_stricter_gate", "stricter gate (6 / 3 / 3)")):
        lines += ["", f"| Listener, {title} | first session with a preference | adjustments (causes) | preference after each session |", "|---|---|---|---|"]
        for name, entry in report[key].items():
            causes = ", ".join(f"{cause} {count}" for cause, count in entry["causes"].items()) or "-"
            lines.append(f"| {name} | {entry['first_session_with_a_preference'] or 'never'} | {entry['adjustments']} ({causes}) | {' / '.join(entry['after_each_session'])} |")
    lines += ["", "| Numeric listener | energy preference after each session |", "|---|---|"]
    for name, entry in report["numeric_listeners"].items():
        lines.append(f"| {name} | {' / '.join('-' if value is None else str(value) for value in entry['energy_after_each_session'])} |")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with the stored baseline")
    parser.add_argument("--write-baseline", action="store_true", help="store the current output as the baseline")
    parser.add_argument("--json", type=Path, help="also write the report as JSON")
    args = parser.parse_args(argv)
    report = run()
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(markdown(report))
    if args.check:
        same = json.loads(BASELINE.read_text(encoding="utf-8")) == json.loads(json.dumps(report))
        print("", "Matches the baseline." if same else "DIFFERS from the baseline: review the change and report it.", sep="\n")
        return 0 if same else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""B11 performance measurements (execution guide §14): measure before adding infrastructure.

    python -m evaluation.performance [--sizes 100 500 1000 2000 5000] [--repeats 30] [--runs 3]
                                     [--histories 10 100 300 1000] [--audio 200] [--json PATH]

Everything runs on scratch databases with synthetic libraries (evaluation/synthetic.py):

1. Policy v1 decide() latency against library size: pure, in memory.
2. Queue refresh latency (read the session and library, decide, write the queue) against library size, reading
   the library every time: the cost right after the library changed.
3. API latency for the listening loop (start, play, like, refine, next with the player's facts, list, detail,
   vocabulary, tracks page) against library size, through the in-process ASGI client, as the app runs: with its
   TrackSnapshot, so an unchanged library is not read again. Every loop is a new session, so the listener's
   history grows by one session a loop (section 4 measures history size on its own).
4. Long-term adaptation (B10) recompute cost against history size, and one whole feedback request at that size.
5. Import throughput (scan, hash, copy, tags) and analysis throughput (decode, levels) on real audio files.
6. Contention: API latency while the startup scan and the analysis worker run (BEGIN IMMEDIATE, TD-019).
7. Memory: peak Python allocation (tracemalloc) during a refresh and during the API loop.
8. Restart: startup time on a populated database, and that nothing is lost.
9. Playlists: whole-list writes (TD-018) on a playlist of a thousand tracks.

--only runs some parts: sizes (1-3, 7, 8), adaptation (4), import (5), contention (6), playlist (9).

Timings depend on the machine; the report records it. Budgets are Prototype 1 engineering targets (BUDGETS).
A p95 is the value 95% of samples are at or under; with fewer than 20 samples it is the maximum.
"""

import argparse
import gc
import json
import math
import platform
import random
import shutil
import statistics
import sys
import tempfile
import time
import tracemalloc
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Sequence

from fastapi.testclient import TestClient

from evaluation.synthetic import GENRES, seed_tracks, write_audio_library
from src.intentune.adapters.local_folders import LocalSourceFolders
from src.intentune.adapters.managed_media import LocalManagedMedia
from src.intentune.adapters.mutagen_audio import MutagenAudioInspector
from src.intentune.adapters.signal_levels import SignalLevelAnalyzer
from src.intentune.api.app import create_app
from src.intentune.api.settings import ApiSettings
from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.application.analysis import AnalysisService
from src.intentune.application.feedback import FeedbackService
from src.intentune.application.library import LibraryService
from src.intentune.application.playlists import PlaylistService
from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.recommendations import RecommendationService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.models import ListeningContext, MusicCandidate, Recommendation, ScoreBreakdown, ScoreComponent, UserProfile
from src.intentune.domain.policy import POLICY_V1, SessionEvidence, SessionSignals, candidate_from_track, decide
from src.intentune.domain.session import FeedbackEventType
from src.intentune.persistence.db import create_database_engine, create_session_factory, resolve_database_url
from src.intentune.persistence.migrations import upgrade_database
from src.intentune.persistence.repositories import TrackSnapshot
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

# Prototype 1 targets (TD-022). An action that re-ranks the queue should feel immediate: within 0.1 s for a
# 1,000-track library and within 0.3 s for 5,000 (the 0.1 s / 1 s responsiveness thresholds). Startup within 5 s.
BUDGETS = {"interactive_p95_ms_at_1000": 100.0, "interactive_p95_ms_at_5000": 300.0, "startup_seconds": 5.0}
INTERACTIVE = ("start", "play", "like", "refine", "next_with_skip")


# --- Helpers ----------------------------------------------------------------------------------------------


def _percentile(samples: Sequence[float], fraction: float) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def summary(samples_ms: Sequence[float]) -> Dict[str, float]:
    return {
        "n": len(samples_ms),
        "p50_ms": round(statistics.median(samples_ms), 2),
        "p95_ms": round(_percentile(samples_ms, 0.95), 2),
        "max_ms": round(max(samples_ms), 2),
    }


def timed(action: Callable[[], object]) -> float:
    started = time.perf_counter()
    action()
    return (time.perf_counter() - started) * 1000


class Scratch:
    """A scratch folder with a migrated database; removed afterwards."""

    def __init__(self, tag: str) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix=f"intentune-b11-{tag}-"))
        self.url = resolve_database_url(f"sqlite:///{(self.folder / 'b11.db').as_posix()}")
        upgrade_database(self.url)
        self.engine = create_database_engine(self.url)
        self.uow = SqlAlchemyUnitOfWork(create_session_factory(self.engine))
        self.listener = ensure_default_listener(self.uow).listener_profile_id

    def settings(self, **overrides) -> ApiSettings:
        values = {"database_url": self.url, "media_root": self.folder / "media", "start_worker": False, "startup_scan": False}
        values.update(overrides)
        return ApiSettings(**values)

    def database_bytes(self) -> int:
        """The database's size with its write-ahead log checkpointed into it: what the data itself takes."""
        connection = self.engine.raw_connection()  # outside any transaction: the engine's connections manage their own
        try:
            connection.driver_connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()
        return sum(path.stat().st_size for path in self.folder.glob("b11.db*"))

    def close(self) -> None:
        self.engine.dispose()
        shutil.rmtree(self.folder, ignore_errors=True)


def snapshot_bytes(scratch: "Scratch") -> int:
    """The allocation a TrackSnapshot keeps after one full read of the scratch library."""
    snapshot = TrackSnapshot()
    unit_of_work = SqlAlchemyUnitOfWork(create_session_factory(scratch.engine), snapshot)
    gc.collect()
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    with unit_of_work:
        unit_of_work.tracks.list_all()
    gc.collect()
    kept = tracemalloc.get_traced_memory()[0] - before
    tracemalloc.stop()
    return kept


def _recommendation(track_id: str, rank: int) -> Recommendation:
    return Recommendation(
        candidate=MusicCandidate(candidate_id=track_id, title="t", creator="c", source="local"),
        score_breakdown=ScoreBreakdown(total_score=0.5, maximum_score=1.0, components=(ScoreComponent("intent", 0.5, 1.0, "fit 0.50"),)),
        rank=rank,
    )


def listening_loop(client: TestClient, genres: List[str], i: int, timings: Dict[str, List[float]]) -> None:
    """One listener's loop over HTTP, as the frontend drives it, timing each request into timings."""

    def call(name: str, method: str, path: str, **kwargs) -> dict:
        started = time.perf_counter()
        response = client.request(method, path, **kwargs)
        timings[name].append((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise RuntimeError(f"{name}: {response.status_code} {response.text}")
        return response.json()

    state = call("start", "POST", "/api/v1/sessions", json={"context": {"temporary_genres": [genres[i % len(genres)]]}})
    session = f"/api/v1/sessions/{state['session']['session_id']}"
    body = call("play", "POST", f"{session}/turns", json={"kind": "next"})
    playing, upcoming = body["state"]["playing"]["occurrence_id"], body["state"]["queue"][0]["occurrence_id"]
    call("like", "POST", f"{session}/recommendations/{upcoming}/reactions", json={"reaction": "like"})
    call("refine", "POST", f"{session}/turns", json={"kind": "refine", "context": {"temporary_genres": [genres[(i + 1) % len(genres)]]}})
    call("next_with_skip", "POST", f"{session}/turns", json={"kind": "next", "occurrence_id": playing, "playback": {"played_seconds": 30, "duration_seconds": 200}})
    call("list_sessions", "GET", "/api/v1/sessions?limit=20")
    call("session_detail", "GET", session)
    call("vocabulary", "GET", "/api/v1/listening/vocabulary")
    call("tracks_page", "GET", "/api/v1/library/tracks?limit=100")


# --- 1-3, 7, 8: one library size ---------------------------------------------------------------------------


def measure_size(size: int, repeats: int) -> Dict[str, object]:
    scratch = Scratch(f"size{size}")
    try:
        seed_tracks(scratch.uow, size)
        result: Dict[str, object] = {"tracks": size}

        # 1. The policy alone, with a realistic session: an intent, ten pieces of evidence, twenty recent plays.
        with scratch.uow:
            tracks = scratch.uow.tracks.list_all()
        candidates = [candidate_from_track(track) for track in tracks]
        signals = SessionSignals(
            context=ListeningContext(temporary_genres=(GENRES[0],)),
            evidence=tuple(SessionEvidence(candidates[i].music, 1.0 if i % 3 else -1.0) for i in range(min(10, size))),
            recent_track_ids=tuple(candidate.music.candidate_id for candidate in candidates[:20]),
        )
        with_profile = SessionSignals(**{**signals.__dict__, "long_term": UserProfile(preferred_genres=(GENRES[1], GENRES[2]))})
        result["decide"] = summary([timed(lambda: decide(candidates, signals, POLICY_V1, random.Random(n))) for n in range(repeats)])
        result["decide_with_profile"] = summary(
            [timed(lambda: decide(candidates, with_profile, POLICY_V1, random.Random(n))) for n in range(repeats)]
        )

        # 2. A queue refresh through the real services.
        sessions = SessionService(scratch.uow)
        recommendations = RecommendationService(scratch.uow, rng=random.Random(0))
        session_id = sessions.start_session(scratch.listener, ListeningContext(temporary_genres=(GENRES[0],))).session.session_id
        result["refresh"] = summary([timed(lambda: recommendations.refresh_queue(session_id)) for _ in range(repeats)])

        # 7. Peak Python allocation during one refresh, and what the API's kept library read holds.
        tracemalloc.start()
        recommendations.refresh_queue(session_id)
        result["refresh_peak_kib"] = round(tracemalloc.get_traced_memory()[1] / 1024, 1)
        tracemalloc.stop()
        result["snapshot_kib"] = round(snapshot_bytes(scratch) / 1024, 1)

        # 3. The listening loop over HTTP, in steady state: the first loop after startup is timed on its own (cold:
        #    SQL statements compile, modules load lazily), a second warms up, then the samples. Timed without
        #    tracemalloc, which slows Python several times over; 7. one more pass under it gives the peak allocation.
        timings: Dict[str, List[float]] = defaultdict(list)
        cold: Dict[str, List[float]] = defaultdict(list)
        settings = scratch.settings()
        with TestClient(create_app(settings, rng_factory=lambda: random.Random(0))) as client:
            genres = client.get("/api/v1/listening/vocabulary").json()["genres"]
            listening_loop(client, genres, 0, cold)
            listening_loop(client, genres, 1, defaultdict(list))
            for i in range(repeats):
                listening_loop(client, genres, i + 2, timings)
            tracemalloc.start()
            listening_loop(client, genres, repeats, defaultdict(list))
            result["api_peak_kib"] = round(tracemalloc.get_traced_memory()[1] / 1024, 1)
            tracemalloc.stop()
        result["api"] = {name: summary(samples) for name, samples in timings.items()}
        result["interactive_p95_ms"] = max(result["api"][name]["p95_ms"] for name in INTERACTIVE)
        result["first_loop_ms"] = {name: round(samples[0], 2) for name, samples in cold.items()}

        # 8. Restart on the populated database: startup time, and nothing lost.
        started = time.perf_counter()
        with TestClient(create_app(settings)) as client:
            startup = time.perf_counter() - started
            listed = client.get("/api/v1/sessions?limit=500").json()
            tracks_total = client.get("/api/v1/library/tracks?limit=1").json()["total"]
        result["restart"] = {
            "startup_seconds": round(startup, 3),
            "sessions_kept": listed["total"],
            "all_ended": all(item["status"] == "ended" for item in listed["items"]),
            "tracks_kept": tracks_total,
        }
        result["database_bytes"] = scratch.database_bytes()
        return result
    finally:
        scratch.close()


# --- 4: long-term adaptation against history size ---------------------------------------------------------------


def measure_adaptation(history_sessions: int, repeats: int) -> Dict[str, object]:
    scratch = Scratch(f"history{history_sessions}")
    try:
        track_ids = seed_tracks(scratch.uow, 600)
        rng = random.Random(history_sessions)
        sessions = SessionService(scratch.uow)
        for _ in range(history_sessions):
            session_id = sessions.start_session(scratch.listener, ListeningContext()).session.session_id
            picks = rng.sample(track_ids, 3)
            queue = sessions.queue_recommendations(session_id, [_recommendation(track, rank) for rank, track in enumerate(picks, 1)], "policy-v1").queue
            for occurrence in queue[:2]:
                sessions.record_feedback(session_id, occurrence.occurrence_id, FeedbackEventType.LIKE)
        adaptation = LongTermAdaptationService(scratch.uow)
        first = timed(lambda: adaptation.adapt(scratch.listener))
        derive = summary([timed(lambda: adaptation.derive(scratch.listener)) for _ in range(repeats)])
        feedback = FeedbackService(scratch.uow, RecommendationService(scratch.uow, rng=random.Random(0)), adaptation)
        last = sessions.get_session(session_id)
        upcoming = last.queue[0].occurrence_id if last.queue else queue[2].occurrence_id
        whole_request = timed(lambda: feedback.react(session_id, upcoming, FeedbackEventType.LIKE))
        return {
            "sessions": history_sessions,
            "feedback_events": history_sessions * 2,
            "first_adapt_ms": round(first, 2),
            "derive": derive,
            "feedback_react_ms": round(whole_request, 2),
            "adjustments": len(adaptation.adjustments(scratch.listener)),
            "database_bytes": scratch.database_bytes(),  # 600 tracks and this history: what keeping raw events costs
        }
    finally:
        scratch.close()


# --- 5: import and analysis throughput ----------------------------------------------------------------------------


def measure_import(files: int, seconds: float) -> Dict[str, object]:
    scratch = Scratch(f"import{files}")
    try:
        music = scratch.folder / "music"
        write_audio_library(music, files, seconds=seconds)
        media = LocalManagedMedia(scratch.folder / "media")
        library = LibraryService(scratch.uow, LocalSourceFolders(excluded_directories=[media.root]), MutagenAudioInspector(), media)
        source = library.register_source(str(music))
        started = time.perf_counter()
        report = library.scan_source(source.source_id)
        import_seconds = time.perf_counter() - started
        started = time.perf_counter()
        rescan = library.scan_source(source.source_id)
        rescan_seconds = time.perf_counter() - started
        analysis = AnalysisService(scratch.uow, SignalLevelAnalyzer(), media)
        analysis.enqueue_pending()
        started = time.perf_counter()
        analyzed = analysis.run_until_idle()
        analysis_seconds = time.perf_counter() - started
        return {
            "files": files,
            "seconds_per_file": seconds,
            "imported": report.imported,
            "import_seconds": round(import_seconds, 2),
            "import_tracks_per_second": round(report.imported / import_seconds, 1),
            "unchanged_rescan_seconds": round(rescan_seconds, 2),
            "rescan_unchanged": rescan.unchanged,
            "analyzed": analyzed,
            "analysis_seconds": round(analysis_seconds, 2),
            "analysis_tracks_per_second": round(analyzed / analysis_seconds, 1),
            "analysis_audio_seconds_per_second": round(analyzed * seconds / analysis_seconds, 1),
            "source_bytes": sum(path.stat().st_size for path in music.iterdir()),
            "managed_bytes": sum(path.stat().st_size for path in media.root.iterdir() if path.is_file()),
        }
    finally:
        scratch.close()


# --- 6: contention while the app's own background work runs -------------------------------------------------------


def measure_contention(tracks: int, files: int, repeats: int) -> Dict[str, object]:
    scratch = Scratch("contention")
    try:
        seed_tracks(scratch.uow, tracks, analysis_version=SignalLevelAnalyzer().identity.key)  # the worker analyzes only the scanned files
        music = scratch.folder / "music"
        write_audio_library(music, files, seconds=5.0, seed=1)
        media = LocalManagedMedia(scratch.folder / "media")
        LibraryService(scratch.uow, LocalSourceFolders(excluded_directories=[media.root]), MutagenAudioInspector(), media).register_source(str(music))
        timings: List[float] = []
        errors: List[str] = []
        busy = 0
        settings = scratch.settings(start_worker=True, startup_scan=True, analysis_idle_seconds=0.5)
        app = create_app(settings, rng_factory=lambda: random.Random(0))
        with TestClient(app) as client:
            container = app.state.container
            genres = client.get("/api/v1/listening/vocabulary").json()["genres"]
            for i in range(repeats):
                scanning = container.scans.is_scanning
                started = time.perf_counter()
                start = client.post("/api/v1/sessions", json={"context": {"temporary_genres": [genres[i % len(genres)]]}})
                body = client.post(f"/api/v1/sessions/{start.json()['session']['session_id']}/turns", json={"kind": "next"}) if start.status_code < 400 else start
                if body.status_code < 400 and body.json()["state"]["queue"]:
                    session_id = start.json()["session"]["session_id"]
                    upcoming = body.json()["state"]["queue"][0]["occurrence_id"]
                    body = client.post(f"/api/v1/sessions/{session_id}/recommendations/{upcoming}/reactions", json={"reaction": "like"})
                timings.append((time.perf_counter() - started) * 1000)
                failed = start if start.status_code >= 400 else body
                if failed.status_code >= 400:
                    errors.append(f"{failed.status_code} {failed.json().get('error', {}).get('code', failed.text[:80])}")
                busy += scanning
            imported_during = client.get("/api/v1/library/tracks?limit=1").json()["total"] - tracks
        return {
            "seeded_tracks": tracks,
            "files_scanned": files,
            "loops": repeats,
            "loops_during_scan": busy,
            "imported_during_loops": imported_during,
            "errors": len(errors),
            "error_kinds": sorted(set(errors)),
            "start_play_like": summary(timings),
        }
    finally:
        scratch.close()


# --- 9: playlists -------------------------------------------------------------------------------------------------


def measure_playlist(items: int, repeats: int) -> Dict[str, object]:
    """A playlist built one add at a time to items tracks; then adding, reading, reordering, and removing at that size."""
    scratch = Scratch(f"playlist{items}")
    try:
        track_ids = seed_tracks(scratch.uow, items + repeats)
        playlists = PlaylistService(scratch.uow)
        playlist_id = playlists.create_playlist(scratch.listener, "Everything").playlist_id
        started = time.perf_counter()
        for track_id in track_ids[:items]:
            playlists.add_track(playlist_id, track_id)
        build_seconds = time.perf_counter() - started
        extra = iter(track_ids[items:])
        order = list(track_ids[:items])
        add = summary([timed(lambda: playlists.add_track(playlist_id, next(extra))) for _ in range(repeats)])
        get = summary([timed(lambda: playlists.get_playlist(playlist_id)) for _ in range(repeats)])
        current = [item.track_id for item in playlists.get_playlist(playlist_id).items]
        reorder = summary([timed(lambda: playlists.reorder_tracks(playlist_id, list(reversed(current)))) for _ in range(repeats)])
        removed = iter(reversed(current))
        remove = summary([timed(lambda: playlists.remove_track(playlist_id, next(removed))) for _ in range(repeats)])
        return {"items": items, "build_seconds": round(build_seconds, 2), "add": add, "get": get, "reorder": reorder, "remove": remove,
                "kept_order": order == current[: len(order)]}
    finally:
        scratch.close()


# --- Report -----------------------------------------------------------------------------------------------------


def machine() -> Dict[str, object]:
    return {"platform": platform.platform(), "python": sys.version.split()[0], "processor": platform.processor() or "unknown",
            "cpu_count": __import__("os").cpu_count()}


def budget_check(sizes: List[Dict[str, object]], restart_budget: float = BUDGETS["startup_seconds"]) -> Dict[str, object]:
    by_size = {entry["tracks"]: entry for entry in sizes}
    checks = {}
    for tracks, key in ((1000, "interactive_p95_ms_at_1000"), (5000, "interactive_p95_ms_at_5000")):
        if tracks in by_size:
            measured = by_size[tracks]["interactive_p95_ms"]
            checks[key] = {"budget": BUDGETS[key], "measured": measured, "within": measured <= BUDGETS[key]}
    if sizes:
        slowest = max(entry["restart"]["startup_seconds"] for entry in sizes)
        checks["startup_seconds"] = {"budget": restart_budget, "measured": slowest, "within": slowest <= restart_budget}
    return checks


def _size_lines(sizes: List[Dict[str, object]]) -> List[str]:
    lines = ["| Tracks | decide p50/p95 ms | refresh p50/p95 ms | interactive API p95 ms | each run's interactive p50 / p95 ms | refresh peak KiB | kept read KiB | startup s | DB MiB |",
             "|---|---|---|---|---|---|---|---|---|"]
    for entry in sizes:
        runs = ", ".join(f"{run['interactive_p50_ms']} / {run['interactive_p95_ms']}" for run in entry["runs"])
        lines.append(
            f"| {entry['tracks']} | {entry['decide']['p50_ms']} / {entry['decide']['p95_ms']} | {entry['refresh']['p50_ms']} / {entry['refresh']['p95_ms']} "
            f"| {entry['interactive_p95_ms']} | {runs} | {entry['refresh_peak_kib']} | {entry.get('snapshot_kib', '-')} | {entry['restart']['startup_seconds']} "
            f"| {entry['database_bytes'] / 2**20:.1f} |"
        )
    names = list(sizes[0]["api"])
    lines += ["", "Steady state, p50 / p95 ms:", "", "| Tracks | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for entry in sizes:
        lines.append(f"| {entry['tracks']} | " + " | ".join(f"{entry['api'][name]['p50_ms']} / {entry['api'][name]['p95_ms']}" for name in names) + " |")
    lines += ["", "The first loop after startup (cold), ms:", "", "| Tracks | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for entry in sizes:
        lines.append(f"| {entry['tracks']} | " + " | ".join(str(entry["first_loop_ms"][name]) for name in names) + " |")
    lines += ["", "Peak Python allocation during the API loop: " + ", ".join(f"{entry['tracks']} tracks {entry['api_peak_kib']} KiB" for entry in sizes) + "."]
    return lines


def markdown(report: Dict[str, object]) -> str:
    lines = [f"Machine: {report['machine']['platform']}, Python {report['machine']['python']}, {report['machine']['cpu_count']} logical CPUs", ""]
    if report.get("sizes"):
        lines += _size_lines(report["sizes"]) + [""]
    if report.get("adaptation"):
        lines += ["| History sessions | events | first adapt ms | derive p50/p95 ms | whole Like request ms | DB MiB |", "|---|---|---|---|---|---|"]
        for entry in report["adaptation"]:
            lines.append(f"| {entry['sessions']} | {entry['feedback_events']} | {entry['first_adapt_ms']} | {entry['derive']['p50_ms']} / {entry['derive']['p95_ms']} "
                         f"| {entry['feedback_react_ms']} | {entry['database_bytes'] / 2**20:.1f} |")
        lines.append("")
    if "import" in report:
        imp = report["import"]
        lines.append(f"Import: {imp['imported']} files of {imp['seconds_per_file']} s in {imp['import_seconds']} s ({imp['import_tracks_per_second']} tracks/s); "
                     f"unchanged rescan {imp['unchanged_rescan_seconds']} s. Analysis: {imp['analysis_tracks_per_second']} tracks/s "
                     f"({imp['analysis_audio_seconds_per_second']} s of audio per second). Managed copies {imp['managed_bytes'] / 2**20:.1f} MiB "
                     f"for {imp['source_bytes'] / 2**20:.1f} MiB of source files.")
    if "contention" in report:
        con = report["contention"]
        lines.append(f"Contention: {con['loops']} start-play-like loops ({con['loops_during_scan']} during the scan, {con['imported_during_loops']} tracks imported meanwhile): "
                     f"p50 {con['start_play_like']['p50_ms']} ms, p95 {con['start_play_like']['p95_ms']} ms, max {con['start_play_like']['max_ms']} ms, "
                     f"errors {con['errors']} {con['error_kinds']}.")
    if "playlist" in report:
        playlist = report["playlist"]
        lines.append(f"Playlist of {playlist['items']} tracks, built one add at a time in {playlist['build_seconds']} s; at that size, p50 / p95 ms: "
                     + ", ".join(f"{name} {playlist[name]['p50_ms']} / {playlist[name]['p95_ms']}" for name in ("add", "get", "reorder", "remove")) + ".")
    if report.get("budgets"):
        lines += ["", "Budgets: " + "; ".join(f"{name} {value['measured']} (budget {value['budget']}, {'within' if value['within'] else 'OVER'})"
                                              for name, value in report["budgets"].items())]
    return "\n".join(lines)


PARTS = ("sizes", "adaptation", "import", "contention", "playlist")


def run(
    sizes: List[int], repeats: int, histories: List[int], audio_files: int, audio_seconds: float, contention_loops: int, runs: int = 1,
    playlist_items: int = 1000, parts: Sequence[str] = PARTS,
) -> Dict[str, object]:
    """The parts asked for. Each library size is measured runs times, and its median run is reported (by interactive
    p95) with every run's interactive p50 and p95, because one run on a busy machine can mislead."""
    report: Dict[str, object] = {"machine": machine(), "repeats": repeats, "runs": runs}
    if "sizes" in parts:
        report["sizes"] = []
        for size in sizes:
            print(f"library {size} ...", file=sys.stderr, flush=True)
            measured = [measure_size(size, repeats) for _ in range(runs)]
            median = dict(sorted(measured, key=lambda entry: entry["interactive_p95_ms"])[len(measured) // 2])
            median["runs"] = [
                {"interactive_p50_ms": max(entry["api"][name]["p50_ms"] for name in INTERACTIVE), "interactive_p95_ms": entry["interactive_p95_ms"]}
                for entry in measured
            ]
            report["sizes"].append(median)
        report["budgets"] = budget_check(report["sizes"])
    if "adaptation" in parts:
        report["adaptation"] = []
        for sessions in histories:
            print(f"history {sessions} ...", file=sys.stderr, flush=True)
            report["adaptation"].append(measure_adaptation(sessions, repeats))
    if "import" in parts:
        print(f"import {audio_files} ...", file=sys.stderr, flush=True)
        report["import"] = measure_import(audio_files, audio_seconds)
    if "contention" in parts:
        print("contention ...", file=sys.stderr, flush=True)
        report["contention"] = measure_contention(max(min(sizes), 500), audio_files, contention_loops)
    if "playlist" in parts:
        print(f"playlist {playlist_items} ...", file=sys.stderr, flush=True)
        report["playlist"] = measure_playlist(playlist_items, repeats)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 500, 1000, 2000, 5000])
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--runs", type=int, default=1, help="measure each library size this many times and report the median run")
    parser.add_argument("--histories", type=int, nargs="+", default=[10, 100, 300, 1000])
    parser.add_argument("--audio", type=int, default=200)
    parser.add_argument("--audio-seconds", type=float, default=5.0)
    parser.add_argument("--contention-loops", type=int, default=40)
    parser.add_argument("--playlist-items", type=int, default=1000)
    parser.add_argument("--only", nargs="+", choices=PARTS, default=list(PARTS))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    report = run(args.sizes, args.repeats, args.histories, args.audio, args.audio_seconds, args.contention_loops, args.runs,
                 args.playlist_items, args.only)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(markdown(report))
    return 0 if all(check["within"] for check in report.get("budgets", {}).values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

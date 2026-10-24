"""B11 library reads: the kept full read (TrackSnapshot) and its revision, and reading tracks by id in batches.

A kept read is reused only while the library is exactly as it was read: every write to a track or its labels
advances the library revision in the writing transaction, so a committed change is seen at once and a rolled-back
one never is. Only reads of the committed library are kept, and a newer kept read is never replaced by an older one.
"""

import ast
import inspect
import random
import threading
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork
from src.intentune.persistence import repositories
from src.intentune.persistence.repositories import SqlAlchemyTrackRepository, TrackSnapshot

_NOW = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)


def _track(number, **overrides):
    values = dict(
        track_id=str(uuid.uuid4()),
        sha256=f"{number:064x}",
        size_bytes=1000,
        audio_format=AudioFormat.FLAC,
        status=TrackStatus.READY,
        original_filename=f"song-{number}.flac",
        created_at=_NOW + timedelta(seconds=number),
        updated_at=_NOW + timedelta(seconds=number),
        labels=(TrackLabel(LabelKind.GENRE, "Jazz", "embedded_tags", True),),
    )
    values.update(overrides)
    return Track(**values)


def _add(unit_of_work, *tracks):
    with unit_of_work:
        for track in tracks:
            unit_of_work.tracks.add(track)
        unit_of_work.commit()


def _list_all(unit_of_work):
    with unit_of_work:
        return unit_of_work.tracks.list_all()


@pytest.fixture
def snapshot():
    return TrackSnapshot()


@pytest.fixture
def kept(session_factory, snapshot):
    """A unit of work sharing the snapshot, as every request's does in the API."""
    return SqlAlchemyUnitOfWork(session_factory, snapshot)


@pytest.fixture
def other(session_factory, snapshot):
    """Another request's unit of work, sharing the same snapshot."""
    return SqlAlchemyUnitOfWork(session_factory, snapshot)


def test_an_unchanged_library_is_read_once_and_handed_out_as_a_fresh_list(kept, other):
    _add(kept, _track(1), _track(2))

    first = _list_all(kept)
    second = _list_all(other)

    assert second == first
    assert all(a is b for a, b in zip(first, second))  # the kept Track objects, not a new read
    second.clear()
    assert _list_all(kept) == first  # a caller changing its list changes nothing kept


def test_a_committed_track_or_label_change_is_seen_by_the_next_read(kept, other):
    first, second = _track(1), _track(2)
    _add(kept, first)
    assert _list_all(kept) == [first]

    _add(other, second)
    assert _list_all(kept) == [first, second]

    relabeled = replace(first, labels=(TrackLabel(LabelKind.GENRE, "Ambient", "embedded_tags", True),), updated_at=_NOW)
    with other:
        other.tracks.save(relabeled)
        other.commit()
    assert _list_all(kept) == [relabeled, second]


def test_a_writing_transaction_reads_its_own_change_keeps_nothing_and_its_rollback_invalidates_nothing(kept, other, snapshot):
    first = _track(1)
    _add(kept, first)
    read = _list_all(kept)
    revision = snapshot.revision
    missing = replace(first, status=TrackStatus.MISSING_MANAGED_FILE)

    with other:
        other.tracks.save(missing)
        assert other.tracks.list_all() == [missing]  # its own uncommitted change, read afresh
        assert snapshot.revision == revision  # and not kept
        # leaving without commit rolls the change back

    again = _list_all(kept)
    assert again == [first] and snapshot.revision == revision
    assert all(a is b for a, b in zip(read, again))  # the kept read is still good: the rollback invalidated nothing
    with kept:
        assert kept.tracks._revision() == revision


def test_a_unit_of_work_without_a_snapshot_reads_every_time_and_its_writes_still_count(session_factory, kept):
    plain = SqlAlchemyUnitOfWork(session_factory)
    first, second = _track(1), _track(2)
    _add(plain, first)
    assert _list_all(kept) == [first]

    _add(plain, second)  # a writer that keeps nothing still gives the library a new revision

    assert _list_all(kept) == [first, second]
    assert _list_all(plain) == [first, second]
    assert all(a is not b for a, b in zip(_list_all(plain), _list_all(plain)))


def test_every_write_gives_the_library_a_new_revision(kept):
    with kept:
        before = kept.tracks._revision()
    track = _track(1)
    _add(kept, track)
    with kept:
        after_add = kept.tracks._revision()
        kept.tracks.save(replace(track, title="Renamed"))
        kept.commit()
    with kept:
        after_save = kept.tracks._revision()

    assert len({before, after_add, after_save}) == 3


def test_get_many_reads_the_known_tracks_with_their_labels_in_import_order(unit_of_work):
    tracks = [_track(number, labels=(TrackLabel(LabelKind.GENRE, f"Genre {number}", "embedded_tags", True),)) for number in range(3)]
    _add(unit_of_work, *reversed(tracks))

    with unit_of_work:
        found = unit_of_work.tracks.get_many([tracks[2].track_id, str(uuid.uuid4()), tracks[0].track_id, tracks[2].track_id])
        none = unit_of_work.tracks.get_many([])

    assert found == [tracks[0], tracks[2]]
    assert none == []


def test_get_many_reads_more_ids_than_one_batch_holds(unit_of_work):
    tracks = [_track(number) for number in range(1, 1201)]
    _add(unit_of_work, *tracks)

    with unit_of_work:
        found = unit_of_work.tracks.get_many(track.track_id for track in tracks)

    assert found == tracks


# --- One full read per listening command (B11) ----------------------------------------------------------------------


def test_each_listening_command_reads_the_whole_library_once(client, library_tracks, monkeypatch):
    """The capability check and the refresh share one read; adaptation reads only the tracks its history mentions."""
    reads = []
    list_all = SqlAlchemyTrackRepository.list_all
    monkeypatch.setattr(SqlAlchemyTrackRepository, "list_all", lambda self: reads.append(1) or list_all(self))

    def full_reads(method, path, body):
        reads.clear()
        response = client.request(method, path, json=body)
        assert response.status_code < 300, response.text
        return len(reads), response.json()

    started_reads, started = full_reads("POST", "/api/v1/sessions", {"context": {"temporary_genres": ["Jazz"]}})
    session = f"/api/v1/sessions/{started['session']['session_id']}"
    play_reads, played = full_reads("POST", f"{session}/turns", {"kind": "next"})
    playing, upcoming = played["state"]["playing"]["occurrence_id"], played["state"]["queue"][0]["occurrence_id"]
    counts = {
        "start": started_reads,
        "play": play_reads,
        "like": full_reads("POST", f"{session}/recommendations/{upcoming}/reactions", {"reaction": "like"})[0],
        "refine": full_reads("POST", f"{session}/turns", {"kind": "refine", "context": {"temporary_genres": ["Ambient"]}})[0],
        "next with the player's facts": full_reads(
            "POST", f"{session}/turns", {"kind": "next", "occurrence_id": playing, "playback": {"played_seconds": 30, "duration_seconds": 200}}
        )[0],
        "not for me": full_reads("POST", f"{session}/turns", {"kind": "not_for_me"})[0],
        "typed refinement": full_reads("POST", f"{session}/turns", {"kind": "message", "text": "jazz"})[0],
        "typed start": full_reads("POST", "/api/v1/sessions", {"message": "ambient"})[0],
    }

    assert counts == dict.fromkeys(counts, 1)


# --- The snapshot under concurrent access (B11 review) ------------------------------------------------------------------


def test_an_older_read_that_finishes_last_never_replaces_a_newer_one(snapshot):
    older, newer = (_track(1),), (_track(2),)

    snapshot.keep(5, newer)
    snapshot.keep(4, older)

    assert (snapshot.revision, snapshot.tracks_for(5), snapshot.tracks_for(4)) == (5, newer, None)


def test_overlapping_publications_in_any_order_leave_the_newest_installed(snapshot):
    values = {revision: (_track(revision),) for revision in range(1, 201)}
    order = list(values)
    random.Random(0).shuffle(order)
    start = threading.Barrier(8)

    def publish(revisions):
        start.wait()
        for revision in revisions:
            snapshot.keep(revision, values[revision])

    threads = [threading.Thread(target=publish, args=(order[index::8],)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert (snapshot.revision, snapshot.tracks_for(200)) == (200, values[200])
    assert all(snapshot.tracks_for(revision) is None for revision in range(1, 200))


class _CountingSnapshot(TrackSnapshot):
    def __init__(self):
        super().__init__()
        self.hits = 0

    def tracks_for(self, revision):
        kept = super().tracks_for(revision)
        self.hits += kept is not None
        return kept


def test_a_read_never_returns_a_library_older_than_a_commit_that_finished_before_it_began(session_factory):
    """Three readers and a writer share one snapshot, each with its own unit of work, as API requests do. After each of
    the writer's 40 commits it waits until some read has begun after that commit, so every commit is checked. Every
    read sees at least every track whose commit had returned before the read began."""
    snapshot = _CountingSnapshot()
    _add(SqlAlchemyUnitOfWork(session_factory, snapshot), *(_track(number) for number in range(5)))
    state = {"committed": 5, "floors_read": set()}  # tracks whose commit has returned; floors some read began from
    changed = threading.Condition()
    done = threading.Event()
    stale, missed = [], []

    def write():
        unit_of_work = SqlAlchemyUnitOfWork(session_factory, snapshot)
        try:
            for number in range(5, 45):
                _add(unit_of_work, _track(number))
                with changed:
                    state["committed"] += 1
                    changed.notify_all()
                    if not changed.wait_for(lambda: state["committed"] in state["floors_read"], timeout=10):
                        missed.append(state["committed"])
        finally:
            done.set()

    def read():
        unit_of_work = SqlAlchemyUnitOfWork(session_factory, snapshot)
        while not done.is_set():
            with changed:
                floor = state["committed"]
            seen = len(_list_all(unit_of_work))
            with changed:
                if seen < floor:
                    stale.append((floor, seen))
                state["floors_read"].add(floor)
                changed.notify_all()

    threads = [threading.Thread(target=write)] + [threading.Thread(target=read) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)

    assert (stale, missed) == ([], [])
    assert set(range(6, 46)) <= state["floors_read"]  # a read began after every one of the 40 commits
    assert snapshot.hits > 0  # and the kept read was used along the way
    assert len(_list_all(SqlAlchemyUnitOfWork(session_factory, snapshot))) == 45


def test_every_write_to_the_track_tables_advances_the_revision():
    """The snapshot is exact only while nothing writes tracks or track_labels without advancing the revision.

    Only the track repository touches those tables, and each of its methods that writes them advances it. Migrations
    also write tracks, but they run at startup, before any read is kept. A future write to anything the snapshot
    comes to hold (measured features, for one) must advance the revision too.
    """
    tree = ast.parse(inspect.getsource(repositories))
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    for node in classes:
        if node.name != "SqlAlchemyTrackRepository":
            used = {name.id for name in ast.walk(node) if isinstance(name, ast.Name)}
            assert not used & {"TrackRecord", "TrackLabelRecord", "_apply_track", "LibraryRevisionRecord"}, node.name
    track_repository = next(node for node in classes if node.name == "SqlAlchemyTrackRepository")
    writers = []
    for method in (node for node in track_repository.body if isinstance(node, ast.FunctionDef)):
        source = ast.unparse(method)
        if method.name not in ("_changed", "_add_labels") and any(
            write in source for write in ("self._session.add(", "delete(", "update(", "_apply_track(", "self._add_labels(")
        ):
            writers.append(method.name)
            assert "self._changed()" in source, method.name
    assert sorted(writers) == ["add", "save"]
    source_root = Path(repositories.__file__).resolve().parents[1]
    for module in source_root.rglob("*.py"):
        if module.name not in ("models.py", "repositories.py"):
            text = module.read_text(encoding="utf-8")
            assert "TrackRecord" not in text and "TrackLabelRecord" not in text and "library_revision" not in text, module

"""Alembic migrations: a clean database upgrades, downgrades, matches the ORM records, and fails atomically."""

import os
import uuid
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from src.intentune.application.adaptation import LongTermAdaptationService
from src.intentune.application.local_listener import ensure_default_listener
from src.intentune.application.playlists import PlaylistService
from src.intentune.application.sessions import SessionService
from src.intentune.domain.library import AudioFormat, LabelKind, Track, TrackLabel, TrackStatus
from src.intentune.domain.models import ListeningContext, MusicCandidate, Recommendation, ScoreBreakdown, ScoreComponent
from src.intentune.domain.session import FeedbackEventType, TurnKind
from src.intentune.persistence.db import create_database_engine, create_session_factory
from src.intentune.persistence.migrations import alembic_config, upgrade_database
from src.intentune.persistence.models import Base
from src.intentune.persistence.unit_of_work import SqlAlchemyUnitOfWork

_INSERT_PROFILE = "INSERT INTO listener_profiles (id, is_default, created_at) VALUES (?, ?, '2026-10-19 12:00:00')"
_FIRST_ID = "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e"
_SECOND_ID = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"


def _head_revision(database_url):
    return ScriptDirectory.from_config(alembic_config(database_url)).get_current_head()


def _current_revision(database_url):
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _table_names(database_url):
    engine = create_database_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _definition(object_type, sql):
    """A table's definition as an unordered set of its column and constraint clauses; other SQL unchanged.

    Alembic's batch mode rebuilds a table from SQLAlchemy's constraint *set*,
    so a rebuilt table (B3's tracks) lists the same constraints in a varying
    order. Comparing clauses as a set keeps every definition exact while
    ignoring that order.
    """
    if object_type != "table" or sql is None:
        return sql
    body = sql[sql.index("(") + 1 : sql.rindex(")")]
    return frozenset(clause.strip().rstrip(",").strip() for clause in body.splitlines() if clause.strip())


def _schema_snapshot(database_url):
    """Every table, index, and trigger definition SQLite holds, for before/after comparison."""
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
            ).all()
    finally:
        engine.dispose()
    return [(object_type, name, table, _definition(object_type, sql)) for object_type, name, table, sql in rows]


def test_migration_history_has_a_single_head(database_url):
    heads = ScriptDirectory.from_config(alembic_config(database_url)).get_heads()

    assert len(heads) == 1


def test_clean_database_upgrades_to_head(database_url):
    upgrade_database(database_url)

    tables = _table_names(database_url)
    assert _current_revision(database_url) == _head_revision(database_url)
    assert "listener_profiles" in tables
    # Exactly matching the records (no missing or extra tables) is checked by
    # test_migrations_match_the_orm_records.
    assert set(Base.metadata.tables) <= tables


def test_listener_profiles_schema(engine):
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("listener_profiles")}
    primary_key = inspector.get_pk_constraint("listener_profiles")

    assert set(columns) == {"id", "is_default", "created_at"}
    assert [name for name, column in columns.items() if column["nullable"]] == []
    assert primary_key["constrained_columns"] == ["id"]
    assert primary_key["name"] == "pk_listener_profiles"
    assert inspector.get_foreign_keys("listener_profiles") == []


def test_listener_profiles_has_a_unique_index_on_the_default_flag(engine):
    indexes = {index["name"]: index for index in inspect(engine).get_indexes("listener_profiles")}

    index = indexes["uq_listener_profiles_is_default"]
    assert index["unique"]
    assert index["column_names"] == ["is_default"]
    # The index is partial (WHERE is_default = 1). That is verified by behavior:
    # test_database_allows_only_one_default_listener and
    # test_database_allows_several_non_default_listeners.


def test_database_path_with_spaces_and_percent_signs_upgrades(tmp_path):
    directory = tmp_path / "100% local music"
    directory.mkdir()
    database_url = URL.create("sqlite", database=str(directory / "intentune.db"))

    upgrade_database(database_url)

    assert (directory / "intentune.db").is_file()
    assert _current_revision(database_url) == _head_revision(database_url)


def test_upgrading_an_up_to_date_database_is_a_no_op(migrated_database_url):
    before = _schema_snapshot(migrated_database_url)

    upgrade_database(migrated_database_url)

    assert _current_revision(migrated_database_url) == _head_revision(migrated_database_url)
    assert _schema_snapshot(migrated_database_url) == before


def test_downgrade_to_base_removes_the_schema(migrated_database_url):
    command.downgrade(alembic_config(migrated_database_url), "base")

    tables = _table_names(migrated_database_url)
    assert _current_revision(migrated_database_url) is None
    assert "listener_profiles" not in tables
    assert not tables & set(Base.metadata.tables)


def test_upgrade_downgrade_upgrade_round_trip(migrated_database_url):
    config = alembic_config(migrated_database_url)
    first_upgrade = _schema_snapshot(migrated_database_url)

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    assert _current_revision(migrated_database_url) == _head_revision(migrated_database_url)
    assert _schema_snapshot(migrated_database_url) == first_upgrade


def test_migrations_match_the_orm_records(engine):
    with engine.connect() as connection:
        differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)

    assert differences == []


def test_database_allows_only_one_default_listener(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(_INSERT_PROFILE, (_FIRST_ID, 1))

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql(_INSERT_PROFILE, (_SECOND_ID, 1))

    with engine.begin() as connection:
        connection.exec_driver_sql(_INSERT_PROFILE, (_SECOND_ID, 0))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE listener_profiles SET is_default = 1 WHERE id = ?", (_SECOND_ID,))

    with engine.connect() as connection:
        defaults = connection.exec_driver_sql("SELECT id FROM listener_profiles WHERE is_default = 1").scalars().all()
    assert defaults == [_FIRST_ID]


def test_database_allows_several_non_default_listeners(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(_INSERT_PROFILE, (_FIRST_ID, 0))
        connection.exec_driver_sql(_INSERT_PROFILE, (_SECOND_ID, 0))

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM listener_profiles").scalar() == 2


def test_downgrading_background_analysis_keeps_tracks_and_returns_them_to_imported(migrated_database_url):
    """B3's migration rebuilt tracks to allow ANALYZING and READY; its downgrade must keep every track."""
    track_id = "3f2c4a8e-1b7d-4c55-9e0a-6d1f2b3c4d5e"
    engine = create_database_engine(migrated_database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO tracks (id, sha256, size_bytes, audio_format, status, original_filename, analysis_version, created_at, updated_at) "
                "VALUES (?, ?, 10, 'flac', 'READY', 'song.flac', 'a@1', '2026-10-20 09:00:00', '2026-10-20 09:00:00')",
                (track_id, "a" * 64),
            )
            connection.exec_driver_sql(
                "INSERT INTO analysis_jobs (id, track_id, kind, analyzer, status, attempts, created_at, updated_at) "
                "VALUES ('9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d', ?, 'ANALYZE_AUDIO', 'a@1', 'SUCCEEDED', 1, '2026-10-20 09:00:00', '2026-10-20 09:00:00')",
                (track_id,),
            )
    finally:
        engine.dispose()

    command.downgrade(alembic_config(migrated_database_url), "2540be2956b8")

    engine = create_database_engine(migrated_database_url)
    try:
        with engine.connect() as connection:
            rows = connection.exec_driver_sql("SELECT id, status, analysis_version FROM tracks").all()
        assert rows == [(track_id, "IMPORTED", None)]
        assert {"analysis_jobs", "track_features"}.isdisjoint(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    command.upgrade(alembic_config(migrated_database_url), "head")
    assert _current_revision(migrated_database_url) == _head_revision(migrated_database_url)


def test_the_b5_rebuild_keeps_occurrences_and_the_turns_about_them(migrated_database_url):
    """B5 rebuilt recommendation_occurrences to add surfaced_position and is_exploration. Rows and the turns
    that reference them survive the rebuild both ways."""
    engine = create_database_engine(migrated_database_url)
    try:
        unit_of_work = SqlAlchemyUnitOfWork(create_session_factory(engine))
        listener_id = ensure_default_listener(unit_of_work).listener_profile_id
        now = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
        track = Track(
            track_id=_FIRST_ID, sha256="a" * 64, size_bytes=10, audio_format=AudioFormat.FLAC, status=TrackStatus.IMPORTED,
            original_filename="song.flac", created_at=now, updated_at=now,
        )
        with unit_of_work:
            unit_of_work.tracks.add(track)
            unit_of_work.commit()
        sessions = SessionService(unit_of_work)
        session_id = sessions.start_session(listener_id, ListeningContext(temporary_genres=("ambient",))).session.session_id
        recommendation = Recommendation(
            candidate=MusicCandidate(candidate_id=track.track_id, title="Song", creator="Artist", source="local"),
            score_breakdown=ScoreBreakdown(total_score=0.5, maximum_score=1.0, components=(ScoreComponent("intent", 0.5, 1.0, "intent fit 0.50"),)),
            rank=1,
        )
        [occurrence] = sessions.queue_recommendations(session_id, [recommendation], "policy-v1", exploration_track_ids={track.track_id}).queue
        assert occurrence.is_exploration
        sessions.advance(session_id)
        sessions.apply_turn(session_id, TurnKind.NOT_FOR_ME)
    finally:
        engine.dispose()

    def occurrence_rows():
        engine = create_database_engine(migrated_database_url)
        try:
            with engine.connect() as connection:
                occurrences = connection.exec_driver_sql("SELECT * FROM recommendation_occurrences").mappings().all()
                turn_targets = connection.exec_driver_sql("SELECT occurrence_id FROM session_turns WHERE occurrence_id IS NOT NULL").scalars().all()
            return [dict(row) for row in occurrences], turn_targets
        finally:
            engine.dispose()

    command.downgrade(alembic_config(migrated_database_url), "dd7360f46b8b")
    [before_b5], turn_targets = occurrence_rows()
    assert {"is_exploration", "surfaced_position"}.isdisjoint(before_b5)
    # Not for me about the playing track moved playback on (B6), so it has played.
    assert (before_b5["id"], before_b5["status"], turn_targets) == (occurrence.occurrence_id, "PLAYED", [occurrence.occurrence_id])

    command.upgrade(alembic_config(migrated_database_url), "head")
    [after_b5], turn_targets = occurrence_rows()
    assert after_b5 == {**before_b5, "is_exploration": 0, "surfaced_position": 0}
    assert turn_targets == [occurrence.occurrence_id]


def test_the_b5_migration_recovers_surfaced_positions_from_insertion_order(database_url):
    """Occurrences from before B5 get the position they were surfaced at: B4 inserted each queue in order,
    with one surfaced_at, so insertion order within a session and surfaced_at is the surfaced order."""
    command.upgrade(alembic_config(database_url), "dd7360f46b8b")
    first_queue, second_queue = "2026-10-20 09:00:00", "2026-10-20 09:05:00"
    track_ids = [f"7d1f2b3c-4d5e-4c55-9e0a-3f2c4a8e1b7{index}" for index in range(3)]
    listener_ids = [_FIRST_ID, _SECOND_ID]  # one active session each
    session_ids = ["0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e40", "0c1d2e3f-4a5b-4c6d-8e7f-9a0b1c2d3e41"]
    # (session, surfaced_at, track, rank, status, queue_position, started_at, finished_at), in insertion order.
    occurrences = [
        (0, first_queue, 1, 2, "PLAYED", None, first_queue, second_queue),  # rank 2 surfaced, and played, first
        (0, first_queue, 0, 1, "REPLACED", None, None, second_queue),
        (0, first_queue, 2, 3, "REPLACED", None, None, second_queue),
        (1, first_queue, 0, 1, "QUEUED", 0, None, None),  # another session's queue, surfaced at the same moment
        (0, second_queue, 2, 1, "PLAYING", None, second_queue, None),
        (0, second_queue, 0, 2, "QUEUED", 1, None, None),
    ]
    engine = create_database_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(_INSERT_PROFILE, (_FIRST_ID, 1))
            connection.exec_driver_sql(_INSERT_PROFILE, (_SECOND_ID, 0))
            for index, track_id in enumerate(track_ids):
                connection.exec_driver_sql(
                    "INSERT INTO tracks (id, sha256, size_bytes, audio_format, status, original_filename, created_at, updated_at) "
                    "VALUES (?, ?, 10, 'flac', 'IMPORTED', 'song.flac', ?, ?)",
                    (track_id, str(index) * 64, first_queue, first_queue),
                )
            for session_id, listener_id in zip(session_ids, listener_ids):
                connection.exec_driver_sql(
                    "INSERT INTO listening_sessions (id, listener_profile_id, status, context_json, started_at, updated_at) "
                    "VALUES (?, ?, 'ACTIVE', '{\"context\": {}, \"format\": 1}', ?, ?)",
                    (session_id, listener_id, first_queue, second_queue),
                )
            for number, (session, surfaced_at, track, rank, status, position, started, finished) in enumerate(occurrences):
                connection.exec_driver_sql(
                    "INSERT INTO recommendation_occurrences "
                    "(id, session_id, track_id, rank, score, algorithm, status, queue_position, surfaced_at, updated_at, started_at, finished_at) "
                    "VALUES (?, ?, ?, ?, 0.5, 'test-algorithm-v1', ?, ?, ?, ?, ?, ?)",
                    (f"5e4f4a3b-8c2d-4e0f-9a8b-7c6d5e4f4a3{number}", session_ids[session], track_ids[track], rank, status,
                     position, surfaced_at, surfaced_at, started, finished),
                )
    finally:
        engine.dispose()

    command.upgrade(alembic_config(database_url), "head")

    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT id, surfaced_position, queue_position, is_exploration FROM recommendation_occurrences"
            ).all()
    finally:
        engine.dispose()
    by_id = {row[0]: row[1:] for row in rows}
    stored = [by_id[f"5e4f4a3b-8c2d-4e0f-9a8b-7c6d5e4f4a3{number}"] for number in range(len(occurrences))]
    assert stored == [(0, None, 0), (1, None, 0), (2, None, 0), (0, 0, 0), (0, None, 0), (1, 1, 0)]


def test_the_b7_migration_keeps_feedback_and_its_downgrade_removes_only_playlist_data(migrated_database_url):
    """B7 rebuilt feedback_events to accept PLAYLIST_ADD. Downgrading drops the playlist tables and the PLAYLIST_ADD
    events that came from them, and keeps every other event exactly; upgrading accepts PLAYLIST_ADD again."""
    engine = create_database_engine(migrated_database_url)
    try:
        unit_of_work = SqlAlchemyUnitOfWork(create_session_factory(engine))
        listener_id = ensure_default_listener(unit_of_work).listener_profile_id
        now = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
        with unit_of_work:
            unit_of_work.tracks.add(Track(
                track_id=_FIRST_ID, sha256="a" * 64, size_bytes=10, audio_format=AudioFormat.FLAC, status=TrackStatus.IMPORTED,
                original_filename="song.flac", created_at=now, updated_at=now,
            ))
            unit_of_work.commit()
        sessions = SessionService(unit_of_work)
        session_id = sessions.start_session(listener_id, ListeningContext()).session.session_id
        recommendation = Recommendation(
            candidate=MusicCandidate(candidate_id=_FIRST_ID, title="Song", creator="Artist", source="local"),
            score_breakdown=ScoreBreakdown(total_score=0.5, maximum_score=1.0, components=(ScoreComponent("intent", 0.5, 1.0, "intent fit 0.50"),)),
            rank=1,
        )
        [occurrence] = sessions.queue_recommendations(session_id, [recommendation], "policy-v1").queue
        sessions.record_feedback(session_id, occurrence.occurrence_id, FeedbackEventType.LIKE)
        sessions.record_feedback(session_id, occurrence.occurrence_id, FeedbackEventType.PLAYLIST_ADD)
        playlist_id = PlaylistService(unit_of_work).create_playlist(listener_id, "Focus").playlist_id
        PlaylistService(unit_of_work).add_track(playlist_id, _FIRST_ID)
        with engine.connect() as connection:
            like_before = connection.exec_driver_sql("SELECT * FROM feedback_events WHERE event_type = 'LIKE'").one()
    finally:
        engine.dispose()

    command.downgrade(alembic_config(migrated_database_url), "de244c476f3a")

    assert {"playlists", "playlist_items"}.isdisjoint(_table_names(migrated_database_url))
    engine = create_database_engine(migrated_database_url)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT * FROM feedback_events").all() == [like_before]
    finally:
        engine.dispose()

    command.upgrade(alembic_config(migrated_database_url), "head")
    engine = create_database_engine(migrated_database_url)
    try:
        SessionService(SqlAlchemyUnitOfWork(create_session_factory(engine))).record_feedback(
            session_id, occurrence.occurrence_id, FeedbackEventType.PLAYLIST_ADD
        )
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT event_type FROM feedback_events ORDER BY occurred_at").scalars().all() == ["LIKE", "PLAYLIST_ADD"]
    finally:
        engine.dispose()


def test_the_b9_migration_accepts_unlike_and_its_downgrade_removes_only_unlike_events(migrated_database_url):
    """B9 rebuilt feedback_events to accept UNLIKE. Downgrading removes UNLIKE events and keeps every other event
    exactly; upgrading accepts UNLIKE again."""
    engine = create_database_engine(migrated_database_url)
    try:
        unit_of_work = SqlAlchemyUnitOfWork(create_session_factory(engine))
        listener_id = ensure_default_listener(unit_of_work).listener_profile_id
        now = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
        with unit_of_work:
            unit_of_work.tracks.add(Track(
                track_id=_FIRST_ID, sha256="a" * 64, size_bytes=10, audio_format=AudioFormat.FLAC, status=TrackStatus.IMPORTED,
                original_filename="song.flac", created_at=now, updated_at=now,
            ))
            unit_of_work.commit()
        sessions = SessionService(unit_of_work)
        session_id = sessions.start_session(listener_id, ListeningContext()).session.session_id
        recommendation = Recommendation(
            candidate=MusicCandidate(candidate_id=_FIRST_ID, title="Song", creator="Artist", source="local"),
            score_breakdown=ScoreBreakdown(total_score=0.5, maximum_score=1.0, components=(ScoreComponent("intent", 0.5, 1.0, "intent fit 0.50"),)),
            rank=1,
        )
        [occurrence] = sessions.queue_recommendations(session_id, [recommendation], "policy-v1").queue
        sessions.record_feedback(session_id, occurrence.occurrence_id, FeedbackEventType.LIKE)
        sessions.record_feedback(session_id, occurrence.occurrence_id, FeedbackEventType.UNLIKE)
        with engine.connect() as connection:
            like_before = connection.exec_driver_sql("SELECT * FROM feedback_events WHERE event_type = 'LIKE'").one()
    finally:
        engine.dispose()

    command.downgrade(alembic_config(migrated_database_url), "ce0b59df2cd1")

    engine = create_database_engine(migrated_database_url)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT * FROM feedback_events").all() == [like_before]
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql(
                    "INSERT INTO feedback_events (id, session_id, occurrence_id, event_type, occurred_at) VALUES (?, ?, ?, 'UNLIKE', ?)",
                    (_SECOND_ID, session_id, occurrence.occurrence_id, "2026-10-21 10:00:00"),
                )
    finally:
        engine.dispose()

    command.upgrade(alembic_config(migrated_database_url), "head")
    engine = create_database_engine(migrated_database_url)
    try:
        SessionService(SqlAlchemyUnitOfWork(create_session_factory(engine))).record_feedback(
            session_id, occurrence.occurrence_id, FeedbackEventType.UNLIKE
        )
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT event_type FROM feedback_events ORDER BY occurred_at").scalars().all() == ["LIKE", "UNLIKE"]
    finally:
        engine.dispose()


def test_the_b10_migration_adds_long_term_adaptation_and_its_downgrade_keeps_the_raw_history(migrated_database_url):
    """B10 adds the profile and its audit trail. Downgrading drops only those three tables; the raw history they were
    derived from stays exactly, so after upgrading again the same profile is derived and recorded anew."""
    engine = create_database_engine(migrated_database_url)
    try:
        unit_of_work = SqlAlchemyUnitOfWork(create_session_factory(engine))
        listener_id = ensure_default_listener(unit_of_work).listener_profile_id
        now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        track_ids = [str(uuid.UUID(int=n)) for n in range(1, 5)]
        with unit_of_work:
            for n, track_id in enumerate(track_ids):
                unit_of_work.tracks.add(Track(
                    track_id=track_id, sha256=f"{n}" * 64, size_bytes=10, audio_format=AudioFormat.FLAC, status=TrackStatus.READY,
                    original_filename=f"song{n}.flac", created_at=now, updated_at=now, labels=(TrackLabel(LabelKind.GENRE, "Jazz", "tag", True),),
                ))
            unit_of_work.commit()
        sessions = SessionService(unit_of_work)
        for pair in (track_ids[:2], track_ids[2:]):
            session_id = sessions.start_session(listener_id, ListeningContext()).session.session_id
            recommendations = [
                Recommendation(
                    candidate=MusicCandidate(candidate_id=track_id, title="Song", creator="Artist", source="local"),
                    score_breakdown=ScoreBreakdown(total_score=0.5, maximum_score=1.0, components=(ScoreComponent("intent", 0.5, 1.0, "intent fit 0.50"),)),
                    rank=rank,
                )
                for rank, track_id in enumerate(pair, 1)
            ]
            for occurrence in sessions.queue_recommendations(session_id, recommendations, "policy-v1").queue:
                sessions.record_feedback(session_id, occurrence.occurrence_id, FeedbackEventType.LIKE)
        adaptation = LongTermAdaptationService(unit_of_work)
        [added] = adaptation.adapt(listener_id)
        profile = adaptation.profile(listener_id)
        with engine.connect() as connection:
            events_before = connection.exec_driver_sql("SELECT * FROM feedback_events ORDER BY id").all()
    finally:
        engine.dispose()
    assert (added.subject, len(added.evidence), profile.preferred_genres) == ("Jazz", 4, ("Jazz",))

    command.downgrade(alembic_config(migrated_database_url), "4b1e9c7d2a6f")

    tables = _table_names(migrated_database_url)
    assert not {"long_term_profiles", "long_term_adjustments", "long_term_adjustment_evidence"} & tables
    engine = create_database_engine(migrated_database_url)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT * FROM feedback_events ORDER BY id").all() == events_before
    finally:
        engine.dispose()

    command.upgrade(alembic_config(migrated_database_url), "head")
    engine = create_database_engine(migrated_database_url)
    try:
        rebuilt = LongTermAdaptationService(SqlAlchemyUnitOfWork(create_session_factory(engine)))
        [again] = rebuilt.adapt(listener_id)
        assert rebuilt.profile(listener_id) == profile
        assert (again.subject, [reference.feedback_event_id for reference in again.evidence]) == (
            "Jazz", [reference.feedback_event_id for reference in added.evidence]
        )
    finally:
        engine.dispose()


def test_the_b11_migration_adds_one_library_revision_and_its_downgrade_drops_only_it(migrated_database_url):
    """B11 adds the one-row library_revision a full library read is kept under. A track write advances it;
    downgrading drops the table and nothing else; upgrading again starts it afresh."""
    def revision_rows():
        engine = create_database_engine(migrated_database_url)
        try:
            with engine.connect() as connection:
                return connection.exec_driver_sql("SELECT id, revision FROM library_revision").all()
        finally:
            engine.dispose()

    assert revision_rows() == [(1, 1)]
    engine = create_database_engine(migrated_database_url)
    try:
        unit_of_work = SqlAlchemyUnitOfWork(create_session_factory(engine))
        now = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)
        with unit_of_work:
            unit_of_work.tracks.add(Track(
                track_id=str(uuid.UUID(int=1)), sha256="1" * 64, size_bytes=10, audio_format=AudioFormat.FLAC, status=TrackStatus.READY,
                original_filename="song.flac", created_at=now, updated_at=now, labels=(TrackLabel(LabelKind.GENRE, "Jazz", "tag", True),),
            ))
            unit_of_work.commit()
        with engine.connect() as connection:
            tracks_before = connection.exec_driver_sql("SELECT * FROM tracks").all()
            labels_before = connection.exec_driver_sql("SELECT * FROM track_labels").all()
    finally:
        engine.dispose()
    assert revision_rows() == [(1, 2)]

    command.downgrade(alembic_config(migrated_database_url), "5d8e2b7a9c41")

    assert "library_revision" not in _table_names(migrated_database_url)
    engine = create_database_engine(migrated_database_url)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT * FROM tracks").all() == tracks_before
            assert connection.exec_driver_sql("SELECT * FROM track_labels").all() == labels_before
    finally:
        engine.dispose()

    command.upgrade(alembic_config(migrated_database_url), "head")
    assert revision_rows() == [(1, 1)]


def test_migrated_database_uses_wal_and_leaves_no_foreign_key_violations(engine):
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []


# --- A failing migration rolls back completely ---------------------------------
#
# B1 makes SQLite DDL transactional (SQLAlchemy emits BEGIN) and runs each
# upgrade as one transaction (transactional_ddl=True in alembic/env.py).
# These tests add a deliberately failing revision on top of the real head. It
# creates a table and rebuilds listener_profiles with an extra column, checks
# that both changes are in effect, then raises. Without transactional DDL the
# changes would survive the failure.

_FAILING_REVISION = "b1_deliberate_failure"

_FAILING_MIGRATION_SOURCE = '''"""Changes the schema, then fails. Used only by tests/test_migrations.py."""
import sqlalchemy as sa
from alembic import op

revision = "b1_deliberate_failure"
down_revision = DOWN_REVISION
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("doomed_table", sa.Column("id", sa.Integer(), primary_key=True))
    with op.batch_alter_table("listener_profiles", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("doomed_column", sa.String(length=10)))

    inspector = sa.inspect(op.get_bind())
    applied = inspector.has_table("doomed_table") and "doomed_column" in {
        column["name"] for column in inspector.get_columns("listener_profiles")
    }
    raise RuntimeError(f"deliberate failure; schema changes applied before it: {applied}")


def downgrade():
    raise NotImplementedError
'''


def _config_with_failing_migration(database_url, tmp_path):
    """An Alembic config whose history is the real migrations plus the failing revision on top."""
    config = alembic_config(database_url)
    script = ScriptDirectory.from_config(config)

    failing_versions = tmp_path / "failing_versions"
    failing_versions.mkdir()
    (failing_versions / f"{_FAILING_REVISION}.py").write_text(
        _FAILING_MIGRATION_SOURCE.replace("DOWN_REVISION", repr(script.get_current_head())),
        encoding="utf-8",
    )
    locations = os.pathsep.join([script.versions, str(failing_versions)])
    config.set_main_option("version_locations", locations.replace("%", "%%"))
    return config


def test_failed_migration_leaves_schema_and_data_unchanged(migrated_database_url, tmp_path):
    engine = create_database_engine(migrated_database_url)
    try:
        listener = ensure_default_listener(SqlAlchemyUnitOfWork(create_session_factory(engine)))
    finally:
        engine.dispose()
    schema_before = _schema_snapshot(migrated_database_url)
    head = _head_revision(migrated_database_url)

    with pytest.raises(RuntimeError, match="schema changes applied before it: True"):
        command.upgrade(_config_with_failing_migration(migrated_database_url, tmp_path), _FAILING_REVISION)

    assert _schema_snapshot(migrated_database_url) == schema_before
    assert _current_revision(migrated_database_url) == head
    engine = create_database_engine(migrated_database_url)
    try:
        with SqlAlchemyUnitOfWork(create_session_factory(engine)) as unit_of_work:
            assert unit_of_work.listener_profiles.get_default() == listener
    finally:
        engine.dispose()


def test_failed_upgrade_from_empty_rolls_back_every_revision_in_it(database_url, tmp_path):
    schema_before = _schema_snapshot(database_url)

    with pytest.raises(RuntimeError, match="schema changes applied before it: True"):
        command.upgrade(_config_with_failing_migration(database_url, tmp_path), _FAILING_REVISION)

    assert schema_before == []
    assert _schema_snapshot(database_url) == schema_before
    assert _current_revision(database_url) is None

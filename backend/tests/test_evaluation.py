"""B11 evaluation tooling: the algorithm scenarios reproduce their baseline, and the performance harness runs.

The scenarios' baseline is the evaluation of Policy v1 and Long-Term Adaptation Policy v1. A change to either policy
makes the first test fail on purpose: review the difference, report it, and store it with
`python -m evaluation.scenarios --write-baseline` (docs/quality/evaluation-report.md). It is never asserted to be
an improvement.
"""

import json

from evaluation import performance, scenarios


def test_the_scenarios_reproduce_their_baseline_exactly():
    report = json.loads(json.dumps(scenarios.run()))

    assert report == json.loads(scenarios.BASELINE.read_text(encoding="utf-8"))


def test_the_scenarios_cover_the_five_named_ones_and_the_adaptation_listeners():
    baseline = json.loads(scenarios.BASELINE.read_text(encoding="utf-8"))

    assert set(baseline["policy_scenarios"]) == {"study/calm", "workout/high energy", "party/dance", "relax", "discovery"}
    assert set(baseline["adaptation_listeners"]) == set(scenarios.LISTENERS)
    assert baseline["versions"] == {"policy": "policy-v1", "adaptation": "adaptation-v1"}


def test_the_performance_harness_measures_a_tiny_library_and_its_restart():
    size = performance.measure_size(30, repeats=2)

    assert size["tracks"] == 30
    assert set(size["api"]) == {
        "start", "play", "like", "refine", "next_with_skip", "list_sessions", "session_detail", "vocabulary", "tracks_page"
    }
    assert set(size["first_loop_ms"]) == set(size["api"])
    # One session from the refresh measurement, the cold and warm-up loops, one per timed loop, and the memory pass.
    assert size["restart"] == {"startup_seconds": size["restart"]["startup_seconds"], "sessions_kept": 6, "all_ended": True, "tracks_kept": 30}


def test_the_performance_harness_measures_adaptation_import_and_playlists():
    adaptation = performance.measure_adaptation(3, repeats=2)
    imported = performance.measure_import(2, seconds=0.5)
    playlist = performance.measure_playlist(5, repeats=2)

    assert adaptation["sessions"] == 3 and adaptation["derive"]["n"] == 2
    assert (imported["imported"], imported["rescan_unchanged"], imported["analyzed"]) == (2, 2, 2)
    assert imported["managed_bytes"] == imported["source_bytes"]
    assert (playlist["items"], playlist["add"]["n"], playlist["reorder"]["n"], playlist["kept_order"]) == (5, 2, 2, True)


def test_the_performance_report_renders_only_the_parts_measured():
    report = {"machine": performance.machine(), "playlist": performance.measure_playlist(3, repeats=1)}

    assert "Playlist of 3 tracks" in performance.markdown(report)
    assert "Import" not in performance.markdown(report)

"""B11 evaluation tooling: reproducible performance measurements and algorithm scenarios (not part of the app).

Run from backend/:

    python -m evaluation.performance        # latency, throughput, contention, memory, restart
    python -m evaluation.scenarios          # Policy v1 and Long-Term Adaptation Policy v1 scenarios

Everything here builds its own scratch databases and synthetic libraries. It never opens backend/data.
"""

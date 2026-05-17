import sqlite3
import os
import random
import uuid
from datetime import date, timedelta, datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'de_copilot.db')

SITES = ['SEA1', 'SEA2', 'PDX1', 'LAX1', 'LAX2', 'SFO1', 'DEN1', 'CHI1', 'JFK1', 'BOS1']


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'seed.sql')
    with open(schema_path) as f:
        conn.executescript(f.read())

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM site_metrics")
    if cursor.fetchone()[0] == 0:
        _seed_data(conn)

    conn.commit()
    conn.close()


def _seed_data(conn):
    cursor = conn.cursor()
    today = date.today()
    now = datetime.now()

    # site_metrics — 10 sites x 30 days = 300 rows
    # LAX2 has chronic delivery rate issues (below 90%)
    # SEA2 has a freshness issue — records appear stale
    for site in SITES:
        for i in range(30):
            metric_date = today - timedelta(days=i)
            attempted = random.randint(850, 1200)

            if site == 'LAX2':
                rate = round(random.uniform(0.74, 0.87), 4)
            elif site == 'DEN1' and i < 7:
                rate = round(random.uniform(0.86, 0.91), 4)
            else:
                rate = round(random.uniform(0.91, 0.99), 4)

            delivered = int(attempted * rate)

            if site == 'SEA2':
                created_at = (now - timedelta(hours=27 + i)).isoformat()
            else:
                created_at = (now - timedelta(hours=random.randint(1, 3))).isoformat()

            cursor.execute(
                "INSERT INTO site_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), site, metric_date.isoformat(),
                    delivered, attempted, rate,
                    round(random.uniform(3.5, 8.5), 2),
                    created_at,
                )
            )

    # labor_events — 10 sites x 30 days = 300 rows
    # ~5% of rows have NULL headcount + variance to demo data quality
    for site in SITES:
        for i in range(30):
            event_date = today - timedelta(days=i)
            planned = random.randint(40, 120)
            variance = random.randint(-15, 15)
            actual = planned + variance

            if random.random() < 0.05:
                actual = None
                variance = None

            cursor.execute(
                "INSERT INTO labor_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), site, event_date.isoformat(),
                    random.choice(['AM', 'PM', 'NIGHT']),
                    actual, planned, variance,
                    (now - timedelta(hours=random.randint(1, 3))).isoformat(),
                )
            )

    # pipeline_runs — 50 rows across 4 pipelines
    # ~20% failure rate to demo pipeline health
    pipelines = [
        'site_metrics_ingestion',
        'labor_events_etl',
        'delivery_rate_summary',
        'site_capacity_forecast',
    ]
    errors = [
        'Connection timeout to Redshift cluster',
        'S3 partition not found: s3://utr-data/site_metrics/2025-05-10',
        'Row count check failed: expected >= 1000, got 0',
    ]

    for i in range(50):
        pipeline = random.choice(pipelines)
        status = random.choices(['SUCCESS', 'FAILED', 'RUNNING'], weights=[75, 20, 5])[0]
        started = now - timedelta(hours=random.randint(1, 720))
        completed = started + timedelta(minutes=random.randint(5, 60)) if status != 'RUNNING' else None
        error = random.choice(errors) if status == 'FAILED' else None
        rows = random.randint(5000, 500000) if status == 'SUCCESS' else None

        cursor.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()), pipeline, status,
                started.isoformat(),
                completed.isoformat() if completed else None,
                rows, error,
            )
        )

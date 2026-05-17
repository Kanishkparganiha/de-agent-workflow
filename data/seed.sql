CREATE TABLE IF NOT EXISTS labor_events (
    event_id TEXT PRIMARY KEY,
    site_id TEXT,
    event_date DATE,
    shift_type TEXT,
    headcount INTEGER,
    planned_headcount INTEGER,
    variance INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS site_metrics (
    metric_id TEXT PRIMARY KEY,
    site_id TEXT,
    metric_date DATE,
    packages_delivered INTEGER,
    packages_attempted INTEGER,
    delivery_rate REAL,
    avg_stop_time_minutes REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    pipeline_name TEXT,
    status TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    rows_processed INTEGER,
    error_message TEXT
);

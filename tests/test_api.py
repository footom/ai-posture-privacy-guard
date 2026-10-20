import pytest
import sqlite3
from fastapi.testclient import TestClient
from src.api import app

"""
搭配真實Schema的單元測試
"""

@pytest.fixture
def mock_db(monkeypatch):
    test_conn = sqlite3.connect(":memory:", check_same_thread=False)
    test_conn.row_factory = sqlite3.Row
    cursor = test_conn.cursor()
    cursor.execute("""
        CREATE TABLE behavior_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT,
            end_time TEXT,
            duration_sec REAL,
            status TEXT,
            confidence REAL,
            ear_dist_ratio REAL,
            neck_len_ratio REAL,
            face_count INTEGER
        )
    """)
    # 插入測試資料
    cursor.execute("""
        INSERT INTO behavior_logs 
        (start_time, end_time, duration_sec, status, confidence, ear_dist_ratio, neck_len_ratio, face_count)
        VALUES (datetime('now'), datetime('now'), 15.5, 'GoodPosture', 0.95, 1.0, 1.0, 1)
    """)
    test_conn.commit()

    monkeypatch.setattr("src.api.get_db_connection", lambda: test_conn)
    yield test_conn
    test_conn.close()

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_get_latest_status(client, mock_db):
    response = client.get("/api/status/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "GoodPosture"
    assert data["duration_sec"] == 15.5
    assert data["face_count"] == 1

def test_get_history_logs(client, mock_db):
    response = client.get("/api/logs/history?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["total_returned"] == 1
    assert data["logs"][0]["status"] == "GoodPosture"

def test_get_daily_report(client, mock_db):
    response = client.get("/api/reports/daily")
    assert response.status_code == 200
    data = response.json()
    assert data["good_posture_seconds"] == 15.5
    assert data["health_score"] == 100.0
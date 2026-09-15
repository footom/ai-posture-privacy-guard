# -*- coding: utf-8 -*-
"""
database.py單元測試

注意：database.py在import時就把config.DB_FILE / config.REPORT_FILE
複製成模組內部的區域變數(`from config import DB_FILE, REPORT_FILE`)，
所以要重導向到暫存檔案時，必須monkeypatch`database.DB_FILE`，
monkeypatch`config.DB_FILE`是沒有用的(不會生效)。
"""
import sqlite3
import pandas as pd
import pytest

import database as db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """每個測試都用獨立的暫存SQLite檔，避免測試互相污染、也不動到真正的專案DB"""
    db_file = tmp_path / "test_behavior_logs.db"
    monkeypatch.setattr(db, "DB_FILE", str(db_file))
    db.init_db()
    return str(db_file)


@pytest.fixture
def temp_report(tmp_path, monkeypatch):
    report_file = tmp_path / "test_daily_report.txt"
    monkeypatch.setattr(db, "REPORT_FILE", str(report_file))
    return str(report_file)


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------
def test_init_db_creates_table(temp_db):
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='behavior_logs'")
    result = cursor.fetchone()
    conn.close()
    assert result is not None


def test_init_db_is_idempotent(temp_db):
    """重複呼叫init_db不該報錯或清空既有資料(CREATE TABLE IF NOT EXISTS)"""
    db.save_new_status("Good Posture", 40.0, 1.0, 1.0, 1)
    db.init_db()

    conn = sqlite3.connect(temp_db)
    count = conn.execute("SELECT COUNT(*) FROM behavior_logs").fetchone()[0]
    conn.close()
    assert count == 1


# ---------------------------------------------------------------------------
# save_new_status / update_previous_record
# ---------------------------------------------------------------------------
def test_save_new_status_returns_row_id(temp_db):
    row_id = db.save_new_status("Good Posture", 40.0, 1.0, 1.0, 1)
    assert row_id is not None
    assert row_id == 1


def test_save_new_status_persists_fields(temp_db):
    row_id = db.save_new_status("Slouching", 35.5, 0.9, 0.7, 1)
    conn = sqlite3.connect(temp_db)
    row = conn.execute(
        "SELECT status, confidence, ear_dist_ratio, neck_len_ratio, face_count FROM behavior_logs WHERE id=?",
        (row_id,)
    ).fetchone()
    conn.close()
    assert row == ("Slouching", 35.5, 0.9, 0.7, 1)


def test_update_previous_record_sets_duration(temp_db):
    row_id = db.save_new_status("Good Posture", 40.0, 1.0, 1.0, 1)
    db.update_previous_record(row_id, 12.34)

    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT duration_sec, end_time FROM behavior_logs WHERE id=?", (row_id,)).fetchone()
    conn.close()
    assert row[0] == 12.34
    assert row[1] is not None


def test_update_previous_record_with_none_row_id_is_noop(temp_db):
    # 不應丟例外，這是main.py第一次寫入時(last_row_id尚未存在)的正常情境
    db.update_previous_record(None, 5.0)


# ---------------------------------------------------------------------------
# calculate_health_score：純函式，不碰資料庫
# ---------------------------------------------------------------------------
class TestCalculateHealthScore:
    def test_empty_dataframe_returns_zero(self):
        assert db.calculate_health_score(pd.DataFrame()) == 0.0

    def test_none_returns_zero(self):
        assert db.calculate_health_score(None) == 0.0

    def test_all_good_posture_scores_100(self):
        df = pd.DataFrame({"status": ["Good Posture"] * 10})
        assert db.calculate_health_score(df) == 100.0

    def test_all_slouching_scores_zero_floor(self):
        df = pd.DataFrame({"status": ["Slouching"] * 10})
        # good=0 -> 0分, slouch佔比100% -> -20分，理論上是負的，但有下限保護在0
        assert db.calculate_health_score(df) == 0.0

    def test_mixed_statuses(self):
        df = pd.DataFrame({"status": ["Good Posture"] * 7 + ["Slouching"] * 2 + ["Too Close"] * 1})
        # good=70 - slouch(20%*20=4) - close(10%*15=1.5) = 64.5
        assert db.calculate_health_score(df) == 64.5

    def test_score_never_exceeds_100(self):
        df = pd.DataFrame({"status": ["Good Posture"] * 5})
        assert db.calculate_health_score(df) <= 100.0


# ---------------------------------------------------------------------------
# generate_daily_report
# ---------------------------------------------------------------------------
def test_generate_daily_report_creates_file_with_data(temp_db, temp_report):
    db.save_new_status("Good Posture", 40.0, 1.0, 1.0, 1)
    db.update_previous_record(1, 100.0)

    db.generate_daily_report()

    with open(temp_report, "r", encoding="utf-8") as f:
        content = f.read()
    assert "健康分數" in content
    assert "Good Posture" not in content or "良好坐姿" in content  # 報告用中文標籤


def test_generate_daily_report_skips_when_no_data_today(temp_db, temp_report):
    # 沒有任何資料時不該產生報告檔案
    db.generate_daily_report()
    import os
    assert not os.path.exists(temp_report)

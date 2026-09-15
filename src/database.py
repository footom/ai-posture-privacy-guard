import sqlite3
import os
from datetime import datetime
from config import DB_FILE, REPORT_FILE

def init_db():
    """初始化SQLite資料庫"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS behavior_logs(
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
    ''')
    conn.commit()
    conn.close()
    print("資料庫初始化成功。")

def save_new_status(status, confidence, ear_ratio, neck_ratio, face_count):
    """新增一筆狀態起始紀錄，返回該筆資料的row_id"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO behavior_logs (
                start_time, status, confidence, ear_dist_ratio, neck_len_ratio, face_count
            )
            VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?)
        """, (status, confidence, ear_ratio, neck_ratio, face_count))
        row_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return row_id
    except Exception as e:
        print(f"資料庫寫入失敗: {e}")
        return None

def update_previous_record(row_id, duration_sec):
    """更新上一次紀錄的結束時間與總持續秒數"""
    if row_id is None:
        return
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE behavior_logs
            SET end_time = datetime('now', 'localtime'),
                duration_sec = ?
            WHERE id = ?
        """, (round(duration_sec, 2), row_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"資料庫更新失敗: {e}")

def calculate_health_score(df):
    """計算每日健康分數"""
    if df is None or df.empty:
        return 0.0
    total = len(df)
    good = len(df[df.status == "Good Posture"])
    slouch = len(df[df.status == "Slouching"])
    close = len(df[df.status == "Too Close"])
    score = (good / total * 100) - (slouch / total * 20) - (close / total * 15)
    return round(max(0.0, min(score, 100.0)), 1)

def generate_daily_report():
    """關閉程式時，自動生成今日健康與資安文字報告"""
    if not os.path.exists(DB_FILE):
        return
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT status, duration_sec 
            FROM behavior_logs 
            WHERE date(start_time) = date('now', 'localtime')
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print("日誌報告：今日無行為數據，未生成報告。")
            return

        total_sec = 0
        status_durations = {
            "Good Posture": 0.0, "Too Close": 0.0, "Slouching": 0.0,
            "Risk (Spying)": 0.0, "Verifying": 0.0, "Unauthorized User": 0.0,
            "No Face Detected": 0.0
        }
        for status, duration in rows:
            dur = duration if duration is not None else 1.0
            if status in status_durations:
                status_durations[status] += dur
                total_sec += dur

        if total_sec == 0:
            total_sec = 1.0

        good_ratio = (status_durations["Good Posture"] / total_sec) * 100
        slouch_ratio = (status_durations["Slouching"] / total_sec) * 100
        close_ratio = (status_durations["Too Close"] / total_sec) * 100

        # 計算今日健康分數
        import pandas as pd
        temp_df = pd.DataFrame(rows, columns=['status', 'duration_sec'])
        score = calculate_health_score(temp_df)

        security_count = len([r for r in rows if r[0] in ["Risk (Spying)", "Unauthorized User"]])
        today_str = datetime.now().strftime("%Y-%m-%d")

        report_content = f"""==================================
 AI Posture && Privacy Guard每日健康與安全報告
 報告日期: {today_str}
==================================

【健康分數分析】
🏆今日健康分數 : {score} / 100 分

【姿勢時間佔比】
* 良好坐姿 (Good Posture)  : {good_ratio:.1f}% ({round(status_durations["Good Posture"])} 秒)
* 駝背狀態 (Slouching)     : {slouch_ratio:.1f}% ({round(status_durations["Slouching"])} 秒)
* 距離過近 (Too Close)     : {close_ratio:.1f}% ({round(status_durations["Too Close"])} 秒)

【資安防禦事件】
* 異常與入侵偵測事件次數  : {security_count} 次
* 螢幕無人時間 (No Face)  : {round(status_durations["No Face Detected"])} 秒

----------------------------------
系統提醒：適度起立活動、伸展背部，能有效維持工作專注力與身體健康！
"""
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"日誌報告：今日報告已生成至：{REPORT_FILE}")
    except Exception as e:
        print(f"報告生成失敗: {e}")
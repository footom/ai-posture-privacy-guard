import sqlite3
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

# 嘗試從config引入路徑，若無則採用專案預設位置
try:
    from src.config import DB_PATH
except ImportError:
    DB_PATH = "src/user_behavior_logs.db"

app = FastAPI(
    title="AI Posture & Privacy Guard API",
    description="邊緣端即時狀態檢索與行為日誌查詢 API 服務",
    version="1.0.0"
)

"""
AI Posture & Privacy Guard RESTful API服務
"""

# ---------------------------------------------------------
# Pydantic Response Models(資料模型定義)
# ---------------------------------------------------------
class StatusResponse(BaseModel):
    id: int
    start_time: str = Field(..., description="事件開始時間")
    end_time: Optional[str] = Field(None, description="事件結束時間")
    duration_sec: Optional[float] = Field(None, description="持續時間(秒)，若事件剛觸發可能為 None")
    status: str = Field(..., description="狀態 (如 GoodPosture, Slouching, TooClose, Risk)")
    confidence: Optional[float] = Field(None, description="模型信心度")
    ear_dist_ratio: Optional[float] = Field(None, description="耳距比例")
    neck_len_ratio: Optional[float] = Field(None, description="頸長比例")
    face_count: Optional[int] = Field(1, description="畫面中偵測到的人臉數")

class LogItem(BaseModel):
    id: int
    start_time: str
    end_time: Optional[str] = None
    duration_sec: Optional[float] = Field(None, description="持續時間(秒)")
    status: str
    confidence: Optional[float] = None
    ear_dist_ratio: Optional[float] = None
    neck_len_ratio: Optional[float] = None
    face_count: Optional[int] = None

class LogsResponse(BaseModel):
    total_returned: int
    logs: List[LogItem]

class DailyReportResponse(BaseModel):
    date: str
    health_score: float = Field(..., description="當日健康評分 (0~100)")
    good_posture_seconds: float = Field(..., description="良好坐姿累積秒數")
    bad_posture_seconds: float = Field(..., description="不良坐姿累積秒數")
    security_risk_count: int = Field(..., description="資安/偷窺觸發次數")
    summary: str = Field(..., description="健康狀態摘要建議")

# ---------------------------------------------------------
# 資料庫輔助連線
# ---------------------------------------------------------
def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # 允許用欄位名稱存取
        return conn
    except sqlite3.Error as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"無法連接本機資料庫: {str(e)}"
        )

# ---------------------------------------------------------
# 導向首頁 (避免造訪 127.0.0.1:8000 出現 404)
# ---------------------------------------------------------
@app.get("/", tags=["系統"])
def root():
    return {"message": "AI Posture & Privacy Guard API運作中，請至 /docs 查看Swagger介面"}

@app.get("/health", tags=["系統"])
def health_check():
    return {"status": "ok", "service": "AI Posture API"}

# ---------------------------------------------------------
# 1. 取得當前最新一筆狀態 API
# ---------------------------------------------------------
@app.get(
    "/api/status/latest",
    response_model=StatusResponse,
    summary="取得使用者最新即時狀態",
    tags=["即時狀態"]
)
def get_latest_status():
    """撈取 SQLite 中最新一筆行為紀錄"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, start_time, end_time, duration_sec, status, 
                   confidence, ear_dist_ratio, neck_len_ratio, face_count 
            FROM behavior_logs 
            ORDER BY id DESC LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="目前尚無任何行為監控紀錄"
            )
        return dict(row)
    finally:
        conn.close()

# ---------------------------------------------------------
# 2. 查詢歷史事件紀錄 API (支援分頁與狀態過濾)
# ---------------------------------------------------------
@app.get(
    "/api/logs/history",
    response_model=LogsResponse,
    summary="查詢歷史行為日誌",
    tags=["歷史紀錄"]
)
def get_history_logs(
    limit: int = Query(50, ge=1, le=500, description="單次查詢最大筆數"),
    status_filter: Optional[str] = Query(None, alias="status", description="依狀態過濾 (如 Slouching, Risk)"),
    days: Optional[int] = Query(None, ge=1, le=365, description="查詢最近幾天內的日誌 (若不填則撈全部最新紀錄)")
):
    """查詢歷史行為日誌，動態組合條件與參數"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        conditions = []
        params = []

        # 1. 天數過濾：有帶 days 才加入條件與參數
        if days is not None:
            cutoff_time = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            conditions.append("start_time >= ?")
            params.append(cutoff_time)

        # 2. 狀態過濾：有帶 status 才加入條件與參數
        if status_filter:
            conditions.append("status = ?")
            params.append(status_filter)

        # 組裝 WHERE 子句
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""

        # 組裝完整 SQL (最後加上 ORDER BY 與 LIMIT)
        query = f"""
            SELECT id, start_time, end_time, duration_sec, status, 
                   confidence, ear_dist_ratio, neck_len_ratio, face_count 
            FROM behavior_logs 
            {where_clause}
            ORDER BY id DESC 
            LIMIT ?
        """
        params.append(limit)

        # 執行查詢 (此時 SQL 的 ? 數量必然與 len(params) 完全一致)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        logs = [dict(r) for r in rows]
        return LogsResponse(total_returned=len(logs), logs=logs)
    finally:
        conn.close()

# ---------------------------------------------------------
# 3. 取得每日健康評分與報告摘要 API
# ---------------------------------------------------------
@app.get(
    "/api/reports/daily",
    response_model=DailyReportResponse,
    summary="取得特定日期之健康與資安報告",
    tags=["報表摘要"]
)
def get_daily_report(
    target_date: Optional[str] = Query(
        None, 
        description="查詢日期 (格式: YYYY-MM-DD)，預設為今日"
    )
):
    """
    依據當日紀錄之duration_sec累計良好與不良坐姿秒數，
    並結合face_count / status計算健康分數。
    """
    query_date = target_date if target_date else date.today().isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT status, duration_sec, face_count 
            FROM behavior_logs 
            WHERE date(start_time) = ?
            """,
            (query_date,)
        )
        rows = cursor.fetchall()

        if not rows:
            return DailyReportResponse(
                date=query_date,
                health_score=100.0,
                good_posture_seconds=0.0,
                bad_posture_seconds=0.0,
                security_risk_count=0,
                summary=f"{query_date} 尚無任何監控數據"
            )

        good_sec =sum((r["duration_sec"] or 0.0) for r in rows if r["status"] == "GoodPosture")
        bad_sec = sum((r["duration_sec"] or 0.0) for r in rows if r["status"] in ("Slouching", "TooClose"))
        risk_count = sum(1 for r in rows if r["status"] in ("Risk", "Unauthorized") or (r["face_count"] and r["face_count"] > 1))

        total_sec = good_sec + bad_sec
        base_score = round((good_sec / total_sec) * 100, 1) if total_sec > 0 else 100.0
        final_score = max(0.0, base_score - (risk_count * 5.0))

        summary_text = (
            f"當日良好姿勢累積 {round(good_sec, 1)} 秒；"
            f"不良姿勢累積 {round(bad_sec, 1)} 秒；"
            f"偵測到資安偷窺風險 {risk_count} 次。"
        )

        return DailyReportResponse(
            date=query_date,
            health_score=final_score,
            good_posture_seconds=round(good_sec, 1),
            bad_posture_seconds=round(bad_sec, 1),
            security_risk_count=risk_count,
            summary=summary_text
        )
    finally:
        conn.close()
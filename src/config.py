import os

# --- 路徑設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_MODEL_FILE = os.path.join(BASE_DIR, "owner_lbph_model.yml")
DB_FILE = os.path.join(BASE_DIR, "user_behavior_logs.db")
REPORT_FILE = os.path.join(BASE_DIR, "daily_report.txt")

# --- 監控參數設定 ---
BAD_POSTURE_THRESHOLD_SEC = 3      # 坐姿不良維持秒數觸發警告
SPY_THRESHOLD_SEC = 10             # 安全風險維持10秒觸發鎖定
NOFACE_GRACE_SEC = 1.0             # 人臉瞬時丟失的容忍秒數
COOLDOWN_AFTER_LOCK_SEC = 5.0      # 解除鎖定後的防重複觸發保護冷卻

# --- 坐姿判斷相對比例門檻 ---
TOO_CLOSE_RATIO = 1.35             # ear_distance超過baseline比例
SLOUCH_RATIO = 0.75                # neck_len低於baseline比例
ADAPTIVE_ALPHA = 0.05              # 自適應學習率

# --- 省電設定 ---
ENABLE_BACKGROUND_BLUR = False     # 設為False關閉去背模型
SEGMENT_FRAME_INTERVAL = 5         # 去背遮罩更新頻率

# --- 數據平滑濾波 (EMA) ---
EMA_ALPHA = 0.2

# --- FaceID風格無死角註冊參數 ---
REQUIRED_ZONES = ["front", "right", "down", "left", "up"]
ZONE_LABELS = {
    "front": "Look straight at the camera",
    "right": "Slowly turn your head to the RIGHT",
    "left": "Slowly turn your head to the LEFT",
    "up": "Slowly tilt your head UP",
    "down": "Slowly tilt your head DOWN",
}
YAW_THRESH = 0.25
PITCH_UP_THRESH = 0.40
PITCH_DOWN_THRESH = 0.62
ZONE_STABLE_FRAMES = 5
ZONE_CAPTURE_COOLDOWN_SEC = 0.6

# --- 未授權判定 ---
UNAUTH_CONFIRM_FRAMES = 5
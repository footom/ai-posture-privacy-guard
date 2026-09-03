import math
import time
from datetime import datetime
import config as cfg
import database as db


class BehaviorTracker:
    def __init__(self):
        # 數據平滑濾波狀態
        self.smoothed_ear_distance = None
        self.smoothed_neck_length = None

        # 姿勢基準線
        self.posture_baseline = {"ear_distance": None, "neck_len": None}
        self.baseline_calibrated = False

        # 計時狀態
        self.bad_posture_start_time = None
        self.security_risk_start_time = None
        self.last_lock_time = 0
        self.noface_start_time = None
        self.unauth_frame_counter = 0
        self.last_spy_time = 0

        # 資料庫狀態追蹤
        self.last_saved_status = None
        self.current_status_start_time = datetime.now()
        self.last_row_id = None

        # 狀態緩存
        self.cached_status_text = "Good Posture"
        self.cached_text_color = (0, 255, 0)

    def process_ema_and_baseline(self, current_ear_distance, current_neck_length):
        """計算EMA平滑值與自適應Baseline調整"""
        if self.smoothed_ear_distance is None:
            self.smoothed_ear_distance = current_ear_distance
            self.smoothed_neck_length = current_neck_length
        else:
            self.smoothed_ear_distance = (cfg.EMA_ALPHA * current_ear_distance +
                                          (1 - cfg.EMA_ALPHA) * self.smoothed_ear_distance)
            self.smoothed_neck_length = (cfg.EMA_ALPHA * current_neck_length +
                                         (1 - cfg.EMA_ALPHA) * self.smoothed_neck_length)

        # 初始基準校正
        if not self.baseline_calibrated:
            self.posture_baseline["ear_distance"] = self.smoothed_ear_distance
            self.posture_baseline["neck_len"] = self.smoothed_neck_length
            self.baseline_calibrated = True
            print(f"健康校正初始基準：耳距={self.smoothed_ear_distance:.1f}, 頸長={self.smoothed_neck_length:.1f}")
            return

        # 自適應調整 Baseline
        self.posture_baseline["ear_distance"] = (self.posture_baseline["ear_distance"] * (1 - cfg.ADAPTIVE_ALPHA) +
                                                 self.smoothed_ear_distance * cfg.ADAPTIVE_ALPHA)
        self.posture_baseline["neck_len"] = (self.posture_baseline["neck_len"] * (1 - cfg.ADAPTIVE_ALPHA) +
                                             self.smoothed_neck_length * cfg.ADAPTIVE_ALPHA)

    def get_posture_status(self):
        """根據比例門檻判定坐姿狀態"""
        if not self.baseline_calibrated:
            return "Good Posture", (0, 255, 0)

        if self.smoothed_ear_distance > self.posture_baseline["ear_distance"] * cfg.TOO_CLOSE_RATIO:
            return "Too Close", (0, 0, 255)
        elif self.smoothed_neck_length < self.posture_baseline["neck_len"] * cfg.SLOUCH_RATIO:
            return "Slouching", (0, 165, 255)
        return "Good Posture", (0, 255, 0)

    def update_spy_flag(self, face_count, curr_frame_time, buffer_sec=1.0):
        """
        多人入鏡的防閃爍緩衝：一旦偵測到2人以上就記錄時間戳，
        在buffer_sec秒內即使暫時只偵測到1人/0人，仍視為Spying狀態，
        避免MediaPipe單幀漏偵測造成畫面狀態閃爍。
        回傳目前是否應判定為Spying。
        """
        if face_count > 1:
            self.last_spy_time = curr_frame_time
        return (curr_frame_time - self.last_spy_time) < buffer_sec

    def classify_identity_status(self, face_count, is_spying, curr_frame_time,
                                  has_face_roi=True, label=None, confidence=None,
                                  recognized_label=1, confidence_threshold=65):
        """
        根據人臉數量與辨識結果，判定當前的身份/在場狀態(不含坐姿分析)。

        這是Verifying狀態機的核心：未授權使用者需連續
        cfg.UNAUTH_CONFIRM_FRAMES幀都判定失敗，才會從Verifying
        升級為Unauthorized User，避免單幀誤判(光線/角度)直接
        被標記成Good Posture並重置資安計時器。

        參數：
            face_count:當前畫面偵測到的人臉數
            is_spying:是否已由 update_spy_flag() 判定為多人入鏡
            curr_frame_time:目前幀的時間戳(time.time())
            has_face_roi:face_count==1時，該人臉框是否有效(寬高>0)
            label, confidence:LBPH辨識器的預測結果(僅face_count==1且has_face_roi時需要)
            recognized_label/confidence_threshold:判定為本人的標準

        回傳：
            (status_text, text_color)
        """
        if is_spying:
            self.unauth_frame_counter = 0
            self.noface_start_time = None
            status_text, text_color = "Risk (Spying)", (255, 0, 255)

        elif face_count == 1:
            self.noface_start_time = None
            if has_face_roi:
                if label == recognized_label and confidence is not None and confidence <= confidence_threshold:
                    self.unauth_frame_counter = 0
                    status_text, text_color = "Good Posture", (0, 255, 0)
                else:
                    self.unauth_frame_counter += 1
                    if self.unauth_frame_counter >= cfg.UNAUTH_CONFIRM_FRAMES:
                        status_text, text_color = "Unauthorized User", (0, 0, 128)
                    else:
                        status_text, text_color = "Verifying", (0, 200, 200)
            else:
                status_text, text_color = "Verifying", (0, 200, 200)

        else:  # face_count == 0
            self.unauth_frame_counter = 0
            if self.noface_start_time is None:
                self.noface_start_time = curr_frame_time

            if curr_frame_time - self.noface_start_time >= cfg.NOFACE_GRACE_SEC:
                status_text, text_color = "No Face Detected", (0, 255, 255)
            else:
                # 尚在容忍期內，維持前一個快取狀態，不更新快取
                return self.cached_status_text, self.cached_text_color

        self.cached_status_text = status_text
        self.cached_text_color = text_color
        return status_text, text_color

    def get_face_proximity_status(self, face_w, frame_w):
        """
        雙重防線：當臉部距離近到Pose模型無法運作時，
        直接透過人臉框寬度佔畫面的比例判定是否太近。
        若臉寬大於畫面寬度的55%，即視為Too Close。
        """
        ratio = face_w / frame_w
        if ratio > 0.55:
            return "Too Close", (0, 0, 255)
        return "Good Posture", (0, 255, 0)

    def update_database_status(self, status_text, current_confidence, face_count):
        """處理狀態改變時的SQLite資料庫更新與寫入"""
        if status_text != self.last_saved_status:
            now_dt = datetime.now()
            # 1.更新上一個紀錄
            if self.last_row_id is not None:
                duration = (now_dt - self.current_status_start_time).total_seconds()
                db.update_previous_record(self.last_row_id, duration)

            # 2.計算比例
            e_ratio = None
            n_ratio = None
            if self.posture_baseline["ear_distance"] and self.smoothed_ear_distance:
                e_ratio = round(self.smoothed_ear_distance / self.posture_baseline["ear_distance"], 3)
            if self.posture_baseline["neck_len"] and self.smoothed_neck_length:
                n_ratio = round(self.smoothed_neck_length / self.posture_baseline["neck_len"], 3)

            # 3.儲存新狀態
            self.last_row_id = db.save_new_status(
                status_text, current_confidence, e_ratio, n_ratio, face_count
            )
            self.current_status_start_time = now_dt
            self.last_saved_status = status_text
            print(f"資料庫狀態切換: {status_text}")
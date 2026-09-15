# -*- coding: utf-8 -*-
"""
tracker.py單元測試

重點測試對象：classify_identity_status()，這是修復過的核心狀態機——
未授權使用者必須連續UNAUTH_CONFIRM_FRAMES幀判定失敗，才會從
"Verifying"升級為"Unauthorized User"，藉此避免單幀誤判(光線、
角度)被直接標記成"Good Posture"並重置資安計時器。
"""
import pytest
import config as cfg
from tracker import BehaviorTracker


@pytest.fixture
def tracker():
    return BehaviorTracker()


# ---------------------------------------------------------------------------
# classify_identity_status:Spying(多人入鏡)
# ---------------------------------------------------------------------------
class TestClassifyIdentitySpying:
    def test_is_spying_returns_risk_status(self, tracker):
        status, color = tracker.classify_identity_status(
            face_count=2, is_spying=True, curr_frame_time=100.0
        )
        assert status == "Risk (Spying)"
        assert color == (255, 0, 255)

    def test_spying_resets_unauth_counter_and_noface_timer(self, tracker):
        tracker.unauth_frame_counter = 3
        tracker.noface_start_time = 50.0

        tracker.classify_identity_status(face_count=2, is_spying=True, curr_frame_time=100.0)

        assert tracker.unauth_frame_counter == 0
        assert tracker.noface_start_time is None

    def test_spying_updates_cache(self, tracker):
        tracker.classify_identity_status(face_count=2, is_spying=True, curr_frame_time=100.0)
        assert tracker.cached_status_text == "Risk (Spying)"
        assert tracker.cached_text_color == (255, 0, 255)


# ---------------------------------------------------------------------------
# classify_identity_status:單一人臉，本人辨識成功
# ---------------------------------------------------------------------------
class TestClassifyIdentityRecognizedOwner:
    def test_recognized_owner_is_good_posture(self, tracker):
        status, color = tracker.classify_identity_status(
            face_count=1, is_spying=False, curr_frame_time=100.0,
            has_face_roi=True, label=1, confidence=40.0
        )
        assert status == "Good Posture"
        assert color == (0, 255, 0)

    def test_confidence_exactly_at_threshold_is_owner(self, tracker):
        # confidence <= 65才算本人，65剛好是邊界
        status, _ = tracker.classify_identity_status(
            face_count=1, is_spying=False, curr_frame_time=100.0,
            has_face_roi=True, label=1, confidence=65.0
        )
        assert status == "Good Posture"

    def test_recognized_owner_resets_unauth_counter(self, tracker):
        tracker.unauth_frame_counter = 4
        tracker.classify_identity_status(
            face_count=1, is_spying=False, curr_frame_time=100.0,
            has_face_roi=True, label=1, confidence=30.0
        )
        assert tracker.unauth_frame_counter == 0


# ---------------------------------------------------------------------------
# classify_identity_status:最核心的回歸測試 ——
# 單幀辨識失敗不該直接變成Unauthorized，也絕對不該變成Good Posture
# ---------------------------------------------------------------------------
class TestVerifyingStateMachine:
    def test_single_failed_frame_is_verifying_not_unauthorized(self, tracker):
        """對應曾修復過的bug：單幀誤判不應直接標記為Unauthorized或Good Posture"""
        status, color = tracker.classify_identity_status(
            face_count=1, is_spying=False, curr_frame_time=100.0,
            has_face_roi=True, label=0, confidence=80.0
        )
        assert status == "Verifying"
        assert color == (0, 200, 200)
        assert status != "Good Posture"
        assert status != "Unauthorized User"

    def test_confidence_above_threshold_is_verifying(self, tracker):
        # label正確但confidence超過閾值，仍算辨識失敗
        status, _ = tracker.classify_identity_status(
            face_count=1, is_spying=False, curr_frame_time=100.0,
            has_face_roi=True, label=1, confidence=65.1
        )
        assert status == "Verifying"

    def test_escalates_to_unauthorized_after_confirm_frames(self, tracker):
        """連續失敗達UNAUTH_CONFIRM_FRAMES幀才升級為Unauthorized User"""
        last_status = None
        for i in range(cfg.UNAUTH_CONFIRM_FRAMES):
            last_status, _ = tracker.classify_identity_status(
                face_count=1, is_spying=False, curr_frame_time=100.0 + i,
                has_face_roi=True, label=0, confidence=90.0
            )
            if i < cfg.UNAUTH_CONFIRM_FRAMES - 1:
                assert last_status == "Verifying", f"第{i+1}幀不該提早升級"

        assert last_status == "Unauthorized User"
        assert tracker.unauth_frame_counter == cfg.UNAUTH_CONFIRM_FRAMES

    def test_success_frame_in_the_middle_resets_counter(self, tracker):
        """驗證中途出現一幀本人成功辨識，counter要歸零，不能延續之前的失敗次數"""
        for _ in range(cfg.UNAUTH_CONFIRM_FRAMES - 1):
            tracker.classify_identity_status(
                face_count=1, is_spying=False, curr_frame_time=100.0,
                has_face_roi=True, label=0, confidence=90.0
            )
        assert tracker.unauth_frame_counter == cfg.UNAUTH_CONFIRM_FRAMES - 1

        # 中途混入一幀本人成功
        status, _ = tracker.classify_identity_status(
            face_count=1, is_spying=False, curr_frame_time=100.0,
            has_face_roi=True, label=1, confidence=30.0
        )
        assert status == "Good Posture"
        assert tracker.unauth_frame_counter == 0

    def test_no_face_roi_is_verifying(self, tracker):
        """人臉框寬高無效(fw<=0 or fh<=0)時應視為Verifying，而非直接放行"""
        status, color = tracker.classify_identity_status(
            face_count=1, is_spying=False, curr_frame_time=100.0,
            has_face_roi=False
        )
        assert status == "Verifying"
        assert color == (0, 200, 200)


# ---------------------------------------------------------------------------
# classify_identity_status: 無人臉 + 容忍期(grace period)
# ---------------------------------------------------------------------------
class TestNoFaceGracePeriod:
    def test_no_face_within_grace_period_keeps_cached_status(self, tracker):
        tracker.cached_status_text = "Good Posture"
        tracker.cached_text_color = (0, 255, 0)

        status, color = tracker.classify_identity_status(
            face_count=0, is_spying=False, curr_frame_time=100.0
        )
        # 剛丟臉的第一幀，還在容忍期內，維持原本快取狀態
        assert status == "Good Posture"
        assert color == (0, 255, 0)
        assert tracker.noface_start_time == 100.0

    def test_no_face_after_grace_period_becomes_no_face_detected(self, tracker):
        tracker.cached_status_text = "Good Posture"
        tracker.classify_identity_status(face_count=0, is_spying=False, curr_frame_time=100.0)

        status, color = tracker.classify_identity_status(
            face_count=0, is_spying=False,
            curr_frame_time=100.0 + cfg.NOFACE_GRACE_SEC
        )
        assert status == "No Face Detected"
        assert color == (0, 255, 255)

    def test_no_face_resets_unauth_counter(self, tracker):
        tracker.unauth_frame_counter = 3
        tracker.classify_identity_status(face_count=0, is_spying=False, curr_frame_time=100.0)
        assert tracker.unauth_frame_counter == 0

    def test_face_reappearing_resets_noface_timer(self, tracker):
        tracker.classify_identity_status(face_count=0, is_spying=False, curr_frame_time=100.0)
        assert tracker.noface_start_time == 100.0

        tracker.classify_identity_status(
            face_count=1, is_spying=False, curr_frame_time=101.0,
            has_face_roi=True, label=1, confidence=30.0
        )
        assert tracker.noface_start_time is None


# ---------------------------------------------------------------------------
# classify_identity_status: 記錄目前程式碼對呼叫端的隱含假設
# ---------------------------------------------------------------------------
class TestClassifyIdentityContractAssumption:
    def test_multi_face_without_spy_flag_falls_into_noface_branch(self, tracker):
        """
        警示性測試：這不是理想行為，而是記錄目前程式碼的實際假設——
        呼叫端必須保證face_count>1 時is_spying一定是True
        (即必須先呼叫update_spy_flag())。正常流程下這個假設會成立，
        但函式本身沒有防禦這個情況。若未來想讓classify_identity_status
        自己防禦(例如face_count>1時直接視為Spying)，這個測試就該跟著改。
        """
        status, _ = tracker.classify_identity_status(
            face_count=2, is_spying=False, curr_frame_time=100.0
        )
        # 目前實作下會被誤判成face_count==0分支，而不是Spying
        assert status != "Risk (Spying)"


# ---------------------------------------------------------------------------
# update_spy_flag:多人入鏡防閃爍緩衝
# ---------------------------------------------------------------------------
class TestUpdateSpyFlag:
    def test_multiple_faces_triggers_spying(self, tracker):
        assert tracker.update_spy_flag(face_count=2, curr_frame_time=100.0, buffer_sec=1.0) is True

    def test_single_face_within_buffer_still_spying(self, tracker):
        tracker.update_spy_flag(face_count=2, curr_frame_time=100.0, buffer_sec=1.0)
        # 0.5秒後只偵測到1張臉，仍在1秒緩衝內
        assert tracker.update_spy_flag(face_count=1, curr_frame_time=100.5, buffer_sec=1.0) is True

    def test_single_face_after_buffer_not_spying(self, tracker):
        tracker.update_spy_flag(face_count=2, curr_frame_time=100.0, buffer_sec=1.0)
        # 1.5秒後超過緩衝時間
        assert tracker.update_spy_flag(face_count=1, curr_frame_time=101.5, buffer_sec=1.0) is False

    def test_no_prior_spying_is_not_spying(self, tracker):
        assert tracker.update_spy_flag(face_count=1, curr_frame_time=100.0, buffer_sec=1.0) is False


# ---------------------------------------------------------------------------
# get_face_proximity_status
# ---------------------------------------------------------------------------
class TestFaceProximityStatus:
    def test_face_width_over_threshold_is_too_close(self, tracker):
        status, color = tracker.get_face_proximity_status(face_w=400, frame_w=640)  # 62.5%
        assert status == "Too Close"
        assert color == (0, 0, 255)

    def test_face_width_under_threshold_is_good_posture(self, tracker):
        status, color = tracker.get_face_proximity_status(face_w=200, frame_w=640)  # 31%
        assert status == "Good Posture"
        assert color == (0, 255, 0)

    def test_boundary_at_55_percent(self, tracker):
        status, _ = tracker.get_face_proximity_status(face_w=352, frame_w=640)  # 剛好55%
        assert status == "Good Posture"  # 門檻是 >0.55 才算太近，等於不算


# ---------------------------------------------------------------------------
# process_ema_and_baseline / get_posture_status
# ---------------------------------------------------------------------------
class TestPostureBaseline:
    def test_first_frame_sets_initial_baseline(self, tracker):
        tracker.process_ema_and_baseline(current_ear_distance=100.0, current_neck_length=50.0)
        assert tracker.baseline_calibrated is True
        assert tracker.posture_baseline["ear_distance"] == 100.0
        assert tracker.posture_baseline["neck_len"] == 50.0

    def test_status_before_calibration_is_good_posture(self, tracker):
        status, color = tracker.get_posture_status()
        assert status == "Good Posture"
        assert color == (0, 255, 0)

    def test_too_close_when_ear_distance_grows(self, tracker):
        tracker.process_ema_and_baseline(100.0, 50.0)
        # 直接操縱平滑值來模擬靠太近，避開EMA收斂速度的干擾
        tracker.smoothed_ear_distance = tracker.posture_baseline["ear_distance"] * (cfg.TOO_CLOSE_RATIO + 0.1)
        status, color = tracker.get_posture_status()
        assert status == "Too Close"
        assert color == (0, 0, 255)

    def test_slouching_when_neck_shrinks(self, tracker):
        tracker.process_ema_and_baseline(100.0, 50.0)
        tracker.smoothed_neck_length = tracker.posture_baseline["neck_len"] * (cfg.SLOUCH_RATIO - 0.1)
        status, color = tracker.get_posture_status()
        assert status == "Slouching"
        assert color == (0, 165, 255)

    def test_too_close_takes_priority_over_slouching(self, tracker):
        """兩個條件同時成立時，Too Close的判斷順序在前，應優先回傳"""
        tracker.process_ema_and_baseline(100.0, 50.0)
        tracker.smoothed_ear_distance = tracker.posture_baseline["ear_distance"] * (cfg.TOO_CLOSE_RATIO + 0.1)
        tracker.smoothed_neck_length = tracker.posture_baseline["neck_len"] * (cfg.SLOUCH_RATIO - 0.1)
        status, _ = tracker.get_posture_status()
        assert status == "Too Close"


# ---------------------------------------------------------------------------
# update_database_status:只驗證「有沒有正確呼叫DB層」，不驗證DB本身
# 用monkeypatch換掉tracker.db.save_new_status / update_previous_record，
# 確保這裡是純粹的單元測試，不會真的去寫SQLite檔案。
# ---------------------------------------------------------------------------
class TestUpdateDatabaseStatus:
    def test_status_change_saves_new_record(self, tracker, monkeypatch):
        calls = {}

        def fake_save_new_status(status, confidence, e_ratio, n_ratio, face_count):
            calls["save"] = (status, confidence, e_ratio, n_ratio, face_count)
            return 1

        monkeypatch.setattr("tracker.db.save_new_status", fake_save_new_status)

        tracker.update_database_status("Good Posture", 40.0, 1)

        assert calls["save"][0] == "Good Posture"
        assert tracker.last_saved_status == "Good Posture"
        assert tracker.last_row_id == 1

    def test_same_status_does_not_trigger_new_save(self, tracker, monkeypatch):
        save_count = {"n": 0}
        monkeypatch.setattr("tracker.db.save_new_status", lambda *a, **k: save_count.__setitem__("n", save_count["n"] + 1) or 1)
        monkeypatch.setattr("tracker.db.update_previous_record", lambda *a, **k: None)

        tracker.update_database_status("Good Posture", 40.0, 1)
        tracker.update_database_status("Good Posture", 42.0, 1)  # 狀態沒變

        assert save_count["n"] == 1

    def test_status_change_updates_previous_record_duration(self, tracker, monkeypatch):
        monkeypatch.setattr("tracker.db.save_new_status", lambda *a, **k: 1)
        update_calls = []
        monkeypatch.setattr("tracker.db.update_previous_record", lambda row_id, duration: update_calls.append((row_id, duration)))

        tracker.update_database_status("Good Posture", 40.0, 1)
        tracker.update_database_status("Too Close", 40.0, 1)  # 狀態改變，觸發前一筆的收尾

        assert len(update_calls) == 1
        assert update_calls[0][0] == 1

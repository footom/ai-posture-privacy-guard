import cv2
import time
import threading
import ctypes
import os
import numpy as np
import platform
import psutil

# 導入自訂模組
import config as cfg
import database as db
import models as md
import gui
from tracker import BehaviorTracker

# 全域控制變數
running = True
has_model = False
registration_faces = []
icon = None

# 初始化追蹤器
tracker = BehaviorTracker()

# 畫面繪製長條圖用
stats_counts = {
    "Good Posture": 0, "Too Close": 0, "Slouching": 0,
    "Risk (Spying)": 0, "Verifying": 0, "Unauthorized User": 0,
    "No Face Detected": 0
}

def draw_realtime_chart(frame, counts, frame_w, frame_h):
    total = sum(counts.values())
    if total == 0:
        return
    start_x = frame_w - 260
    start_y = 20
    overlay = frame.copy()
    cv2.rectangle(overlay, (start_x - 10, start_y - 10), (frame_w - 10, start_y + 235), (40, 40, 40), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    labels = ["Good", "Close", "Slouch", "Spy", "Verify", "Unauth", "NoFace"]
    keys = ["Good Posture", "Too Close", "Slouching", "Risk (Spying)", "Verifying", "Unauthorized User", "No Face Detected"]
    colors = [(0, 255, 0), (0, 0, 255), (0, 165, 255), (255, 0, 255), (0, 200, 200), (0, 0, 128), (0, 255, 255)]

    for i, (key, label, color) in enumerate(zip(keys, labels, colors)):
        percentage = counts[key] / total
        bar_width = int(percentage * 100)
        y_pos = start_y + (i * 32)
        cv2.putText(frame, f"{label}:", (start_x, y_pos + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        if bar_width > 0:
            cv2.rectangle(frame, (start_x + 75, y_pos + 5), (start_x + 75 + bar_width, y_pos + 20), color, -1)
        cv2.putText(frame, f"{int(percentage * 100)}%", (start_x + 80 + bar_width, y_pos + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

def draw_registration_progress_ring(frame, captured_zones, current_zone):
    h, w, _ = frame.shape
    center = (w - 90, 110)
    radius = 55
    n = len(cfg.REQUIRED_ZONES)
    segment_angle = 360.0 / n
    start_angle = -90.0

    for i, zone in enumerate(cfg.REQUIRED_ZONES):
        a0 = start_angle + i * segment_angle + 4
        a1 = start_angle + (i + 1) * segment_angle - 4
        if zone in captured_zones:
            color, thickness = (0, 255, 0), 8
        elif zone == current_zone:
            color, thickness = (0, 255, 255), 8
        else:
            color, thickness = (90, 90, 90), 5
        cv2.ellipse(frame, center, (radius, radius), 0, a0, a1, color, thickness)

    cv2.putText(frame, f"{len(captured_zones)}/{n}", (center[0] - 22, center[1] + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

def monitor_loop():
    global running, has_model, registration_faces, icon

    has_model = md.load_face_model()
    db.init_db()

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    last_stat_time = time.time()
    last_capture_time = 0
    captured_zones = set()
    zone_stable_tracker = {"zone": None, "count": 0}
    frame_count_for_seg = 0
    cached_condition = None
    mesh_released = False

    prev_frame_time = time.time()
    fps = 0.0
    process = psutil.Process(os.getpid())
    cpu_usage = 0.0
    ram_usage_mb = 0.0
    last_sys_check_time = 0
    
    # 防閃爍緩衝時間變數
    last_spy_time = 0
    SPY_BUFFER_SEC = 1.0 

    while running:
        if not cap.isOpened():
            cap = cv2.VideoCapture(0)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            time.sleep(0.5)
            continue

        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            continue

        curr_frame_time = time.time()
        time_diff = curr_frame_time - prev_frame_time
        if time_diff > 0:
            fps = 0.9 * fps + 0.1 * (1.0 / time_diff) if fps > 0 else (1.0 / time_diff)
        prev_frame_time = curr_frame_time

        if curr_frame_time - last_sys_check_time > 0.5:
            cpu_usage = process.cpu_percent(interval=None) / psutil.cpu_count()
            ram_usage_mb = process.memory_info().rss / (1024 * 1024)
            last_sys_check_time = curr_frame_time

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        rgb_small = cv2.resize(rgb_frame, (320, 240))
        detection_results = md.face_detector.process(rgb_small)
        faces = md.get_faces_from_mediapipe(detection_results, w, h)
        face_count = len(faces)

        # --- 1.註冊模式 ---
        if not has_model:
            output_frame = frame.copy()
            mesh_results = md.face_mesh.process(rgb_frame)
            current_zone = None
            if mesh_results.multi_face_landmarks:
                current_zone = md.classify_face_zone(mesh_results.multi_face_landmarks[0], w, h)

            if face_count != 1:
                reg_prompt_text = "Please make sure only your face is visible..."
            elif current_zone in captured_zones:
                reg_prompt_text = "Great! Now move to another angle..."
            elif current_zone:
                reg_prompt_text = cfg.ZONE_LABELS[current_zone]
            else:
                reg_prompt_text = "Please face the camera..."

            cv2.rectangle(output_frame, (20, 20), (560, 85), (0, 0, 0), -1)
            cv2.putText(output_frame, "REGISTRATION MODE: Full-Coverage Face Scan", (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            cv2.putText(output_frame, reg_prompt_text, (30, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

            draw_registration_progress_ring(output_frame, captured_zones, current_zone)

            now = time.time()
            if face_count == 1 and current_zone and current_zone not in captured_zones:
                if zone_stable_tracker["zone"] == current_zone:
                    zone_stable_tracker["count"] += 1
                else:
                    zone_stable_tracker["zone"] = current_zone
                    zone_stable_tracker["count"] = 1

                if (zone_stable_tracker["count"] >= cfg.ZONE_STABLE_FRAMES and now - last_capture_time > cfg.ZONE_CAPTURE_COOLDOWN_SEC):
                    x, y, fw, fh = faces[0]
                    if fw > 0 and fh > 0:
                        face_roi = gray_frame[y:y + fh, x:x + fw]
                        registration_faces.append(face_roi)
                        captured_zones.add(current_zone)
                        last_capture_time = now
                        zone_stable_tracker["count"] = 0
                        print(f"已擷取角度「{current_zone}」（{len(captured_zones)}/{len(cfg.REQUIRED_ZONES)}）")

                    if len(captured_zones) == len(cfg.REQUIRED_ZONES):
                        labels = np.array([1] * len(registration_faces))
                        md.recognizer.train(registration_faces, labels)
                        md.recognizer.save(cfg.USER_MODEL_FILE)
                        has_model = True
                        print("註冊成功，模型已儲存。")
            else:
                zone_stable_tracker["count"] = 0

            cv2.putText(output_frame, f"FPS: {fps:.1f} | CPU: {cpu_usage:.1f}% | RAM: {ram_usage_mb:.1f}MB",
                        (20, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

            cv2.imshow('AI Posture && Privacy Guard Pro (OpenCV Edge)', output_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                on_quit(icon)
            continue

        if not mesh_released and has_model:
            md.face_mesh.close()
            mesh_released = True

        # 去背運算
        if cfg.ENABLE_BACKGROUND_BLUR and md.selfie is not None:
            if frame_count_for_seg % cfg.SEGMENT_FRAME_INTERVAL == 0 or cached_condition is None:
                selfie_results = md.selfie.process(rgb_frame)
                if selfie_results.segmentation_mask is not None:
                    mask = selfie_results.segmentation_mask
                    cached_condition = np.stack((mask,) * 3, axis=-1) > 0.5
            frame_count_for_seg += 1
            output_frame = np.where(cached_condition, frame, cv2.GaussianBlur(frame, (55, 55), 0)) if cached_condition is not None else frame.copy()
        else:
            output_frame = frame.copy()

        # --- 2.核心狀態判定 ---
        status_text = "Good Posture"
        text_color = (0, 255, 0)
        current_confidence = None

        if face_count > 1:
            last_spy_time = curr_frame_time
            
        is_spying = (curr_frame_time - last_spy_time) < SPY_BUFFER_SEC

        if is_spying:
            status_text = "Risk (Spying)"
            text_color = (255, 0, 255)
            tracker.unauth_frame_counter = 0
            tracker.noface_start_time = None
            tracker.cached_status_text = status_text
            tracker.cached_text_color = text_color
        elif face_count == 1:
            tracker.noface_start_time = None
            x, y, fw, fh = faces[0]
            if fw > 0 and fh > 0:
                face_roi = gray_frame[y:y + fh, x:x + fw]
                label, confidence = md.recognizer.predict(face_roi)
                current_confidence = round(confidence, 2)

                if label == 1 and confidence <= 65:
                    tracker.unauth_frame_counter = 0
                    status_text = "Good Posture"
                    text_color = (0, 255, 0)
                else:
                    tracker.unauth_frame_counter += 1
                    if tracker.unauth_frame_counter >= cfg.UNAUTH_CONFIRM_FRAMES:
                        status_text = "Unauthorized User"
                        text_color = (0, 0, 128)
                    else:
                        status_text = "Verifying"
                        text_color = (0, 200, 200)
            else:
                status_text = "Verifying"
                text_color = (0, 200, 200)
            tracker.cached_status_text = status_text
            tracker.cached_text_color = text_color
        else:
            tracker.unauth_frame_counter = 0
            if tracker.noface_start_time is None:
                tracker.noface_start_time = curr_frame_time

            if curr_frame_time - tracker.noface_start_time >= cfg.NOFACE_GRACE_SEC:
                status_text = "No Face Detected"
                text_color = (0, 255, 255)
                tracker.cached_status_text = status_text
                tracker.cached_text_color = text_color
            else:
                status_text = tracker.cached_status_text
                text_color = tracker.cached_text_color

        # --- 3.坐姿與近距離分析 ---
        if status_text == "Good Posture":
            if face_count == 1:
                xf, yf, wf, hf = faces[0]
                status_text, text_color = tracker.get_face_proximity_status(wf, w)

            if status_text == "Good Posture":
                pose_results = md.pose.process(rgb_small)
                if pose_results.pose_landmarks:
                    landmarks = pose_results.pose_landmarks.landmark
                    left_ear = landmarks[md.mp_pose.PoseLandmark.LEFT_EAR]
                    right_ear = landmarks[md.mp_pose.PoseLandmark.RIGHT_EAR]
                    left_shoulder = landmarks[md.mp_pose.PoseLandmark.LEFT_SHOULDER]
                    right_shoulder = landmarks[md.mp_pose.PoseLandmark.RIGHT_SHOULDER]

                    cur_ear_dist = np.hypot((left_ear.x - right_ear.x) * w, (left_ear.y - right_ear.y) * h)
                    cur_neck_len = ((left_shoulder.y + right_shoulder.y) / 2 * h) - ((left_ear.y + right_ear.y) / 2 * h)

                    tracker.process_ema_and_baseline(cur_ear_dist, cur_neck_len)
                    status_text, text_color = tracker.get_posture_status()
                    md.mp_drawing.draw_landmarks(output_frame, pose_results.pose_landmarks, md.mp_pose.POSE_CONNECTIONS)

        current_time = time.time()
        if current_time - last_stat_time >= 0.5:
            stats_counts[status_text] += 1
            last_stat_time = current_time

        # 警報邏輯
        if current_time - tracker.last_lock_time < cfg.COOLDOWN_AFTER_LOCK_SEC:
            tracker.security_risk_start_time = None
            tracker.bad_posture_start_time = None
            tracker.unauth_frame_counter = 0
            tracker.noface_start_time = None
        else:
            if status_text in ["Risk (Spying)", "Unauthorized User", "No Face Detected"]:
                tracker.bad_posture_start_time = None
                if tracker.security_risk_start_time is None:
                    tracker.security_risk_start_time = current_time
                else:
                    elapsed = current_time - tracker.security_risk_start_time
                    countdown = max(0, cfg.SPY_THRESHOLD_SEC - int(elapsed))
                    
                    if countdown > 0:
                        cv2.putText(output_frame, f"SECURITY LOCK IN {countdown}s!", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    
                    if elapsed >= cfg.SPY_THRESHOLD_SEC:
                        if platform.system() == "Windows":
                            print("資安威脅：執行Windows系統鎖定...")
                            ctypes.windll.user32.LockWorkStation()
                        else:
                            print("資安威脅：偵測到資安風險！")
                            if not gui.is_popup_showing:
                                gui.root.after(0, lambda: gui.show_warning_popup("偵測到窺探或未授權用戶，請注意資安！"))
                        
                        tracker.last_lock_time = time.time()
                        tracker.security_risk_start_time = None
                        tracker.bad_posture_start_time = None
                        tracker.unauth_frame_counter = 0
                        tracker.noface_start_time = None
                        tracker.cached_status_text = "Good Posture"
                        tracker.cached_text_color = (0, 255, 0)
            else:
                tracker.security_risk_start_time = None
                if status_text in ["Too Close", "Slouching"]:
                    if tracker.bad_posture_start_time is None:
                        tracker.bad_posture_start_time = current_time
                    else:
                        elapsed = current_time - tracker.bad_posture_start_time
                        countdown = max(0, cfg.BAD_POSTURE_THRESHOLD_SEC - int(elapsed))
                        if countdown > 0:
                            cv2.putText(output_frame, f"Warning in {countdown}s!", (30, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)
                        if elapsed >= cfg.BAD_POSTURE_THRESHOLD_SEC and not gui.is_popup_showing:
                            popup_msg = "靠螢幕太近了，請往後靠！" if status_text == "Too Close" else "駝背了，請把背挺直！"
                            gui.root.after(0, lambda: gui.show_warning_popup(popup_msg))
                            tracker.bad_posture_start_time = None
                else:
                    tracker.bad_posture_start_time = None

        tracker.update_database_status(status_text, current_confidence, face_count)

        cv2.putText(output_frame, status_text, (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)
        cv2.putText(output_frame, f"Faces Detected: {face_count}", (30, h - 35), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(output_frame, f"FPS: {fps:.1f} | CPU: {cpu_usage:.1f}% | RAM: {ram_usage_mb:.1f}MB",
                    (30, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        draw_realtime_chart(output_frame, stats_counts, w, h)

        cv2.imshow('AI Posture & Privacy Guard Pro (OpenCV Edge)', output_frame)
        time.sleep(0.03)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            on_quit(icon)

    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()

def on_quit(icon_obj):
    global running
    running = False
    print("系統通知：正在為您產生今日健康與安全摘要報告...")
    db.generate_daily_report()
    if icon_obj:
        icon_obj.stop()
    gui.stop_gui_loop()
    os._exit(0)

if __name__ == '__main__':
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    icon = gui.setup_system_tray(on_quit)
    gui.start_gui_loop()
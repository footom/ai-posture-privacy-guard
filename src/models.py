import cv2
import numpy as np
import mediapipe as mp
import os
from config import (
    USER_MODEL_FILE, ENABLE_BACKGROUND_BLUR,
    YAW_THRESH, PITCH_UP_THRESH, PITCH_DOWN_THRESH
)

# --- 1.初始化人臉識別器 ---
recognizer = cv2.face.LBPHFaceRecognizer_create()

def load_face_model():
    """載入本地端擁有者辨識模型"""
    if os.path.exists(USER_MODEL_FILE):
        recognizer.read(USER_MODEL_FILE)
        return True
    return False

# --- 2.MediaPipe模型初始化 ---
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_drawing = mp.solutions.drawing_utils

mp_face_detection = mp.solutions.face_detection
face_detector = mp_face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.6)

selfie = None
if ENABLE_BACKGROUND_BLUR:
    mp_selfie = mp.solutions.selfie_segmentation
    selfie = mp_selfie.SelfieSegmentation(model_selection=0)

mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1, refine_landmarks=False,
    min_detection_confidence=0.6, min_tracking_confidence=0.6
)

# --- 3. 輔助運算函式 ---
def get_faces_from_mediapipe(detection_results, w, h):
    """解析MediaPipe偵測結果，回傳Bounding Box列表"""
    faces_list = []
    if detection_results.detections:
        for detection in detection_results.detections:
            bbox = detection.location_data.relative_bounding_box
            xmin = max(0, int(bbox.xmin * w))
            ymin = max(0, int(bbox.ymin * h))
            width = min(int(bbox.width * w), w - xmin)
            height = min(int(bbox.height * h), h - ymin)
            faces_list.append((xmin, ymin, width, height))
    return faces_list

def classify_face_zone(face_landmarks, w, h):
    """判定使用者目前的臉部轉動角度區域 (註冊用)"""
    lm = face_landmarks.landmark
    nose = lm[1]
    left_eye = lm[33]
    right_eye = lm[263]
    forehead = lm[10]
    chin = lm[152]

    eye_mid_x = (left_eye.x + right_eye.x) / 2
    eye_dist_px = max(abs(left_eye.x - right_eye.x) * w, 1.0)
    yaw_ratio = ((nose.x - eye_mid_x) * w) / eye_dist_px

    face_height_px = max((chin.y - forehead.y) * h, 1.0)
    pitch_ratio = ((nose.y - forehead.y) * h) / face_height_px

    if yaw_ratio > YAW_THRESH:
        return "right"
    if yaw_ratio < -YAW_THRESH:
        return "left"
    if pitch_ratio < PITCH_UP_THRESH:
        return "up"
    if pitch_ratio > PITCH_DOWN_THRESH:
        return "down"
    return "front"
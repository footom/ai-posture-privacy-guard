# -*- coding: utf-8 -*-
"""
models.py單元測試

注意：models.py在import階段就會建立cv2 LBPH recognizer與多個
MediaPipe pipeline(Pose/FaceDetection/FaceMesh)物件作為模組全域變數，
所以import models本身就需要環境裝好opencv-contrib與
mediapipe才能成功，這裡假設測試環境滿足requirements.txt。

這裡只測試不需要真實攝影機畫面、純幾何計算的兩個輔助函式：
- get_faces_from_mediapipe()：解析detection結果算bounding box
- classify_face_zone()：用landmark座標算yaw/pitch分類角度區域

model.recognizer.predict() / pose.process()等真正呼叫底層CV/ML pipeline
的部分不在單元測試範圍內，那些需要真實影像資料，比較適合用手動測試或
之後補上帶有樣本圖片的整合測試(integration test)。
"""
import pytest
from models import get_faces_from_mediapipe, classify_face_zone
import config as cfg


class FakeBBox:
    def __init__(self, xmin, ymin, width, height):
        self.xmin = xmin
        self.ymin = ymin
        self.width = width
        self.height = height


class FakeLocationData:
    def __init__(self, bbox):
        self.relative_bounding_box = bbox


class FakeDetection:
    def __init__(self, bbox):
        self.location_data = FakeLocationData(bbox)


class FakeDetectionResults:
    def __init__(self, detections):
        self.detections = detections


class FakeLandmark:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class FakeFaceLandmarks:
    """模擬mediapipe FaceMesh的landmark結果，只填入classify_face_zone用到的index"""
    def __init__(self, nose, left_eye, right_eye, forehead, chin):
        self.landmark = {}
        self.landmark[1] = nose
        self.landmark[33] = left_eye
        self.landmark[263] = right_eye
        self.landmark[10] = forehead
        self.landmark[152] = chin

    class _LandmarkList(list):
        pass


def make_face_landmarks(nose, left_eye, right_eye, forehead, chin):
    """回傳一個可用index存取的假landmark list，符合classify_face_zone的使用方式"""
    max_index = 264
    lm_list = [FakeLandmark(0.5, 0.5)] * max_index
    lm_list[1] = FakeLandmark(*nose)
    lm_list[33] = FakeLandmark(*left_eye)
    lm_list[263] = FakeLandmark(*right_eye)
    lm_list[10] = FakeLandmark(*forehead)
    lm_list[152] = FakeLandmark(*chin)

    class _Wrapper:
        landmark = lm_list

    return _Wrapper()


# ---------------------------------------------------------------------------
# get_faces_from_mediapipe
# ---------------------------------------------------------------------------
class TestGetFacesFromMediapipe:
    def test_no_detections_returns_empty_list(self):
        results = FakeDetectionResults(detections=None)
        assert get_faces_from_mediapipe(results, w=640, h=480) == []

    def test_single_detection_converts_relative_to_pixel_bbox(self):
        bbox = FakeBBox(xmin=0.25, ymin=0.1, width=0.2, height=0.3)
        results = FakeDetectionResults(detections=[FakeDetection(bbox)])

        faces = get_faces_from_mediapipe(results, w=640, h=480)

        assert len(faces) == 1
        xmin, ymin, width, height = faces[0]
        assert xmin == int(0.25 * 640)
        assert ymin == int(0.1 * 480)
        assert width == int(0.2 * 640)
        assert height == int(0.3 * 480)

    def test_negative_xmin_is_clamped_to_zero(self):
        bbox = FakeBBox(xmin=-0.05, ymin=0.1, width=0.2, height=0.3)
        results = FakeDetectionResults(detections=[FakeDetection(bbox)])

        faces = get_faces_from_mediapipe(results, w=640, h=480)

        assert faces[0][0] == 0

    def test_width_clamped_to_frame_boundary(self):
        # xmin接近畫面邊緣，width若照原比例計算會超出畫面
        bbox = FakeBBox(xmin=0.9, ymin=0.1, width=0.5, height=0.3)
        results = FakeDetectionResults(detections=[FakeDetection(bbox)])

        faces = get_faces_from_mediapipe(results, w=640, h=480)

        xmin, ymin, width, height = faces[0]
        assert xmin + width <= 640

    def test_multiple_detections(self):
        bbox1 = FakeBBox(0.1, 0.1, 0.2, 0.2)
        bbox2 = FakeBBox(0.5, 0.5, 0.2, 0.2)
        results = FakeDetectionResults(detections=[FakeDetection(bbox1), FakeDetection(bbox2)])

        faces = get_faces_from_mediapipe(results, w=640, h=480)
        assert len(faces) == 2


# ---------------------------------------------------------------------------
# classify_face_zone
# ---------------------------------------------------------------------------
class TestClassifyFaceZone:
    W, H = 640, 480

    def test_front_facing(self):
        landmarks = make_face_landmarks(
            nose=(0.5, 0.5), left_eye=(0.45, 0.45), right_eye=(0.55, 0.45),
            forehead=(0.5, 0.3), chin=(0.5, 0.7)
        )
        assert classify_face_zone(landmarks, self.W, self.H) == "front"

    def test_turned_right(self):
        # nose.x明顯偏離雙眼中心點，超過YAW_THRESH
        landmarks = make_face_landmarks(
            nose=(0.65, 0.5), left_eye=(0.45, 0.45), right_eye=(0.55, 0.45),
            forehead=(0.5, 0.3), chin=(0.5, 0.7)
        )
        assert classify_face_zone(landmarks, self.W, self.H) == "right"

    def test_turned_left(self):
        landmarks = make_face_landmarks(
            nose=(0.35, 0.5), left_eye=(0.45, 0.45), right_eye=(0.55, 0.45),
            forehead=(0.5, 0.3), chin=(0.5, 0.7)
        )
        assert classify_face_zone(landmarks, self.W, self.H) == "left"

    def test_tilted_up(self):
        # nose靠近forehead(pitch_ratio偏小) -> up
        landmarks = make_face_landmarks(
            nose=(0.5, 0.33), left_eye=(0.45, 0.45), right_eye=(0.55, 0.45),
            forehead=(0.5, 0.3), chin=(0.5, 0.7)
        )
        assert classify_face_zone(landmarks, self.W, self.H) == "up"

    def test_tilted_down(self):
        # nose靠近chin(pitch_ratio偏大) -> down
        landmarks = make_face_landmarks(
            nose=(0.5, 0.6), left_eye=(0.45, 0.45), right_eye=(0.55, 0.45),
            forehead=(0.5, 0.3), chin=(0.5, 0.7)
        )
        assert classify_face_zone(landmarks, self.W, self.H) == "down"

    def test_yaw_checked_before_pitch(self):
        """yaw和pitch同時超過門檻時，函式的if順序是yaw優先判斷"""
        landmarks = make_face_landmarks(
            nose=(0.65, 0.6), left_eye=(0.45, 0.45), right_eye=(0.55, 0.45),
            forehead=(0.5, 0.3), chin=(0.5, 0.7)
        )
        assert classify_face_zone(landmarks, self.W, self.H) == "right"

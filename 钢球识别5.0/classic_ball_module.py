"""Fixed-pipe classical steel-ball detector for the 5.0 application."""

import math

import config
from ball_module import (
    BallTracker,
    BallVision,
    attach_display_geometry,
    clamp,
    make_marker_geometry,
    make_pipe_guide_lines,
    project_to_rod,
    ratio_to_position_mm,
    validate_physical_parameters,
    validate_rod_points,
)


def _config(name, default):
    return getattr(config, name, default)


def expected_ball_diameter_px(
    left,
    right,
    ball_diameter_mm=config.BALL_DIAMETER_MM,
    rod_length_mm=config.ROD_LENGTH_MM,
):
    axis_x = right[0] - left[0]
    axis_y = right[1] - left[1]
    rod_length_px = (axis_x * axis_x + axis_y * axis_y) ** 0.5
    return rod_length_px * float(ball_diameter_mm) / float(rod_length_mm)


def evaluate_contour_candidate(
    box,
    area,
    perimeter,
    center,
    motion_score,
    expected_diameter_px,
):
    x, y, width, height = box
    diameter = max(1.0, float(expected_diameter_px))
    expected_area = math.pi * (diameter * 0.5) ** 2
    if (
        area < expected_area * _config("CLASSIC_MIN_AREA_RATIO", 0.10)
        or area > expected_area * _config("CLASSIC_MAX_AREA_RATIO", 2.80)
    ):
        return None

    minimum_size = diameter * _config("CLASSIC_MIN_DIAMETER_RATIO", 0.35)
    maximum_size = diameter * _config("CLASSIC_MAX_DIAMETER_RATIO", 1.85)
    if (
        width < minimum_size
        or height < minimum_size
        or width > maximum_size
        or height > maximum_size
    ):
        return None

    aspect_ratio = width / float(max(1, height))
    if not (
        _config("CLASSIC_MIN_ASPECT_RATIO", 0.35)
        <= aspect_ratio
        <= _config("CLASSIC_MAX_ASPECT_RATIO", 2.80)
    ):
        return None

    circularity = 0.0
    if perimeter > 0.0:
        circularity = 4.0 * math.pi * float(area) / (float(perimeter) ** 2)
    if circularity < _config("CLASSIC_MIN_CIRCULARITY", 0.06):
        return None

    measured_diameter = max(width, height)
    size_score = max(0.0, 1.0 - abs(measured_diameter - diameter) / diameter)
    shape_score = min(1.0, circularity / 0.75)
    motion_score = clamp(float(motion_score), 0.0, 1.0)
    detector_score = (
        0.50 * size_score + 0.35 * shape_score + 0.15 * motion_score
    )
    return {
        "center": (float(center[0]), float(center[1])),
        "box": (int(x), int(y), int(width), int(height)),
        "detector_score": detector_score,
        "size_score": size_score,
        "shape_score": shape_score,
        "motion_score": motion_score,
    }


def detect_candidates(
    roi_bgr,
    previous_gray,
    expected_diameter_px,
    cv2_module=None,
    numpy_module=None,
):
    if cv2_module is None or numpy_module is None:
        import cv2 as cv2_module
        import numpy as numpy_module

    cv2 = cv2_module
    np = numpy_module
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.GaussianBlur(gray, (5, 5), 0)

    static_mask = cv2.inRange(
        hsv,
        np.array(
            (0, 0, _config("CLASSIC_VALUE_MIN", 35)),
            dtype=np.uint8,
        ),
        np.array(
            (
                179,
                _config("CLASSIC_SATURATION_MAX", 85),
                _config("CLASSIC_VALUE_MAX", 255),
            ),
            dtype=np.uint8,
        ),
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    static_mask = cv2.morphologyEx(static_mask, cv2.MORPH_OPEN, kernel)
    static_mask = cv2.morphologyEx(
        static_mask,
        cv2.MORPH_CLOSE,
        kernel,
        iterations=2,
    )

    motion_mask = np.zeros_like(gray_blur)
    if previous_gray is not None and previous_gray.shape == gray_blur.shape:
        difference = cv2.absdiff(previous_gray, gray_blur)
        _, motion_mask = cv2.threshold(
            difference,
            _config("CLASSIC_MOTION_THRESHOLD", 18),
            255,
            cv2.THRESH_BINARY,
        )
        motion_mask = cv2.dilate(motion_mask, kernel, iterations=1)

    contour_result = cv2.findContours(
        static_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    contours = contour_result[-2]
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        x, y, width, height = cv2.boundingRect(contour)
        perimeter = cv2.arcLength(contour, True)
        moments = cv2.moments(contour)
        if moments["m00"] > 0.0:
            center = (
                moments["m10"] / moments["m00"],
                moments["m01"] / moments["m00"],
            )
        else:
            center = (x + width * 0.5, y + height * 0.5)

        motion_region = motion_mask[y : y + height, x : x + width]
        motion_score = (
            float(np.mean(motion_region)) / 255.0
            if motion_region.size
            else 0.0
        )
        candidate = evaluate_contour_candidate(
            (x, y, width, height),
            area,
            perimeter,
            center,
            motion_score,
            expected_diameter_px,
        )
        if candidate is not None:
            candidates.append(candidate)

    return candidates, gray_blur, static_mask


def translate_candidates(candidates, roi):
    roi_x, roi_y, _, _ = roi
    translated = []
    for candidate in candidates:
        item = dict(candidate)
        center_x, center_y = candidate["center"]
        item["center"] = (center_x + roi_x, center_y + roi_y)
        x, y, width, height = candidate["box"]
        item["box"] = (x + roi_x, y + roi_y, width, height)
        translated.append(item)
    return translated


def select_classic_candidate(candidates, previous_center, left, right, diameter_px):
    diameter = max(1.0, float(diameter_px))
    accepted = []
    for candidate in candidates:
        _, _, distance = project_to_rod(candidate["center"], left, right)
        if distance <= diameter * _config("CLASSIC_AXIS_DISTANCE_DIAMETERS", 1.75):
            accepted.append(candidate)
    if not accepted:
        return None

    def score(candidate):
        center = candidate["center"]
        _, _, distance = project_to_rod(center, left, right)
        value = float(candidate.get("detector_score", 0.0))
        value -= 0.35 * distance / diameter
        if previous_center is not None:
            delta_x = center[0] - previous_center[0]
            delta_y = center[1] - previous_center[1]
            track_distance = (delta_x * delta_x + delta_y * delta_y) ** 0.5
            value -= 0.25 * track_distance / diameter
        return value

    return max(accepted, key=score)


def validate_classic_roi(roi, frame_width, frame_height):
    x, y, width, height = roi
    return (
        width > 0
        and height > 0
        and x >= 0
        and y >= 0
        and x + width <= frame_width
        and y + height <= frame_height
    )


class ClassicBallVision(BallVision):
    """OpenCV detector that preserves the 5.0 tracking and overlay contract."""

    def __init__(self):
        validate_physical_parameters()
        if not validate_rod_points(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.CAPTURE_WIDTH,
            config.CAPTURE_HEIGHT,
        ):
            raise ValueError("invalid rod calibration points")

        self.roi = _config("CLASSIC_ROD_ROI", (8, 75, 304, 90))
        if not validate_classic_roi(
            self.roi,
            config.CAPTURE_WIDTH,
            config.CAPTURE_HEIGHT,
        ):
            raise ValueError("invalid CLASSIC_ROD_ROI")

        from maix import image
        import cv2
        import numpy as np

        self.image = image
        self.cv2 = cv2
        self.np = np
        self.input_format = image.Format.FMT_BGR888
        self.tracker = BallTracker()
        self.ball_diameter_px = expected_ball_diameter_px(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
        )
        self.previous_gray = None
        self.previous_center = None
        self.missed_frames = _config("CLASSIC_MAX_TRACK_MISSES", 3) + 1
        self.markers = make_marker_geometry(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.ROD_LENGTH_MM,
            config.MARKER_HALF_LENGTH_PX,
        )
        self.pipe_guide_lines = make_pipe_guide_lines(
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            config.PIPE_HALF_WIDTH_PX,
        )

    def reset(self):
        self.tracker.reset()
        self.previous_gray = None
        self.previous_center = None
        self.missed_frames = _config("CLASSIC_MAX_TRACK_MISSES", 3) + 1

    def _image_to_cv2(self, img):
        if img.format() != self.image.Format.FMT_BGR888:
            img = img.to_format(self.image.Format.FMT_BGR888)
        data = self.np.frombuffer(img.to_bytes(), dtype=self.np.uint8)
        return data.reshape((img.height(), img.width(), 3))

    def process(self, img, now_ms):
        cv_img = self._image_to_cv2(img)
        roi_x, roi_y, roi_width, roi_height = self.roi
        roi_bgr = cv_img[
            roi_y : roi_y + roi_height,
            roi_x : roi_x + roi_width,
        ]
        roi_candidates, current_gray, _ = detect_candidates(
            roi_bgr,
            self.previous_gray,
            self.ball_diameter_px,
            self.cv2,
            self.np,
        )
        self.previous_gray = current_gray
        candidates = translate_candidates(roi_candidates, self.roi)
        max_misses = _config("CLASSIC_MAX_TRACK_MISSES", 3)
        tracking_reference = (
            self.previous_center if self.missed_frames <= max_misses else None
        )
        best = select_classic_candidate(
            candidates,
            tracking_reference,
            config.ROD_LEFT_POINT,
            config.ROD_RIGHT_POINT,
            self.ball_diameter_px,
        )

        measurement_mm = None
        detected_center = None
        detector_score = 0.0
        if best is not None:
            detected_center = best["center"]
            ratio, _, _ = project_to_rod(
                detected_center,
                config.ROD_LEFT_POINT,
                config.ROD_RIGHT_POINT,
            )
            measurement_mm = ratio_to_position_mm(clamp(ratio, 0.0, 1.0))
            detector_score = best["detector_score"]
            self.previous_center = detected_center
            self.missed_frames = 0
        else:
            self.missed_frames += 1
            if self.missed_frames > max_misses:
                self.previous_center = None

        result = self.tracker.update(measurement_mm, now_ms, detector_score)
        result = attach_display_geometry(result, detected_center)
        result["raw_candidate_boxes"] = tuple(
            candidate["box"] for candidate in candidates
        )
        return result

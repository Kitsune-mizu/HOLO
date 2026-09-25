"""Uji HandTracker._feed langsung (tanpa kamera/thread sungguhan): rotasi satu tangan, zoom dua tangan,
dan kedip kerangka yang singkat tidak boleh membatalkan gesture yang sedang berjalan."""
from pathlib import Path

from hologram.config import Config
from hologram.vision.hands import DropoutGate, HandState, HandTracker, _build_controller

FPS = 24
DT = 1 / FPS


def make_tracker(qapp, **gesture_cfg):
    cfg = Config({"gesture": gesture_cfg} if gesture_cfg else {})
    tracker = HandTracker(camera=None, model_path=Path("unused"), cfg=cfg)
    spins, zooms, labels = [], [], []
    tracker.spin.connect(lambda yaw, pitch: spins.append((yaw, pitch)))
    tracker.zoomFactor.connect(zooms.append)
    tracker.gestureLabel.connect(labels.append)
    return tracker, spins, zooms, labels


def pointing(x: float, y: float = 0.3, base=(0.5, 0.7), confidence: float = 0.9) -> HandState:
    pts = [(0.5, 0.5)] * 21
    pts = list(pts)
    pts[8] = (x, y)          # ujung telunjuk: titik yang dilacak
    pts[5] = base            # pangkal telunjuk: arah kemiringan diukur dari sini
    pts[0] = (0.5, 0.9)
    return HandState(present=True, pointing=True, confidence=confidence, points=tuple(pts), palm=(0.5, 0.7))


def two_finger(x: float, y: float = 0.3, base=(0.5, 0.7), confidence: float = 0.9) -> HandState:
    pts = [(0.5, 0.5)] * 21
    pts = list(pts)
    pts[8] = (x, y)
    pts[5] = base
    pts[0] = (0.5, 0.9)
    return HandState(present=True, two_finger=True, confidence=confidence, points=tuple(pts), palm=(0.5, 0.7))


def run(tracker, gesture, gate, states_fn, n, start_i=0):
    for i in range(start_i, start_i + n):
        tracker._feed(gesture, gate, states_fn(i), 0.5625, i * DT, DT)
    return start_i + n


def test_single_hand_tilt_rotates_continuously_in_right_direction(qapp):
    tracker, spins, zooms, labels = make_tracker(qapp)
    gesture, gate = _build_controller(tracker._gesture_cfg), DropoutGate(0.15)
    run(tracker, gesture, gate, lambda i: (pointing(0.85, base=(0.5, 0.7)),), 20)
    assert spins and all(y > 0 for y, p in spins) and zooms == []
    assert "memutar kanan" in labels


def test_two_hands_apart_zoom_in_continuously(qapp):
    tracker, spins, zooms, labels = make_tracker(qapp)
    gesture, gate = _build_controller(tracker._gesture_cfg), DropoutGate(0.15)

    def two(i):
        x = 0.45 - i * 0.01
        return pointing(x, base=(x, 0.7)), pointing(0.55, base=(0.55, 0.7))

    run(tracker, gesture, gate, two, 15)
    assert zooms and any(z > 1.0 for z in zooms) and spins == []
    assert "zoom in" in labels


def test_brief_dropout_mid_rotation_does_not_reset_it(qapp):
    tracker, spins, zooms, labels = make_tracker(qapp)
    gesture, gate = _build_controller(tracker._gesture_cfg), DropoutGate(0.15)
    i = run(tracker, gesture, gate, lambda k: (pointing(0.85),), 10, 0)
    # kedip hilang ~2 frame di tengah gesture (gerakan cepat)
    tracker._feed(gesture, gate, (), 0.5625, i * DT, DT); i += 1
    tracker._feed(gesture, gate, (), 0.5625, i * DT, DT); i += 1
    before = len(spins)
    run(tracker, gesture, gate, lambda k: (pointing(0.85),), 10, i)
    assert len(spins) > before and all(y > 0 for y, p in spins)   # tetap berputar arah yang sama, tidak direset


def test_long_dropout_resets_the_gesture(qapp):
    tracker, spins, zooms, labels = make_tracker(qapp)
    gesture, gate = _build_controller(tracker._gesture_cfg), DropoutGate(0.15)
    i = run(tracker, gesture, gate, lambda k: (pointing(0.85),), 10, 0)
    for _ in range(6):                                    # 6/24s = 0.25s, lebih lama dari grace 0.15s
        tracker._feed(gesture, gate, (), 0.5625, i * DT, DT); i += 1
    assert labels[-1] == ""                                # gesture diberi tahu berhenti


def test_stabilize_ignores_a_single_frame_flicker_from_point_to_two(qapp):
    tracker, _, _, _ = make_tracker(qapp)
    steady = pointing(0.85)
    flicker = two_finger(0.85)
    tracker._stabilize((steady,))              # dua frame dulu supaya mode "point" benar-benar aktif
    tracker._stabilize((steady,))
    s2 = tracker._stabilize((flicker,))         # satu frame menyimpang: belum cukup untuk berganti
    s3 = tracker._stabilize((steady,))
    assert s2[0].pointing and not s2[0].two_finger and s3[0].pointing


def test_stabilize_switches_after_two_consistent_frames(qapp):
    tracker, _, _, _ = make_tracker(qapp)
    tracker._stabilize((pointing(0.85),))
    tracker._stabilize((two_finger(0.85),))
    tracker._stabilize((two_finger(0.85),))
    result = tracker._stabilize((two_finger(0.85),))
    assert result[0].two_finger and not result[0].pointing


def test_stabilize_resets_slot_when_hand_disappears(qapp):
    tracker, _, _, _ = make_tracker(qapp)
    tracker._stabilize((two_finger(0.85), two_finger(0.15)))
    tracker._stabilize((two_finger(0.85), two_finger(0.15)))
    tracker._stabilize(())                    # kedua tangan hilang: slot harus direset
    tracker._stabilize((pointing(0.85),))
    result = tracker._stabilize((pointing(0.85),))
    assert result[0].pointing                 # bukan lagi "two" basi dari sebelumnya


def test_two_finger_hand_produces_pitch_not_yaw(qapp):
    tracker, spins, zooms, labels = make_tracker(qapp)
    gesture, gate = _build_controller(tracker._gesture_cfg), DropoutGate(0.15)
    run(tracker, gesture, gate, lambda i: (two_finger(0.85),), 20)
    assert spins and all(y == 0 and p > 0 for y, p in spins) and zooms == []
    assert "menunduk" in labels


def test_point_and_two_finger_hands_rotate_both_axes_at_once(qapp):
    tracker, spins, zooms, labels = make_tracker(qapp)
    gesture, gate = _build_controller(tracker._gesture_cfg), DropoutGate(0.15)
    run(tracker, gesture, gate, lambda i: (pointing(0.85), two_finger(0.15)), 20)
    assert spins and any(y > 0 and p != 0 for y, p in spins) and zooms == []


def test_low_confidence_pointing_hand_produces_no_gesture(qapp):
    tracker, spins, zooms, labels = make_tracker(qapp)
    gesture, gate = _build_controller(tracker._gesture_cfg), DropoutGate(0.15)
    run(tracker, gesture, gate, lambda i: (pointing(0.85, confidence=0.2),), 15)
    assert spins == [] and zooms == []


def test_three_hands_worth_of_pointing_is_never_produced_by_real_pipeline(qapp):
    # Batas keamanan: fungsi feed harus diam kalau daftar tangan aneh (bukan 1 atau 2), tidak error.
    tracker, spins, zooms, labels = make_tracker(qapp)
    gesture, gate = _build_controller(tracker._gesture_cfg), DropoutGate(0.15)
    tracker._feed(gesture, gate, (pointing(0.6), pointing(0.7), pointing(0.8)), 0.5625, 0.0, DT)
    assert spins == [] and zooms == []

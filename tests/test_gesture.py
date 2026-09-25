from hologram.vision.gesture import (
    GestureController, PinchGesture, RotationConfig, RotationGesture, signed_tilt_deg,
)

FPS = 24
DT = 1 / FPS


def test_signed_tilt_zero_when_straight_up():
    assert abs(signed_tilt_deg((0.5, 0.7), (0.5, 0.3))) < 1e-9


def test_signed_tilt_sign_matches_left_right():
    assert signed_tilt_deg((0.5, 0.7), (0.6, 0.3)) > 0    # ujung ke kanan dari pangkal: positif
    assert signed_tilt_deg((0.5, 0.7), (0.4, 0.3)) < 0    # ujung ke kiri: negatif


def test_rotation_is_silent_inside_deadzone():
    g = RotationGesture(RotationConfig(deadzone_deg=8))
    base, tip = (0.5, 0.7), (0.53, 0.3)                    # sedikit miring, di bawah 8 derajat
    delta, label = 0.0, ""
    for i in range(10):
        delta, label = g.update(base, tip, i * DT, DT)
    assert delta == 0.0 and label == ""


def test_small_tilt_moves_slower_than_sharp_tilt():
    slow = RotationGesture()
    fast = RotationGesture()
    base = (0.5, 0.7)
    slow_tip, fast_tip = (0.56, 0.3), (0.75, 0.3)          # miring sedikit vs miring tajam ke kanan
    ds, df = 0.0, 0.0
    for i in range(20):
        ds, _ = slow.update(base, slow_tip, i * DT, DT)
        df, _ = fast.update(base, fast_tip, i * DT, DT)
    assert 0 < ds < df


def test_rotation_direction_label_and_sign():
    g = RotationGesture()
    base = (0.5, 0.7)
    d, label = 0.0, ""
    for i in range(20):
        d, label = g.update(base, (0.75, 0.3), i * DT, DT)
    assert d > 0 and label == "kanan"
    g2 = RotationGesture()
    for i in range(20):
        d, label = g2.update(base, (0.25, 0.3), i * DT, DT)
    assert d < 0 and label == "kiri"


def test_rotation_speed_never_exceeds_configured_max_per_frame():
    cfg = RotationConfig(max_dps=150, max_tilt_deg=45)
    g = RotationGesture(cfg)
    base = (0.5, 0.7)
    d = 0.0
    for i in range(30):
        d, _ = g.update(base, (0.9, 0.1), i * DT, DT)      # kemiringan ekstrem
    assert abs(d) <= cfg.max_dps * DT + 1e-6


def test_config_from_dict_with_prefix_reads_separate_keys():
    data = {"deadzone_deg": 8, "max_tilt_deg": 45, "max_dps": 150,
            "pitch_deadzone_deg": 5, "pitch_max_tilt_deg": 30, "pitch_max_dps": 90}
    yaw = RotationConfig.from_dict(data)
    pitch = RotationConfig.from_dict(data, prefix="pitch_")
    assert (yaw.deadzone_deg, yaw.max_tilt_deg, yaw.max_dps) == (8, 45, 150)
    assert (pitch.deadzone_deg, pitch.max_tilt_deg, pitch.max_dps) == (5, 30, 90)


def test_pinch_first_call_is_neutral_baseline():
    p = PinchGesture()
    factor, label = p.update((0.3, 0.5), (0.5, 0.5), 0.5625, 0.0, DT)
    assert factor == 1.0 and label == ""


def test_pinch_apart_zooms_in_and_together_zooms_out():
    p = PinchGesture()
    t = 0.0
    p.update((0.45, 0.5), (0.55, 0.5), 0.5625, t, DT)
    factor, label = 1.0, ""
    for i in range(1, 15):
        t = i * DT
        x = 0.45 - i * 0.01
        factor, label = p.update((x, 0.5), (0.55, 0.5), 0.5625, t, DT)
    assert factor > 1.0 and label == "zoom in"

    p2 = PinchGesture()
    t = 0.0
    p2.update((0.2, 0.5), (0.8, 0.5), 0.5625, t, DT)
    for i in range(1, 15):
        t = i * DT
        x = 0.2 + i * 0.01
        factor, label = p2.update((x, 0.5), (0.8, 0.5), 0.5625, t, DT)
    assert factor < 1.0 and label == "zoom out"


def test_pinch_still_hands_produce_no_zoom():
    p = PinchGesture()
    factor, label = 1.0, ""
    for i in range(10):
        factor, label = p.update((0.3, 0.5), (0.5, 0.5), 0.5625, i * DT, DT)
    assert factor == 1.0 and label == ""


def test_one_finger_hand_rotates_yaw_only():
    gc = GestureController()
    base, tip = (0.5, 0.7), (0.8, 0.3)
    result = None
    for i in range(20):
        result = gc.update([("point", base, tip)], 0.5625, i * DT, DT)
    assert result.yaw_deg > 0 and result.pitch_deg == 0.0 and result.zoom_factor == 1.0
    assert result.label == "memutar kanan"


def test_two_finger_hand_pitches_only():
    gc = GestureController()
    base, tip = (0.5, 0.7), (0.8, 0.3)                     # sama-sama miring kanan, tapi mode "two"
    result = None
    for i in range(20):
        result = gc.update([("two", base, tip)], 0.5625, i * DT, DT)
    assert result.pitch_deg > 0 and result.yaw_deg == 0.0
    assert result.label == "menunduk"

    gc2 = GestureController()
    for i in range(20):
        result = gc2.update([("two", base, (0.2, 0.3))], 0.5625, i * DT, DT)  # miring kiri
    assert result.pitch_deg < 0 and result.label == "mendongak"


def test_two_pointing_hands_zoom_and_ignore_rotation():
    gc = GestureController()
    result = None
    for i in range(1, 15):
        x = 0.45 - i * 0.01
        result = gc.update([("point", (x, 0.7), (x, 0.3)), ("point", (0.55, 0.7), (0.55, 0.3))],
                            0.5625, i * DT, DT)
    assert result.zoom_factor > 1.0 and result.yaw_deg == 0.0 and result.pitch_deg == 0.0


def test_one_point_and_one_two_finger_rotate_both_axes_independently():
    gc = GestureController()
    result = None
    for i in range(20):
        result = gc.update(
            [("point", (0.3, 0.7), (0.5, 0.3)), ("two", (0.7, 0.7), (0.9, 0.3))], 0.5625, i * DT, DT
        )
    assert result.yaw_deg > 0 and result.pitch_deg > 0 and result.zoom_factor == 1.0


def test_two_two_finger_hands_is_neutral():
    gc = GestureController()
    result = gc.update([("two", (0.3, 0.7), (0.5, 0.3)), ("two", (0.7, 0.7), (0.9, 0.3))], 0.5625, 0.0, DT)
    assert result.yaw_deg == 0.0 and result.pitch_deg == 0.0 and result.zoom_factor == 1.0


def test_no_hands_is_completely_neutral():
    gc = GestureController()
    result = gc.update([], 0.5625, 0.0, DT)
    assert result.yaw_deg == 0.0 and result.pitch_deg == 0.0 and result.zoom_factor == 1.0 and result.label == ""

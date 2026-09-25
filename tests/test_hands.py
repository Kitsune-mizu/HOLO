from hologram.vision.hands import (
    DropoutGate, ModeStabilizer, count_open_fingers, is_pointing, is_two_finger, palm_center,
)


def two_finger_hand():
    """Tangan sintetis: telunjuk + tengah lurus, manis dan kelingking menekuk (pose dua-jari)."""
    pts = hand(0)
    pts[8] = (0.40, 0.30)   # telunjuk lurus
    pts[12] = (0.47, 0.30)  # tengah lurus
    return pts


def hand(open_fingers: int):
    """Tangan sintetis: pergelangan di bawah, jari ke atas. Jari tertutup = ujung melipat ke bawah."""
    pts = [(0.5, 0.9)] * 21
    pts = list(pts)
    xs = {8: 0.40, 12: 0.47, 16: 0.54, 20: 0.61}
    for k, (tip, pip) in enumerate(((8, 6), (12, 10), (16, 14), (20, 18))):
        pts[pip] = (xs[tip], 0.60)
        pts[tip] = (xs[tip], 0.30) if k < open_fingers else (xs[tip], 0.68)
    for i in (5, 9, 13, 17):
        pts[i] = (0.4 + (i - 5) * 0.0175, 0.7)
    return pts


def test_open_finger_count():
    for n in range(5):
        assert count_open_fingers(hand(n), aspect=0.5625) == n


def test_palm_center_is_average_of_palm_points():
    pts = [(0.0, 0.0)] * 21
    pts[0], pts[5], pts[9], pts[13], pts[17] = (0.2, 0.8), (0.3, 0.5), (0.4, 0.5), (0.5, 0.5), (0.6, 0.5)
    x, y = palm_center(pts)
    assert abs(x - 0.4) < 1e-9 and abs(y - 0.56) < 1e-9


def test_is_pointing_only_when_index_alone_is_extended():
    assert is_pointing(hand(1), aspect=0.5625) is True     # hanya telunjuk lurus
    assert is_pointing(hand(0), aspect=0.5625) is False    # kepalan
    assert is_pointing(hand(2), aspect=0.5625) is False    # telunjuk + tengah: itu pose dua-jari, bukan menunjuk
    assert is_pointing(hand(4), aspect=0.5625) is False    # telapak terbuka penuh


def test_is_two_finger_only_when_index_and_middle_extended():
    assert is_two_finger(two_finger_hand(), aspect=0.5625) is True
    assert is_two_finger(hand(1), aspect=0.5625) is False   # cuma telunjuk: itu pose menunjuk, bukan dua-jari
    assert is_two_finger(hand(0), aspect=0.5625) is False   # kepalan
    assert is_two_finger(hand(4), aspect=0.5625) is False   # telapak terbuka penuh
    assert is_two_finger(hand(2), aspect=0.5625) is True    # hand(2) generik: telunjuk+tengah = sama dgn di atas


def test_dropout_gate_tolerates_brief_flicker_but_not_long_loss():
    gate = DropoutGate(grace_s=0.15)
    assert gate.update(True, 0.0) is False                 # tangan terlihat
    assert gate.update(False, 0.05) is False                # kedip sebentar: belum dianggap hilang
    assert gate.update(True, 0.08) is False                 # muncul lagi
    assert gate.update(False, 0.30) is True                 # hilang lebih lama dari grace: baru dianggap hilang


def test_dropout_gate_starts_lost_if_never_seen():
    assert DropoutGate(grace_s=0.15).update(False, 0.0) is True


def test_is_two_finger_tolerates_a_slightly_lifted_ring_finger():
    """Manis susah ditekuk sendiri secara anatomis: naikkan sedikit, pose dua-jari tetap terdeteksi."""
    pts = two_finger_hand()
    wrist = pts[0]
    ring_pip = pts[14]
    # angkat ujung manis sedikit dari posisi menekuk penuh, tapi masih jauh dari benar-benar lurus
    pts[16] = (ring_pip[0] + (ring_pip[0] - wrist[0]) * 0.25, ring_pip[1] + (ring_pip[1] - wrist[1]) * 0.25)
    assert is_two_finger(pts, aspect=0.5625) is True


def test_is_two_finger_still_rejects_a_fully_extended_ring_finger():
    pts = two_finger_hand()
    pts[16] = (0.34, 0.30)   # manis benar-benar lurus, bukan cuma sedikit terangkat
    assert is_two_finger(pts, aspect=0.5625) is False


def test_mode_stabilizer_ignores_single_frame_flicker():
    m = ModeStabilizer(frames=2)
    assert m.update("point") == "other"     # baru 1 frame, belum cukup untuk masuk mode baru
    assert m.update("other") == "other"     # berkedip balik: batal, bukan dianggap berganti
    assert m.update("point") == "other"
    assert m.update("point") == "point"     # 2 frame berturut-turut: baru dianggap benar berganti


def test_mode_stabilizer_switches_after_enough_consistent_frames():
    m = ModeStabilizer(frames=2)
    m.update("point"); m.update("point")
    assert m._current == "point"
    m.update("two")
    assert m._current == "point"            # baru 1 frame "two", belum cukup
    m.update("two")
    assert m._current == "two"


def test_mode_stabilizer_reset_forgets_current_mode():
    m = ModeStabilizer(frames=2)
    m.update("point"); m.update("point")
    m.reset()
    assert m._current == "other"
    m.update("point")
    assert m._current == "other"            # harus mulai dari nol lagi setelah reset

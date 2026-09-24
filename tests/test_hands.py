from hologram.vision.hands import count_open_fingers, palm_center


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

from hologram.vision.swipe import OneEuroFilter, SwipeConfig, SwipeDetector

FPS = 18.0


def run(det, points, t0=0.0):
    """points: daftar (x, y) tiap frame. Kembalikan daftar (indeks, arah)."""
    events = []
    for i, (x, y) in enumerate(points):
        d = det.update(x, y, t0 + i / FPS)
        if d:
            events.append((i, d))
    return events


def line(start, end, frames):
    return [(start[0] + (end[0] - start[0]) * k / (frames - 1), start[1] + (end[1] - start[1]) * k / (frames - 1)) for k in range(frames)]


def still(pos, frames):
    return [pos] * frames


def test_swipe_right_left_up_down():
    cases = [((0.4, 0.3), (0.75, 0.3), "right"), ((0.4, 0.3), (0.05, 0.3), "left"),
             ((0.4, 0.5), (0.4, 0.08), "up"), ((0.4, 0.08), (0.4, 0.5), "down")]
    for start, end, expected in cases:
        det = SwipeDetector()
        events = run(det, still(start, 6) + line(start, end, 6) + still(end, 6))
        assert [d for _, d in events] == [expected], (end, events)


def test_return_stroke_is_ignored():
    det = SwipeDetector()
    a, b = (0.2, 0.3), (0.7, 0.3)
    frames = still(a, 6) + line(a, b, 6) + line(b, a, 9) + still(a, 10)
    events = run(det, frames)
    assert [d for _, d in events] == ["right"]


def test_two_separate_swipes_after_pause():
    det = SwipeDetector()
    a, b = (0.2, 0.3), (0.7, 0.3)
    frames = still(a, 6) + line(a, b, 6) + still(b, 25) + line(b, a, 6) + still(a, 6)
    events = run(det, frames)
    assert [d for _, d in events] == ["right", "left"]


def test_jitter_does_not_trigger():
    det = SwipeDetector()
    frames = [(0.5 + 0.01 * (-1) ** k, 0.5 + 0.01 * (-1) ** (k // 2)) for k in range(60)]
    assert run(det, frames) == []


def test_slow_drift_does_not_trigger():
    det = SwipeDetector()
    assert run(det, line((0.2, 0.3), (0.8, 0.3), 90)) == []


def test_diagonal_is_ambiguous():
    det = SwipeDetector()
    assert run(det, still((0.2, 0.2), 4) + line((0.2, 0.2), (0.6, 0.6), 6)) == []


def test_lost_hand_clears_history():
    det = SwipeDetector()
    run(det, still((0.2, 0.3), 3) + line((0.2, 0.3), (0.35, 0.3), 3))
    det.lost()
    assert run(det, still((0.8, 0.3), 5), t0=2.0) == []


def test_one_euro_smooths_noise_but_follows_motion():
    f = OneEuroFilter(min_cutoff=1.5, beta=4.0)
    noisy = [0.5 + (0.02 if k % 2 else -0.02) for k in range(40)]
    out = [f(v, k / FPS) for k, v in enumerate(noisy)]
    assert max(out[10:]) - min(out[10:]) < 0.02
    f = OneEuroFilter(min_cutoff=1.5, beta=4.0)
    last = 0.0
    for k in range(12):
        last = f(k * 0.06, k / FPS)
    assert last > 0.55  # menyusul gerakan cepat, tidak tertinggal jauh


def test_config_from_dict_ignores_unknown_keys():
    cfg = SwipeConfig.from_dict({"distance": 0.3, "bogus": 1})
    assert cfg.distance == 0.3

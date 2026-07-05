from __future__ import annotations

import pytest

from tvadblocker.detector import AdStateMachine, State


def make_sm(debounce: int = 3) -> AdStateMachine:
    return AdStateMachine(
        present_threshold=0.90,
        absent_threshold=0.85,
        debounce_frames=debounce,
        initial=State.PROGRAM,
    )


def test_starts_in_program() -> None:
    assert make_sm().state is State.PROGRAM


def test_debounce_requires_n_consecutive() -> None:
    sm = make_sm(debounce=3)
    assert sm.update(0.1) is None  # 1
    assert sm.update(0.1) is None  # 2
    assert sm.state is State.PROGRAM
    assert sm.update(0.1) is State.AD  # 3 -> confirmed
    assert sm.state is State.AD


def test_single_noisy_frame_does_not_flip() -> None:
    sm = make_sm(debounce=3)
    sm.update(0.1)
    sm.update(0.1)
    # a present frame interrupts the run; counter must reset
    assert sm.update(0.95) is None
    assert sm.state is State.PROGRAM
    # now three lows are needed again from scratch
    assert sm.update(0.1) is None
    assert sm.update(0.1) is None
    assert sm.update(0.1) is State.AD


def test_hysteresis_band_holds_state() -> None:
    sm = make_sm(debounce=1)
    # 0.87 is between absent (0.85) and present (0.90): no change, ever
    for _ in range(10):
        assert sm.update(0.87) is None
    assert sm.state is State.PROGRAM


def test_none_score_is_ignored() -> None:
    sm = make_sm(debounce=2)
    assert sm.update(0.1) is None  # 1st real low
    assert sm.update(None) is None  # ignored: does not count, does not reset
    assert sm.state is State.PROGRAM
    # The None left the pending count intact, so the 2nd real low confirms.
    assert sm.update(0.1) is State.AD
    assert sm.state is State.AD


def test_transition_both_directions() -> None:
    sm = make_sm(debounce=1)
    assert sm.update(0.1) is State.AD
    assert sm.update(0.99) is State.PROGRAM
    assert sm.update(0.1) is State.AD


def test_no_transition_reported_when_already_in_state() -> None:
    sm = make_sm(debounce=1)
    sm.update(0.1)  # -> AD
    assert sm.update(0.2) is None  # already AD, no new transition
    assert sm.state is State.AD


@pytest.mark.parametrize("boundary", [0.90, 0.85])
def test_thresholds_are_inclusive(boundary: float) -> None:
    sm = make_sm(debounce=1)
    if boundary == 0.85:
        assert sm.update(boundary) is State.AD  # <= absent counts as absent
    else:
        # exactly present threshold while already PROGRAM: no transition
        assert sm.update(boundary) is None
        assert sm.state is State.PROGRAM

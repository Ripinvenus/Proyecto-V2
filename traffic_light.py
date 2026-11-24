"""Traffic light model.

Traffic lights are infrastructure elements. They cycle independently between
red and green using configurable durations and their own timers. Their state
is not affected by vehicle movement.
"""
from __future__ import annotations


class TrafficLight:
    """A traffic light located at a single grid cell."""

    def __init__(self, row: int, col: int,
                 red_duration: int = 60, green_duration: int = 60,
                 start: str = "red"):
        self.row = row
        self.col = col
        self.red_duration = red_duration
        self.green_duration = green_duration
        self.state = start  # "red" or "green"
        self.timer = 0

    @property
    def pos(self):
        return (self.row, self.col)

    def update(self):
        """Advance the internal timer and flip state when a duration elapses."""
        self.timer += 1
        if self.state == "red" and self.timer >= self.red_duration:
            self.state = "green"
            self.timer = 0
        elif self.state == "green" and self.timer >= self.green_duration:
            self.state = "red"
            self.timer = 0

    @property
    def cell_state(self):
        """Return the cellular automaton state for the current color."""
        return 2 if self.state == "red" else 3  # 2=red, 3=green

    def set_durations(self, red_duration: int, green_duration: int):
        self.red_duration = max(1, red_duration)
        self.green_duration = max(1, green_duration)

    def __repr__(self):
        return f"TrafficLight(pos={self.pos}, state={self.state}, t={self.timer})"

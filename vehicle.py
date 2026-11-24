"""Vehicle model for the traffic cellular automaton.

A vehicle carries its own identity, position, direction of travel and
timing information used by the statistics module.
"""
from __future__ import annotations


class Vehicle:
    """A single vehicle moving along a one-way street segment."""

    def __init__(self, vid: int, row: int, col: int, direction, generation_born: int = 0):
        self.vid = vid
        self.row = row
        self.col = col
        self.direction = direction  # (dr, dc) movement delta
        self.generation_born = generation_born
        self.generations_waited = 0  # consecutive generations stopped
        self.total_wait = 0          # cumulative generations spent stopped
        self.exited = False
        self.travel_time = 0         # generations from birth to exit

    @property
    def pos(self):
        return (self.row, self.col)

    @property
    def current_travel_time(self):
        return None

    def mark_exited(self, generation: int):
        self.exited = True
        self.travel_time = generation - self.generation_born

    def __repr__(self):
        return f"Vehicle(id={self.vid}, pos={self.pos}, dir={self.direction})"

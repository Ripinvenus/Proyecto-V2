"""Simulation coordinator.

Holds the cellular automaton, statistics and vehicle generation. Advances the
simulation one generation at a time. All parameters are configurable directly
through the interface sliders.
"""
from __future__ import annotations

import random

from city_generator import generate_city, entry_points
from statistics import TrafficStatistics


class Simulation:
    """Top-level simulation logic."""

    def __init__(self, rows: int = 41, cols: int = 51):
        self.rows = rows
        self.cols = cols
        self.ca, self.light_positions = generate_city(rows, cols)
        self.entries = entry_points(self.ca)
        self.stats = TrafficStatistics()
        self.generation = 0
        self.paused = False
        self.running = False
        self.speed = 1.0  # generations per frame multiplier (UI)
        self.moved_last_gen = 0

        # Configurable parameters.
        self.gen_rate = 0.30
        self.max_vehicles = 60
        self.initial_density = 0.35
        self.red_duration = 60
        self.green_duration = 60

        self._rng = random.Random()
        self._rng.seed(42)
        self._spawn_accumulator = 0.0

        self.reset(initial=True)

    # ------------------------------------------------------------------ config
    def set_light_durations(self, red: int, green: int):
        self.red_duration = max(1, red)
        self.green_duration = max(1, green)
        self.ca.set_light_durations(self.red_duration, self.green_duration)

    def set_gen_rate(self, rate: float):
        self.gen_rate = max(0.0, min(1.0, rate))

    def set_max_vehicles(self, n: int):
        self.max_vehicles = max(1, n)

    # ------------------------------------------------------------------ lifecycle
    def reset(self, initial: bool = False):
        self.ca, self.light_positions = generate_city(self.rows, self.cols,
                                                      light_red=self.red_duration,
                                                      light_green=self.green_duration)
        self.entries = entry_points(self.ca)
        self.stats = TrafficStatistics()
        self.generation = 0
        self.moved_last_gen = 0
        self._spawn_accumulator = 0.0
        if not initial:
            self._seed_initial_vehicles()
        self.running = False
        self.paused = False

    def _seed_initial_vehicles(self):
        """Populate the city according to initial density."""
        targets = int(self.ca.road_cells() * self.initial_density)
        attempts = 0
        while self.ca.active_vehicles() < targets and attempts < targets * 20:
            attempts += 1
            if not self.entries:
                break
            r, c, direction = self._rng.choice(self.entries)
            self.ca.spawn_vehicle(r, c, direction)

    # ---------------------------------------------------------------- stepping
    def step(self):
        if self.paused or not self.running:
            return

        self.generation += 1
        self.moved_last_gen = 0

        # Stochastic vehicle generation based on rate.
        self._spawn_accumulator += self.gen_rate
        while self._spawn_accumulator >= 1.0 and self.entries:
            self._spawn_accumulator -= 1.0
            self._try_spawn()

        exited_vehicles = self.ca.step()
        self.moved_last_gen = sum(
            1 for v in self.ca.vehicle_list()
            if v.generations_waited == 0
        )

        # Record travel times of newly exited vehicles.
        exited_times = [v.travel_time for v in exited_vehicles]
        self.stats.record(self.generation, self.ca, self.moved_last_gen, exited_times)

    def _try_spawn(self):
        if self.ca.active_vehicles() >= self.max_vehicles:
            return
        r, c, direction = self._rng.choice(self.entries)
        self.ca.spawn_vehicle(r, c, direction)

    # ---------------------------------------------------------------- queries
    def toggle_pause(self):
        self.paused = not self.paused

    def start(self):
        self.running = True
        self.paused = False

    def stop(self):
        self.running = False

    def current_stats(self) -> dict:
        return self.stats.current_stats()

    def history(self) -> dict:
        return self.stats.history()

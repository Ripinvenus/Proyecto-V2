"""Simulation coordinator.

Holds the cellular automaton, statistics, vehicle generation and the
predefined scenarios. Advances the simulation one generation at a time.
"""
from __future__ import annotations

import random
from typing import Callable

from cellular_automaton import CellularAutomaton, VEHICLE
from city_generator import generate_city, entry_points
from statistics import TrafficStatistics


class Simulation:
    """Top-level simulation logic."""

    SCENARIOS = {
        "A": {"name": "Low traffic",
              "gen_rate": 0.10, "max_vehicles": 25, "density": 0.15},
        "B": {"name": "Medium traffic",
              "gen_rate": 0.30, "max_vehicles": 60, "density": 0.35},
        "C": {"name": "High traffic",
              "gen_rate": 0.60, "max_vehicles": 120, "density": 0.60},
    }

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
        self.gen_rate = self.SCENARIOS["B"]["gen_rate"]
        self.max_vehicles = self.SCENARIOS["B"]["max_vehicles"]
        self.initial_density = self.SCENARIOS["B"]["density"]
        self.red_duration = 60
        self.green_duration = 60

        self._rng = random.Random()
        self._rng.seed(42)
        self._spawn_accumulator = 0.0

        self._apply_scenario("B")
        self.reset(initial=True)

    # ------------------------------------------------------------------ config
    def _apply_scenario(self, key: str):
        s = self.SCENARIOS[key]
        self.gen_rate = s["gen_rate"]
        self.max_vehicles = s["max_vehicles"]
        self.initial_density = s["density"]

    def set_scenario(self, key: str):
        if key in self.SCENARIOS:
            self._apply_scenario(key)

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

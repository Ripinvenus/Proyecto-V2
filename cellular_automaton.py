"""Cellular automaton core for the traffic simulation.

Grid states:
  0 = empty street (light gray)
  1 = vehicle (blue)
  2 = red traffic light (red)
  3 = green traffic light (green)
  4 = obstacle / building (dark gray)

Neighbourhood: Von Neumann (up, down, left, right). Diagonal movement is not
allowed. Updates are simultaneous using the current generation as the sole
source of truth so no vehicle can move more than one cell per generation and
no two vehicles ever occupy the same cell.
"""
from __future__ import annotations

import numpy as np

from vehicle import Vehicle
from traffic_light import TrafficLight

# Cell states
EMPTY = 0
VEHICLE = 1
RED_LIGHT = 2
GREEN_LIGHT = 3
OBSTACLE = 4

# Movement deltas (delta_row, delta_col)
DIR_NORTH = (-1, 0)
DIR_SOUTH = (1, 0)
DIR_WEST = (0, -1)
DIR_EAST = (0, 1)

ALL_DIRECTIONS = [DIR_NORTH, DIR_SOUTH, DIR_WEST, DIR_EAST]


class CellularAutomaton:
    """Manages the CA grid, vehicles and one generation transition."""

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.generation = 0
        self.next_vid = 1
        self.total_generated = 0
        self.total_exited = 0

        self.grid = np.full((rows, cols), EMPTY, dtype=int)
        # Base (infrastructure) state restored when a vehicle leaves a cell.
        self.base = np.full((rows, cols), EMPTY, dtype=int)
        self.has_road = np.zeros((rows, cols), dtype=bool)
        # Allowed movement direction per drivable cell.
        self.road_dir = np.zeros((rows, cols, 2), dtype=int)

        # Street layout (row/col -> one-way direction) used to derive entries.
        self.street_rows: dict[int, tuple[int, int]] = {}
        self.street_cols: dict[int, tuple[int, int]] = {}

        self.vehicles: dict[int, Vehicle] = {}
        self.traffic_lights: dict[tuple[int, int], TrafficLight] = {}

    # ------------------------------------------------------------------ setup
    def is_within(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def set_road(self, r: int, c: int, direction):
        self.has_road[r, c] = True
        self.road_dir[r, c] = direction
        self.base[r, c] = EMPTY
        self.grid[r, c] = EMPTY

    def set_obstacle(self, r: int, c: int):
        self.has_road[r, c] = False
        self.base[r, c] = OBSTACLE
        self.grid[r, c] = OBSTACLE

    def add_traffic_light(self, r: int, c: int,
                          red_duration: int = 60, green_duration: int = 60,
                          start: str = "red"):
        self.has_road[r, c] = True
        self.road_dir[r, c] = (0, 0)
        self.base[r, c] = GREEN_LIGHT if start == "green" else RED_LIGHT
        self.grid[r, c] = self.base[r, c]
        self.traffic_lights[(r, c)] = TrafficLight(
            r, c, red_duration, green_duration, start
        )

    def set_light_durations(self, red_duration: int, green_duration: int):
        for light in self.traffic_lights.values():
            light.set_durations(red_duration, green_duration)

    # -------------------------------------------------------- vehicle spawning
    def spawn_vehicle(self, r: int, c: int, direction):
        if not self.is_within(r, c):
            return None
        if self.grid[r, c] != EMPTY:
            return None
        vid = self.next_vid
        self.next_vid += 1
        self.total_generated += 1
        v = Vehicle(vid, r, c, direction, self.generation)
        self.vehicles[vid] = v
        self.grid[r, c] = VEHICLE
        return v

    def remove_vehicle(self, vid: int):
        v = self.vehicles.pop(vid, None)
        if v is None:
            return
        v.exited = True
        v.travel_time = self.generation - v.generation_born
        self.total_exited += 1

    # ---------------------------------------------------------------- stepping
    def step(self):
        """Advance one generation using simultaneous conflict-free updates."""
        self.generation += 1

        # 1. Update traffic lights (independent of vehicles).
        for light in self.traffic_lights.values():
            light.update()
            self.base[light.row, light.col] = light.cell_state

        # Snapshot of current occupancy.
        occupied = {(v.row, v.col) for v in self.vehicles.values()}

        # Rebuild next grid from infrastructure base.
        new_grid = self.base.copy()

        moves: dict[int, tuple[int, int] | None] = {}
        targets_taken: set[tuple[int, int]] = set()

        # 2. Decide each vehicle's move based ONLY on the current grid.
        for vid in sorted(self.vehicles.keys()):
            v = self.vehicles[vid]
            dr, dc = v.direction
            tr, tc = v.row + dr, v.col + dc

            # Leaves the grid -> exits.
            if not self.is_within(tr, tc):
                moves[vid] = None
                continue

            # Obstacles cannot be traversed.
            if self.base[tr, tc] == OBSTACLE:
                continue

            target_state = self.grid[tr, tc]
            can_enter = False
            if target_state == EMPTY:
                can_enter = True
            elif target_state == GREEN_LIGHT:
                can_enter = True
            # RED_LIGHT or VEHICLE -> cannot enter (vehicle stops).

            if can_enter and (tr, tc) not in targets_taken:
                moves[vid] = (tr, tc)
                targets_taken.add((tr, tc))
            # Otherwise the vehicle stays in place.

        # 3. Apply moves simultaneously.
        exited_vehicles: list[Vehicle] = []
        for vid, target in moves.items():
            v = self.vehicles[vid]
            if target is None:
                self.remove_vehicle(vid)
                exited_vehicles.append(v)
                continue
            tr, tc = target
            new_grid[v.row, v.col] = self.base[v.row, v.col]
            v.row, v.col = tr, tc
            new_grid[tr, tc] = VEHICLE

        # 4. Vehicles that did not move remain in their cell.
        exited_ids = {v.vid for v in exited_vehicles}
        for vid, v in self.vehicles.items():
            if vid in exited_ids:
                continue
            if vid in moves and moves[vid] is not None:
                continue  # already placed at new position
            new_grid[v.row, v.col] = VEHICLE
            v.generations_waited += 1
            v.total_wait += 1

        self.grid = new_grid
        return exited_vehicles

    # --------------------------------------------------------------- queries
    def active_vehicles(self) -> int:
        return len(self.vehicles)

    def vehicle_list(self):
        return list(self.vehicles.values())

    def congestion_count(self) -> int:
        """Vehicles stopped for 3 or more consecutive generations."""
        return sum(1 for v in self.vehicles.values() if v.generations_waited >= 3)

    def road_cells(self) -> int:
        return int(self.has_road.sum())

    def occupied_road(self) -> int:
        return sum(1 for v in self.vehicles.values())

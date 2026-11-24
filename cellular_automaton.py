"""Cellular automaton core for the traffic simulation.

Grid states:
  0 = empty street (light gray)
  1 = vehicle (blue)
  2 = red traffic light (red)
  3 = green traffic light (green)
  4 = obstacle / building (dark gray)
  5 = delivery stop (yellow)
  6 = courier / delivery agent (orange)

Neighbourhood: Von Neumann (up, down, left, right). Diagonal movement is not
allowed. Updates are simultaneous using the current generation as the sole
source of truth so no vehicle can move more than one cell per generation and
no two vehicles ever occupy the same cell.
"""
from __future__ import annotations

import numpy as np

from vehicle import Vehicle
from traffic_light import TrafficLight
from courier import Courier

# Cell states
EMPTY = 0
VEHICLE = 1
RED_LIGHT = 2
GREEN_LIGHT = 3
OBSTACLE = 4
STOP = 5
COURIER = 6

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
        # Short connector edges (e.g. corner hooks of the reverse border lanes).
        self.extra_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()

        self.vehicles: dict[int, Vehicle] = {}
        self.traffic_lights: dict[tuple[int, int], TrafficLight] = {}

        # Delivery route: yellow stop cells (infrastructure) and one courier.
        self.stops: list[tuple[int, int]] = []
        self.courier: Courier | None = None

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

    # --------------------------------------------------------------- courier
    def toggle_stop(self, r: int, c: int) -> bool:
        """Add/remove a yellow stop on a free street cell. Replans on change."""
        if not self.is_within(r, c) or not self.has_road[r, c]:
            return False
        if (r, c) in self.traffic_lights:
            return False
        pos = (r, c)
        if pos in self.stops:
            self.stops.remove(pos)
            if self.base[r, c] == STOP:
                self.base[r, c] = EMPTY
            if self.grid[r, c] == STOP:
                self.grid[r, c] = EMPTY
        else:
            if self.grid[r, c] not in (EMPTY, STOP):
                return False
            self.stops.append(pos)
            self.base[r, c] = STOP
            if self.grid[r, c] != COURIER:
                self.grid[r, c] = STOP
        self.replan_courier()
        return True

    def place_courier(self, r: int, c: int):
        """Place (or move) the single courier and plan its route."""
        if not self.is_within(r, c) or not self.has_road[r, c]:
            return None
        if (r, c) in self.traffic_lights or self.grid[r, c] == VEHICLE:
            return None
        if self.courier is not None:
            old_r, old_c = self.courier.pos
            self.grid[old_r, old_c] = self.base[old_r, old_c]
        self.courier = Courier(r, c)
        self.grid[r, c] = COURIER
        self.replan_courier()
        return self.courier

    def clear_route(self):
        """Remove the courier and every stop."""
        if self.courier is not None:
            r, c = self.courier.pos
            self.grid[r, c] = self.base[r, c]
            self.courier = None
        for r, c in self.stops:
            if self.base[r, c] == STOP:
                self.base[r, c] = EMPTY
            if self.grid[r, c] == STOP:
                self.grid[r, c] = EMPTY
        self.stops.clear()

    def replan_courier(self):
        if self.courier is not None:
            self.courier.plan(self, self.generation)

    def _legal_courier_step(self, r: int, c: int, tr: int, tc: int) -> bool:
        """Check a planned step against the one-way street directions."""
        if not self.is_within(tr, tc) or not self.has_road[tr, tc]:
            return False
        if abs(tr - r) + abs(tc - c) != 1:
            return False
        allowed = []
        if r in self.street_rows:
            dr, dc = self.street_rows[r]
            allowed.append((r + dr, c + dc))
        if c in self.street_cols:
            dr, dc = self.street_cols[c]
            allowed.append((r + dr, c + dc))
        return (tr, tc) in allowed or ((r, c), (tr, tc)) in self.extra_edges

    # -------------------------------------------------------- vehicle spawning
    def spawn_vehicle(self, r: int, c: int, direction):
        if not self.is_within(r, c):
            return None
        if self.grid[r, c] not in (EMPTY, STOP):
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
            # STOP cells are normal streets for vehicles; red lights, vehicles
            # and the courier block entry.
            can_enter = target_state in (EMPTY, GREEN_LIGHT, STOP)

            if can_enter and (tr, tc) not in targets_taken:
                moves[vid] = (tr, tc)
                targets_taken.add((tr, tc))
            # Otherwise the vehicle stays in place.

        # 2b. The courier decides from the same snapshot, after vehicles have
        # claimed their targets, so it never steals or shares a cell.
        courier = self.courier
        courier_target = None
        if courier is not None and courier.status == "moving":
            target = courier.next_step
            if target is None:
                courier.status = "done"
            else:
                tr, tc = target
                if self._legal_courier_step(courier.row, courier.col, tr, tc):
                    courier.direction = (tr - courier.row, tc - courier.col)
                    target_state = self.grid[tr, tc]
                    if (target_state in (EMPTY, GREEN_LIGHT, STOP)
                            and (tr, tc) not in targets_taken):
                        courier_target = (tr, tc)
                        targets_taken.add((tr, tc))
                else:
                    # Street layout changed underneath the plan.
                    self.replan_courier()

        # 3. Apply vehicle moves simultaneously.
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

        # 3b. Apply the courier move (or leave it waiting at a red light).
        if courier_target is not None and courier is not None:
            cr, cc = courier.pos
            new_grid[cr, cc] = self.base[cr, cc]
            courier.row, courier.col = courier_target
            courier.path_index += 1
            if courier.pos in self.stops:
                courier.delivered.add(courier.pos)
            new_grid[courier.row, courier.col] = COURIER
            if courier.path_index >= len(courier.path):
                courier.status = "done"
        elif courier is not None:
            new_grid[courier.row, courier.col] = COURIER
            courier.waited += 1

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

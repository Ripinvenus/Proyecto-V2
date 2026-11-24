"""Statistics collection for the traffic simulation.

Records time-series metrics and computes real-time indicators such as traffic
density, congestion, average speed and travel time.
"""
from __future__ import annotations

from collections import deque


class TrafficStatistics:
    """Collects and aggregates simulation metrics over generations."""

    def __init__(self, history_size: int = 300):
        self.history_size = history_size
        self.generations = deque(maxlen=history_size)
        self.active_vehicles = deque(maxlen=history_size)
        self.exited_vehicles = deque(maxlen=history_size)
        self.congested_cells = deque(maxlen=history_size)
        self.density_pct = deque(maxlen=history_size)
        self.avg_wait = deque(maxlen=history_size)
        self.avg_speed = deque(maxlen=history_size)

        # Completed trips for average travel time.
        self.completed_travel_times = []

        self.total_generated = 0
        self.total_exited = 0

        # Latest courier route snapshot.
        self.courier_status = "-"
        self.stops_done = 0
        self.stops_total = 0
        self.stops_pending = 0
        self.stops_unreachable = 0
        self.route_length = 0
        self.courier_time = 0

    # ------------------------------------------------------------------ record
    def record(self, generation: int, ca, moved_last_gen: int,
               exited_travel_times: list[int]):
        """Snapshot metrics for the current generation."""
        road = ca.road_cells() or 1
        active = ca.active_vehicles()
        exited = ca.total_exited
        congested = ca.congestion_count()
        density = (active / road) * 100.0

        avg_speed = (moved_last_gen / active) if active else 0.0
        waits = [v.total_wait for v in ca.vehicle_list()]
        avg_wait = (sum(waits) / len(waits)) if waits else 0.0

        # Courier / delivery route metrics.
        courier = getattr(ca, "courier", None)
        all_stops = getattr(ca, "stops", [])
        if courier is not None:
            courier_status = courier.status
            stops_done = len(courier.delivered)
            stops_total = len(all_stops)
            stops_pending = max(0, stops_total - stops_done)
            stops_unreachable = len(courier.unreachable)
            route_length = courier.route_length
            courier_time = max(0, generation - courier.born_generation)
        else:
            courier_status = "-"
            stops_done = 0
            stops_total = len(all_stops)
            stops_pending = stops_total
            stops_unreachable = 0
            route_length = 0
            courier_time = 0

        self.completed_travel_times.extend(exited_travel_times)

        self.generations.append(generation)
        self.active_vehicles.append(active)
        self.exited_vehicles.append(exited)
        self.congested_cells.append(congested)
        self.density_pct.append(density)
        self.avg_wait.append(avg_wait)
        self.avg_speed.append(avg_speed)

        self.total_generated = ca.total_generated
        self.total_exited = exited

        self.courier_status = courier_status
        self.stops_done = stops_done
        self.stops_total = stops_total
        self.stops_pending = stops_pending
        self.stops_unreachable = stops_unreachable
        self.route_length = route_length
        self.courier_time = courier_time

    # ---------------------------------------------------------------- queries
    def avg_travel_time(self) -> float:
        if not self.completed_travel_times:
            return 0.0
        return sum(self.completed_travel_times) / len(self.completed_travel_times)

    def current_stats(self) -> dict:
        return {
            "generation": self.generations[-1] if self.generations else 0,
            "active": self.active_vehicles[-1] if self.active_vehicles else 0,
            "exited": self.exited_vehicles[-1] if self.exited_vehicles else 0,
            "congested": self.congested_cells[-1] if self.congested_cells else 0,
            "density": self.density_pct[-1] if self.density_pct else 0.0,
            "avg_wait": self.avg_wait[-1] if self.avg_wait else 0.0,
            "avg_speed": self.avg_speed[-1] if self.avg_speed else 0.0,
            "avg_travel_time": self.avg_travel_time(),
            "total_generated": self.total_generated,
            "total_exited": self.total_exited,
            "courier_status": self.courier_status,
            "stops_done": self.stops_done,
            "stops_total": self.stops_total,
            "stops_pending": self.stops_pending,
            "stops_unreachable": self.stops_unreachable,
            "route_length": self.route_length,
            "courier_time": self.courier_time,
        }

    def history(self) -> dict:
        return {
            "generations": list(self.generations),
            "active": list(self.active_vehicles),
            "exited": list(self.exited_vehicles),
            "congested": list(self.congested_cells),
            "density": list(self.density_pct),
            "avg_wait": list(self.avg_wait),
            "avg_speed": list(self.avg_speed),
        }

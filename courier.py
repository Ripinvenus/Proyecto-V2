"""Delivery courier agent and route planner.

The courier is a single mobile agent (orange) that visits the yellow stop
cells. Its order is chosen with a greedy nearest-stop heuristic and improved
with 2-opt. Routing happens on the directed street graph derived from the
city's one-way streets, so every planned step is legal by construction.
"""
from __future__ import annotations

from collections import deque

INF = float("inf")


# ------------------------------------------------------------------- graph
def build_road_graph(ca):
    """Return ``{cell: [neighbour cells]}`` using the one-way street rules.

    At an intersection both streets are available: the courier may continue
    along its street or turn into the crossing one if that street's direction
    allows leaving the intersection that way.
    """
    graph = {}
    for r in range(ca.rows):
        for c in range(ca.cols):
            if not ca.has_road[r, c]:
                continue
            neighbours = []
            if r in ca.street_rows:
                dr, dc = ca.street_rows[r]
                nr, nc = r + dr, c + dc
                if ca.is_within(nr, nc) and ca.has_road[nr, nc]:
                    neighbours.append((nr, nc))
            if c in ca.street_cols:
                dr, dc = ca.street_cols[c]
                nr, nc = r + dr, c + dc
                if ca.is_within(nr, nc) and ca.has_road[nr, nc]:
                    neighbours.append((nr, nc))
            graph[(r, c)] = list(dict.fromkeys(neighbours))

    # Corner hooks of the reverse border lanes (e.g. (0,1) -> (0,0)).
    for u, v in ca.extra_edges:
        graph.setdefault(u, []).append(v)
    return graph


def _bfs(graph, start):
    """Breadth-first search: shortest distances and predecessor links."""
    dist = {start: 0}
    prev = {}
    queue = deque([start])
    while queue:
        u = queue.popleft()
        for v in graph.get(u, ()):
            if v not in dist:
                dist[v] = dist[u] + 1
                prev[v] = u
                queue.append(v)
    return dist, prev


# ---------------------------------------------------------------- planning
def _route_cost(order, matrix):
    """Total distance of a stop sequence using the precomputed distances."""
    if not order:
        return INF
    total = matrix[0][order[0]]
    if total == INF:
        return INF
    for a, b in zip(order, order[1:]):
        total += matrix[a + 1][b]
        if total == INF:
            return INF
    return total


def _two_opt(order, matrix):
    """Improve a stop sequence by reversing segments while it shortens it."""
    best = list(order)
    improved = True
    while improved:
        improved = False
        best_cost = _route_cost(best, matrix)
        n = len(best)
        for i in range(n - 1):
            for k in range(i + 1, n):
                candidate = best[:i] + best[i:k + 1][::-1] + best[k + 1:]
                if _route_cost(candidate, matrix) < best_cost:
                    best = candidate
                    improved = True
                    break
            if improved:
                break
    return best


def plan_route(ca, start, stops):
    """Plan a route from ``start`` through all reachable ``stops``.

    Returns ``(path, ordered_stops, unreachable)`` where ``path`` is the full
    list of cells to walk (excluding the starting cell).
    """
    if not stops:
        return [], [], []

    graph = build_road_graph(ca)
    searches = [_bfs(graph, start)] + [_bfs(graph, s) for s in stops]
    n = len(stops)

    # matrix[i][j]: row 0 = start, row i+1 = stops[i]; column j = stops[j].
    matrix = [[INF] * n for _ in range(n + 1)]
    for j in range(n):
        matrix[0][j] = searches[0][0].get(stops[j], INF)
        for i in range(n):
            matrix[i + 1][j] = searches[i + 1][0].get(stops[j], INF)

    # Greedy nearest stop.
    remaining = set(range(n))
    order = []
    current = 0
    while remaining:
        reachable = [k for k in remaining if matrix[current][k] != INF]
        if not reachable:
            break
        j = min(reachable, key=lambda k: (matrix[current][k], k))
        order.append(j)
        remaining.remove(j)
        current = j + 1

    order = _two_opt(order, matrix)

    # Stitch the legs together: start -> stop[order[0]] -> ...
    # Each leg needs a BFS rooted at the current position: with one-way
    # streets, reachability is not symmetric.
    path = []
    cursor = start
    for j in order:
        stop = stops[j]
        dist, prev = _bfs(graph, cursor)
        if stop not in dist:
            continue
        chain = [stop]
        while chain[-1] != cursor:
            parent = prev.get(chain[-1])
            if parent is None:
                break
            chain.append(parent)
        else:
            chain.reverse()
            path.extend(chain[1:])
            cursor = stop

    unreachable = [stops[j] for j in range(n) if j not in order]
    return path, [stops[j] for j in order], unreachable


# ------------------------------------------------------------------- agent
class Courier:
    """The single delivery agent living inside the cellular automaton."""

    def __init__(self, row: int, col: int):
        self.row = row
        self.col = col
        self.start = (row, col)
        self.direction = (0, 1)
        self.path: list[tuple[int, int]] = []
        self.path_index = 0
        self.route_length = 0
        self.ordered_stops: list[tuple[int, int]] = []
        self.unreachable: list[tuple[int, int]] = []
        self.delivered: set[tuple[int, int]] = set()
        self.status = "idle"  # idle | moving | done
        self.born_generation = 0
        self.waited = 0

    @property
    def pos(self):
        return (self.row, self.col)

    @property
    def next_step(self):
        if self.status == "moving" and self.path_index < len(self.path):
            return self.path[self.path_index]
        return None

    def plan(self, ca, generation: int):
        """(Re)compute the route from the current position."""
        path, ordered, unreachable = plan_route(ca, self.pos, list(ca.stops))
        self.path = path
        self.path_index = 0
        self.route_length = len(path)
        self.ordered_stops = ordered
        self.unreachable = unreachable
        self.delivered.intersection_update(set(ca.stops))
        if self.pos in ca.stops:
            self.delivered.add(self.pos)
        self.status = "moving" if path else ("done" if ca.stops else "idle")
        self.born_generation = generation
        self.waited = 0

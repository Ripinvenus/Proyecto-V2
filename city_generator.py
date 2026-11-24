"""City generator.

Builds a realistic urban road layout on a rectangular grid:

* horizontal and vertical one-way streets,
* intersections where streets cross,
* a traffic light at every internal intersection,
* obstacles (buildings) filling the blocks between streets.

Street directions alternate so traffic circulates in a coherent pattern and
vehicles always have a valid route from an entry edge to an exit edge.
"""
from __future__ import annotations

from cellular_automaton import (
    CellularAutomaton, EMPTY, OBSTACLE,
    DIR_NORTH, DIR_SOUTH, DIR_WEST, DIR_EAST,
)


def _alternate(index: int):
    """Return EAST for even, WEST for odd (horizontal); SOUTH/NORTH (vertical)."""
    return DIR_EAST if index % 2 == 0 else DIR_WEST


def generate_city(rows: int = 41, cols: int = 51,
                  street_spacing: int = 10,
                  light_red: int = 60, light_green: int = 60):
    """Create a city grid.

    Streets run every ``street_spacing`` cells. Horizontal streets alternate
    East/West; vertical streets alternate South/North. A traffic light is
    placed at every internal intersection. Everything else is an obstacle.
    """
    ca = CellularAutomaton(rows, cols)

    # Everything starts as obstacle.
    for r in range(rows):
        for c in range(cols):
            ca.set_obstacle(r, c)

    # Street rows (horizontal) and street columns (vertical).
    street_rows = list(range(street_spacing, rows, street_spacing))
    street_cols = list(range(street_spacing, cols, street_spacing))

    # Make sure edges are streets so vehicles can enter/exit.
    if 0 not in street_rows:
        street_rows.insert(0, 0)
    if rows - 1 not in street_rows:
        street_rows.append(rows - 1)
    if 0 not in street_cols:
        street_cols.insert(0, 0)
    if cols - 1 not in street_cols:
        street_cols.append(cols - 1)

    # Remember each street's intended direction. This is needed because the
    # vertical-street pass below overwrites ``road_dir`` at every crossing,
    # including the left/right border cells used by horizontal entry points.
    row_dirs = {r: _alternate(i) for i, r in enumerate(street_rows)}
    col_dirs = {c: (DIR_SOUTH if j % 2 == 0 else DIR_NORTH)
                for j, c in enumerate(street_cols)}

    # A second lane just inside every border, running in the opposite
    # direction. Each pair of border lanes forms a one-way couplet, so the
    # courier can turn around and reach cells that were unreachable before.
    def _opposite(direction):
        return tuple(-x for x in direction)

    if 1 not in row_dirs and rows > 3:
        row_dirs[1] = _opposite(row_dirs[0])              # top: West
    if rows - 2 not in row_dirs and rows > 3:
        row_dirs[rows - 2] = _opposite(row_dirs[rows - 1])  # bottom: West
    if 1 not in col_dirs and cols > 3:
        col_dirs[1] = _opposite(col_dirs[0])              # left: North
    if cols - 2 not in col_dirs and cols > 3:
        col_dirs[cols - 2] = _opposite(col_dirs[cols - 1])  # right: South

    ca.street_rows = row_dirs
    ca.street_cols = col_dirs

    # Horizontal streets.
    for r, direction in row_dirs.items():
        for c in range(cols):
            ca.set_road(r, c, direction)

    # Vertical streets.
    for c, direction in col_dirs.items():
        for r in range(rows):
            # Vertical overrides direction at the cell but keeps it drivable.
            ca.has_road[r, c] = True
            ca.base[r, c] = EMPTY
            ca.grid[r, c] = EMPTY
            ca.road_dir[r, c] = direction

    # The top-left corner would otherwise be a dead source (both border lanes
    # lead away from it). The inner left lane reaches (0,1) going North, so a
    # short West hook makes the corner reachable as well.
    if rows > 1 and cols > 1 and ca.has_road[0, 1] and ca.has_road[0, 0]:
        ca.extra_edges.add(((0, 1), (0, 0)))

    # A traffic light at EVERY internal intersection (border crossings are
    # entry/exit cells and must stay free so vehicles can spawn and leave).
    light_positions = []
    for i, r in enumerate(sorted(row_dirs)):
        if r == 0 or r == rows - 1:
            continue
        for j, c in enumerate(sorted(col_dirs)):
            if c == 0 or c == cols - 1:
                continue
            start = "red" if (i + j) % 4 == 0 else "green"
            ca.add_traffic_light(r, c, light_red, light_green, start)
            light_positions.append((r, c))

    return ca, light_positions


def entry_points(ca: CellularAutomaton):
    """Return valid edge cells where new vehicles may enter, with direction.

    Both orientations are produced:

    * Horizontal one-way streets are entered from the left edge when they run
      East, and from the right edge when they run West.
    * Vertical one-way streets are entered from the top edge when they run
      South, and from the bottom edge when they run North.

    The street directions stored on ``ca`` are used instead of ``road_dir``
    because ``road_dir`` is overwritten by vertical streets at every crossing.
    """
    pts = []

    # Horizontal streets -> left edge (East-bound) / right edge (West-bound).
    for r, direction in ca.street_rows.items():
        dr, dc = direction
        if dc > 0:                       # East
            c = 0
        elif dc < 0:                     # West
            c = ca.cols - 1
        else:
            continue
        if ca.has_road[r, c] and ca.grid[r, c] == EMPTY:
            pts.append((r, c, (dr, dc)))

    # Vertical streets -> top edge (South-bound) / bottom edge (North-bound).
    for c, direction in ca.street_cols.items():
        dr, dc = direction
        if dr > 0:                       # South
            r = 0
        elif dr < 0:                     # North
            r = ca.rows - 1
        else:
            continue
        if ca.has_road[r, c] and ca.grid[r, c] == EMPTY:
            pts.append((r, c, (dr, dc)))

    return pts


if __name__ == "__main__":
    ca, lights = generate_city()
    print("Grid:", ca.rows, "x", ca.cols)
    print("Road cells:", ca.road_cells())
    print("Traffic lights:", len(lights))
    print("Entry points:", len(entry_points(ca)))

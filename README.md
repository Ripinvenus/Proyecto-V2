# 2D Cellular Automaton for Urban Traffic Flow and Congestion Simulation

An interactive, visually appealing traffic simulation built with **Python 3**,
**Pygame**, **NumPy** and **Matplotlib**. It models how vehicles move through a
city grid, how congestion develops, and how traffic lights influence
circulation — using a faithful two-dimensional cellular automaton.

## Project structure

```
traffic_simulation/
    main.py             # Entry point
    simulation.py       # Simulation coordinator (spawning, step, parameters)
    cellular_automaton.py  # CA grid, vehicles, simultaneous transition rules
    vehicle.py          # Vehicle model (position, direction, waiting time)
    traffic_light.py    # Traffic light model (independent red/green timers)
    courier.py          # Delivery agent and BFS/greedy/2-opt route planner
    city_generator.py   # Road network, intersections, obstacles, lights
    statistics.py       # Real-time metrics and history
    interface.py        # Pygame rendering, controls and statistics
    requirements.txt    # Python dependencies
    README.md           # This file
```

## Requirements

- Python 3.8+
- pygame
- numpy
- matplotlib (listed for completeness; the interface is drawn with Pygame)

Install dependencies:

```bash
pip install -r requirements.txt
```

## How to run

```bash
cd traffic_simulation
python3 main.py
```

Controls (all also available via on-screen buttons):

| Key / Button | Action |
|---|---|
| Start / Click | Begin the simulation |
| Pause / Space | Pause / resume |
| Reset | Reload the city and clear statistics |
| Generate Vehicle | Spawn one vehicle at a valid entry point |
| Clear Vehicles | Remove every vehicle from the grid |
| Sim. speed slider | Simulation speed from 0.1x (slow motion) to 10x (multiple generations per frame) |
| Gen. rate | Probability of spawning a vehicle each generation |
| Max vehicles | Upper bound of simultaneous vehicles |
| Red / Green duration | Traffic light cycle timers (generations) |
| Initial density | Fill fraction of road cells at reset |
| Left click on the map | Toggle a yellow delivery stop (click again to remove it) |
| Right click on the map | Place/reposition the orange courier and start its route |
| Clear Route | Remove every stop and the courier |
| ESC | Quit |

The window adapts to the desktop size. The city occupies the left side and is
drawn as large as possible; controls and parameters sit in a compact middle
column, and the real-time statistics have a small dedicated panel on the far
right. There are no charts, so the map gets the available space.

## Cellular automaton theory

The simulated city is a two-dimensional grid. Each cell is one section of
street or an urban element and takes exactly one of seven states:

| State | Meaning | Colour |
|-------|---------|--------|
| 0 | Empty street | Light gray |
| 1 | Vehicle | Blue |
| 2 | Red traffic light | Red |
| 3 | Green traffic light | Green |
| 4 | Obstacle / building | Dark gray |
| 5 | Delivery stop | Yellow |
| 6 | Courier (delivery agent) | Orange |

### Von Neumann neighbourhood

Each cell considers only its four orthogonal neighbours — up, down, left,
right. Diagonal movement is **not** allowed. Vehicles follow the direction
assigned to their street and never change direction except by entering a
valid street segment.

### Transition rules (applied simultaneously)

1. A vehicle advances one cell in its assigned direction if the next cell is
   an empty street (state 0).
2. If the next cell holds another vehicle (state 1), the vehicle stays.
3. A vehicle meeting a red traffic light (state 2) stops.
4. When the light turns green (state 3), the vehicle proceeds if the next
   cell is free.
5. Obstacles (state 4) cannot be traversed.
6. Traffic lights alternate red/green after a configurable number of
   generations, using independent timers.
7. A vehicle reaching the end of a street leaves the grid; its previous cell
   becomes empty.
8. Two vehicles never occupy the same cell.
9. No diagonal movement or direction changes off a valid street.
10. All updates are simultaneous via a temporary grid, so no vehicle moves
   more than one cell per generation and no conflicts arise.
11. Stop cells (state 5) are ordinary streets for traffic; the courier (state 6)
   follows its precomputed path one cell per generation, obeying red lights and
   yielding to vehicles. It never shares a cell with another agent.
12. When the courier reaches a stop it is marked as delivered (dark dot) and
    the route continues; after the last stop it stops until repositioned.

Traffic lights are infrastructure, not vehicles: their state is independent
of vehicle movement and persists across generations.

## City generation

`CityGenerator` builds a connected road network automatically:

- Multiple horizontal and vertical one-way streets (directions alternate).
- A second, opposite-direction lane just inside every border (rows 1 and 39,
  columns 1 and 49), forming one-way couplets on all four sides. A short hook
  from `(0,1)` to `(0,0)` makes the whole network strongly connected, so no
  street cell is unreachable for the courier.
- Intersections where streets cross.
- A traffic light at every internal intersection (30 in the default layout).
- Obstacles (buildings) filling the blocks between streets.
- Entry/exit points on every grid edge, including the new reverse lanes
  (15 in total), so vehicles always have a valid route from one side of the
  city to the other.

## Vehicle generation

Vehicles are generated dynamically:

- Configurable generation rate (probability per generation).
- Random valid entry points on grid edges.
- Direction determined by the street they enter.
- Configurable maximum number of simultaneous vehicles.
- No spawning on occupied cells, traffic lights, or obstacles.

## Delivery courier

A single orange agent can be dropped anywhere on a street with **right click**.
Yellow stops are painted/unpainted with **left click** (only on street cells,
never on lights, obstacles or occupied cells). Dropping the courier — or editing
a stop while it is running — recomputes its route from its current position:

- A directed graph is built from the one-way street directions; at
  intersections the courier may continue or turn into the crossing street.
- Distances between all stops are computed with BFS.
- The visiting order is chosen greedily (nearest stop first) and refined with
  2-opt until no inversion shortens the tour.
- The full path is stitched together from BFS legs and validated step by step
  against the street directions. Stops that cannot be reached are reported as
  unreachable and skipped.

The courier respects red lights and vehicle occupancy just like any other
agent, and it stops after delivering the last reachable stop.

## Traffic light behaviour

Each traffic light is an independent object with:

- Configurable red duration and green duration (in generations).
- Its own timer; state flips when a duration elapses.
- Visual indication (red cell = state 2, green cell = state 3).
- Durations editable live through the interface sliders.

## Statistics (updated continuously)

- Total vehicles generated
- Active vehicles currently on the map
- Vehicles that exited the city
- Average vehicle travel time
- Average vehicle speed
- Congested cells (vehicles stopped 3+ consecutive generations)
- Traffic density percentage (active vehicles / road cells)
- Total simulation generations
- Courier status (idle / moving / done)
- Delivered stops / total stops, pending and unreachable stops
- Planned route length and generations since the courier started

## Default parameters

The simulation starts with a generation rate of 0.30, at most 60 vehicles,
an initial density of 0.35 and 60-generation red/green light durations. All of
these values can be changed freely with the sliders while the app is running.

## Architecture

- `CellularAutomaton` — owns the grid and applies one generation transition.
- `Vehicle` — identity, position, direction, waiting/travel time.
- `TrafficLight` — state and independent red/green timers.
- `Courier` — delivery agent and BFS/greedy/2-opt route planner (`courier.py`).
- `CityGenerator` — builds roads, intersections, lights and obstacles.
- `TrafficStatistics` — records metrics and history.
- `Simulation` — coordinates spawning, stepping and parameters.
- `UserInterface` — Pygame rendering, controls and statistics.

## Validation

- Simultaneous, conflict-free updates (temporary grid).
- Vehicles never share a cell; no diagonal moves.
- Red lights block entry; vehicles clear an intersection once inside.
- No spawning on occupied cells, lights or obstacles.
- Courier steps are legal one-way moves; it never overlaps a vehicle or enters
  a red light, and it delivers every reachable stop.
- Continuous run tested without crashes.

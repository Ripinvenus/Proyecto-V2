# 2D Cellular Automaton for Urban Traffic Flow and Congestion Simulation

An interactive, visually appealing traffic simulation built with **Python 3**,
**Pygame**, **NumPy** and **Matplotlib**. It models how vehicles move through a
city grid, how congestion develops, and how traffic lights influence
circulation — using a faithful two-dimensional cellular automaton.

## Project structure

```
traffic_simulation/
    main.py             # Entry point
    simulation.py       # Simulation coordinator (scenarios, spawning, step)
    cellular_automaton.py  # CA grid, vehicles, simultaneous transition rules
    vehicle.py          # Vehicle model (position, direction, waiting time)
    traffic_light.py    # Traffic light model (independent red/green timers)
    city_generator.py   # Road network, intersections, obstacles, lights
    statistics.py       # Real-time metrics and history
    interface.py        # Pygame rendering, controls, bar charts
    requirements.txt    # Python dependencies
    README.md           # This file
```

## Requirements

- Python 3.8+
- pygame
- numpy
- matplotlib (listed for completeness; charts are drawn with Pygame)

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
| Scenario A / B / C | Low / medium / high traffic presets |
| Toggle Charts | Show/hide the bar-chart panel |
| ESC | Quit |

## Cellular automaton theory

The simulated city is a two-dimensional grid. Each cell is one section of
street or an urban element and takes exactly one of five states:

| State | Meaning | Colour |
|-------|---------|--------|
| 0 | Empty street | Light gray |
| 1 | Vehicle | Blue |
| 2 | Red traffic light | Red |
| 3 | Green traffic light | Green |
| 4 | Obstacle / building | Dark gray |

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

Traffic lights are infrastructure, not vehicles: their state is independent
of vehicle movement and persists across generations.

## City generation

`CityGenerator` builds a connected road network automatically:

- Multiple horizontal and vertical one-way streets (directions alternate).
- Intersections where streets cross.
- A traffic light at every internal intersection.
- Obstacles (buildings) filling the blocks between streets.
- Entry/exit points on every grid edge so vehicles always have a valid route
  from one side of the city to the other.

## Vehicle generation

Vehicles are generated dynamically:

- Configurable generation rate (probability per generation).
- Random valid entry points on grid edges.
- Direction determined by the street they enter.
- Configurable maximum number of simultaneous vehicles.
- No spawning on occupied cells, traffic lights, or obstacles.

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

## Data visualization (bar charts)

Four bar charts are rendered live from recorded simulation data:

1. Active vehicles vs. vehicles that exited the city.
2. Traffic congestion levels over recent simulation intervals.
3. Vehicle generation vs. vehicle departure.
4. Traffic density under the current traffic-light configuration.

All charts are bar charts, as required.

## Experimental scenarios

| Scenario | Generation rate | Max vehicles | Initial density |
|----------|----------------|--------------|-----------------|
| A — Low traffic | 0.10 | 25 | 0.15 |
| B — Medium traffic | 0.30 | 60 | 0.35 |
| C — High traffic | 0.60 | 120 | 0.60 |

Switch scenarios to compare congestion levels. Traffic light durations can
also be experimented with independently.

## Architecture

- `CellularAutomaton` — owns the grid and applies one generation transition.
- `Vehicle` — identity, position, direction, waiting/travel time.
- `TrafficLight` — state and independent red/green timers.
- `CityGenerator` — builds roads, intersections, lights and obstacles.
- `TrafficStatistics` — records metrics and history.
- `Simulation` — coordinates spawning, stepping, scenarios and parameters.
- `UserInterface` — Pygame rendering, controls, statistics and charts.

## Validation

- Simultaneous, conflict-free updates (temporary grid).
- Vehicles never share a cell; no diagonal moves.
- Red lights block entry; vehicles clear an intersection once inside.
- No spawning on occupied cells, lights or obstacles.
- Continuous run tested without crashes.

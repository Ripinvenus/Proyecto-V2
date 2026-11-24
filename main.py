"""Entry point for the urban traffic cellular automaton simulation.

Run:
    python main.py
"""
from __future__ import annotations

from simulation import Simulation
from interface import UserInterface


def main():
    sim = Simulation(rows=41, cols=51)
    ui = UserInterface(sim)
    ui.run()


if __name__ == "__main__":
    main()

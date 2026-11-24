"""Pygame graphical interface for the traffic simulation.

Renders the city grid, vehicles, traffic lights and obstacles, a control
panel with buttons and configurable parameters and a compact real-time
statistics panel.
"""
from __future__ import annotations

import random

import pygame

from cellular_automaton import (
    EMPTY, VEHICLE, RED_LIGHT, GREEN_LIGHT, OBSTACLE, STOP, COURIER,
    DIR_NORTH, DIR_SOUTH, DIR_WEST, DIR_EAST,
)

# ------------------------------------------------------------------ colours
BG = (235, 238, 241)
PANEL = (245, 247, 250)
PANEL_BORDER = (200, 205, 210)
TEXT = (40, 50, 60)
TEXT_MUTED = (110, 120, 130)

COLORS = {
    EMPTY: (220, 222, 225),      # light gray street
    VEHICLE: (60, 110, 255),     # blue vehicle
    RED_LIGHT: (225, 60, 60),    # red traffic light
    GREEN_LIGHT: (60, 200, 90),  # green traffic light
    OBSTACLE: (70, 72, 78),      # dark gray building
    STOP: (255, 205, 40),        # yellow delivery stop
    COURIER: (255, 140, 30),     # orange delivery agent
}
INTERSECTION = (180, 185, 192)
GRID_LINE = (170, 175, 180)

BUTTON = (100, 140, 220)
BUTTON_HOVER = (120, 160, 235)
BUTTON_DISABLED = (170, 175, 180)
SLIDER_TRACK = (200, 205, 210)
SLIDER_FILL = (60, 110, 255)
SLIDER_KNOB = (255, 255, 255)

DIRECTION_MARKER = {
    DIR_NORTH: (0, -1),
    DIR_SOUTH: (0, 1),
    DIR_WEST: (-1, 0),
    DIR_EAST: (1, 0),
}

FPS = 60


# ------------------------------------------------------------------ helpers
def draw_text(surface, text, x, y, font, color=TEXT):
    img = font.render(text, True, color)
    surface.blit(img, (x, y))
    return img.get_width()


class Button:
    def __init__(self, rect, text, font, callback=None, enabled=True):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.callback = callback
        self.enabled = enabled
        self.hover = False

    def draw(self, surface):
        col = BUTTON if self.enabled else BUTTON_DISABLED
        if self.hover and self.enabled:
            col = BUTTON_HOVER
        pygame.draw.rect(surface, col, self.rect, border_radius=5)
        pygame.draw.rect(surface, PANEL_BORDER, self.rect, width=2, border_radius=5)
        img = self.font.render(self.text, True, (255, 255, 255) if self.enabled else TEXT_MUTED)
        surface.blit(img, img.get_rect(center=self.rect.center))

    def handle(self, event):
        if not self.enabled or event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        if self.rect.collidepoint(event.pos):
            if self.callback:
                self.callback()
            return True
        return False

    def update_hover(self, pos):
        self.hover = self.enabled and self.rect.collidepoint(pos)


class Slider:
    def __init__(self, rect, value, min_v, max_v, font, label, label_cb=None):
        self.rect = pygame.Rect(rect)
        self.min_v = min_v
        self.max_v = max_v
        self.value = value
        self.font = font
        self.label = label
        self.label_cb = label_cb
        self.dragging = False

    @property
    def fraction(self):
        span = self.max_v - self.min_v
        return (self.value - self.min_v) / span if span else 0.0

    def draw(self, surface):
        pygame.draw.rect(surface, SLIDER_TRACK, self.rect, border_radius=4)
        fill_w = int(self.rect.width * self.fraction)
        fill = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.height)
        pygame.draw.rect(surface, SLIDER_FILL, fill, border_radius=4)
        knob_x = self.rect.x + fill_w
        pygame.draw.circle(surface, SLIDER_KNOB, (knob_x, self.rect.centery), 9)
        pygame.draw.circle(surface, PANEL_BORDER, (knob_x, self.rect.centery), 9, width=1)
        if self.label_cb:
            txt = f"{self.label}: {self.label_cb(self.value)}"
        else:
            txt = f"{self.label}: {self.value:.2f}"
        draw_text(surface, txt, self.rect.x, self.rect.y - 20, self.font, TEXT)

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.dragging = True
                self._set_from_pos(event.pos[0])
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from_pos(event.pos[0])
            return True
        return False

    def _set_from_pos(self, x):
        x = max(self.rect.left, min(self.rect.right, x))
        frac = (x - self.rect.left) / self.rect.width
        self.value = self.min_v + frac * (self.max_v - self.min_v)


# ------------------------------------------------------------------ interface
class UserInterface:
    def __init__(self, sim):
        self.sim = sim
        pygame.init()
        self.font = pygame.font.SysFont(None, 20)
        self.small_font = pygame.font.SysFont(None, 17)
        self.title_font = pygame.font.SysFont(None, 22)

        try:
            desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        except Exception:
            info = pygame.display.Info()
            desktop_w = info.current_w or 1920
            desktop_h = info.current_h or 1080

        # Keep the whole window inside the visible desktop so nothing is cut off.
        self.width = min(1650, max(1100, desktop_w - 40))
        self.height = min(940, max(700, desktop_h - 60))
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("2D Cellular Automaton - Urban Traffic Flow")
        self.clock = pygame.time.Clock()

        # Without charts the side panels need much less room, so the city gets
        # the largest cell size that fits both width and height.
        min_right_w = 650
        max_grid_w = self.width - 40 - min_right_w
        max_grid_h = self.height - 40
        self.cell_size = max(7, min(20,
                                    max_grid_w // self.sim.ca.cols,
                                    max_grid_h // self.sim.ca.rows))
        self.grid_origin = (20, 20)

        self.buttons = []
        self.sliders = []
        # Fractional generations per frame are accumulated so speeds below 1x
        # advance the simulation every N frames instead of rounding up to 1.
        self._step_accumulator = 0.0

        self._build_controls()
        self.running = True

    def _build_controls(self):
        bx, by = 20, 20
        bw, bh, gap = 150, 32, 8

        def add(label, callback, enabled=True):
            b = Button((bx, by, bw, bh), label, self.font, callback, enabled)
            self.buttons.append(b)
            return b

        self.btn_start = add("Start", self.sim.start)
        self.btn_pause = add("Pause", self.sim.toggle_pause)
        self.btn_reset = add("Reset", self.sim.reset)
        self.btn_gen = add("Generate Vehicle", self._spawn_one)
        self.btn_clear = add("Clear Vehicles", self._clear_vehicles)
        self.btn_clear_route = add("Clear Route", self._clear_route)
        by += (bh + gap) * 6 + 14
        param_y = by + 4

        # Sliders / configurable parameters.
        self.sliders.append(Slider((bx, param_y, bw, 20),
                                   self.sim.gen_rate, 0.0, 1.0,
                                   self.small_font, "Generation rate",
                                   lambda v: f"{v:.2f}"))
        param_y += 56
        self.sliders.append(Slider((bx, param_y, bw, 20),
                                   float(self.sim.max_vehicles), 1, 300,
                                   self.small_font, "Max vehicles",
                                   lambda v: f"{int(v)}"))
        param_y += 56
        self.sliders.append(Slider((bx, param_y, bw, 20),
                                   float(self.sim.red_duration), 10, 300,
                                   self.small_font, "Red duration",
                                   lambda v: f"{int(v)}"))
        param_y += 56
        self.sliders.append(Slider((bx, param_y, bw, 20),
                                   float(self.sim.green_duration), 10, 300,
                                   self.small_font, "Green duration",
                                   lambda v: f"{int(v)}"))
        param_y += 56
        self.sliders.append(Slider((bx, param_y, bw, 20),
                                   self.sim.speed, 0.1, 10.0,
                                   self.small_font, "Sim. speed",
                                   lambda v: f"{v:.2f}x" if v < 1 else f"{v:.1f}x"))
        param_y += 56
        self.sliders.append(Slider((bx, param_y, bw, 20),
                                   self.sim.initial_density, 0.0, 1.0,
                                   self.small_font, "Initial density",
                                   lambda v: f"{v:.2f}"))
        self.params_bottom = param_y + 30

    def _spawn_one(self):
        if self.sim.entries:
            r, c, d = random.choice(self.sim.entries)
            self.sim.ca.spawn_vehicle(r, c, d)

    def _clear_vehicles(self):
        self.sim.ca.vehicles.clear()
        self.sim.ca.grid[self.sim.ca.grid == VEHICLE] = EMPTY

    def _clear_route(self):
        self.sim.ca.clear_route()

    def _cell_at(self, pos):
        """Translate a screen position to a (row, col) cell, or None."""
        ox, oy = self.grid_origin
        cs = self.cell_size
        ca = self.sim.ca
        x, y = pos
        if not (ox <= x < ox + ca.cols * cs and oy <= y < oy + ca.rows * cs):
            return None
        return (y - oy) // cs, (x - ox) // cs

    # ---------------------------------------------------------------- drawing
    def _is_intersection(self, ca, r, c):
        if not ca.has_road[r, c]:
            return False
        return (0 < c < ca.cols - 1 and ca.has_road[r, c - 1] and ca.has_road[r, c + 1]
                and 0 < r < ca.rows - 1 and ca.has_road[r - 1, c] and ca.has_road[r + 1, c])

    def draw_grid(self):
        ca = self.sim.ca
        ox, oy = self.grid_origin
        cs = self.cell_size
        for r in range(ca.rows):
            for c in range(ca.cols):
                x = ox + c * cs
                y = oy + r * cs
                state = ca.grid[r, c]
                if state == OBSTACLE:
                    color = COLORS[OBSTACLE]
                elif state == VEHICLE:
                    color = COLORS[VEHICLE]
                elif state == RED_LIGHT:
                    color = COLORS[RED_LIGHT]
                elif state == GREEN_LIGHT:
                    color = COLORS[GREEN_LIGHT]
                elif state == STOP:
                    color = COLORS[STOP]
                elif state == COURIER:
                    color = COLORS[COURIER]
                elif state == EMPTY and ca.has_road[r, c]:
                    color = INTERSECTION if self._is_intersection(ca, r, c) else COLORS[EMPTY]
                else:
                    color = COLORS[EMPTY]
                pygame.draw.rect(self.screen, color, (x, y, cs - 1, cs - 1))

        for v in self.sim.ca.vehicle_list():
            x = ox + v.col * cs + cs // 2
            y = oy + v.row * cs + cs // 2
            dr, dc = v.direction
            pygame.draw.circle(self.screen, (255, 255, 255), (x, y), max(2, cs // 3))
            pygame.draw.line(self.screen, (255, 255, 255), (x, y),
                             (x + dc * 3, y + dr * 3), 2)

        # Courier and delivered-stop markers.
        if ca.courier is not None:
            for r, c in ca.courier.delivered:
                if (r, c) in ca.stops:
                    x = ox + c * cs + cs // 2
                    y = oy + r * cs + cs // 2
                    pygame.draw.circle(self.screen, (110, 70, 0), (x, y),
                                       max(2, cs // 6))
            cour = ca.courier
            x = ox + cour.col * cs + cs // 2
            y = oy + cour.row * cs + cs // 2
            dr, dc = cour.direction
            pygame.draw.circle(self.screen, (255, 255, 255), (x, y), max(3, cs // 2))
            pygame.draw.line(self.screen, (255, 255, 255), (x, y),
                             (x + dc * 4, y + dr * 4), 2)

        gw = ca.cols * cs
        gh = ca.rows * cs
        pygame.draw.rect(self.screen, PANEL_BORDER, (ox, oy, gw, gh), width=2)

    def draw_panel(self):
        """Draw two compact columns to the right of the city.

        Controls/parameters sit in a middle column and the real-time statistics
        in a right column. Both panels are sized to their content instead of
        filling the window, leaving the city as large as possible.
        """
        rx = self.grid_origin[0] + self.sim.ca.cols * self.cell_size + 20
        top, bottom = 20, self.height - 20
        gap = 14
        ctrl_w = max(220, min(300, int((self.width - rx - 20) * 0.42)))
        stats_x = rx + ctrl_w + gap
        stats_w = self.width - stats_x - 20

        stats = self.sim.current_stats()
        lines = [
            ("Generation", f"{stats['generation']}"),
            ("Active vehicles", f"{stats['active']}"),
            ("Exited vehicles", f"{stats['exited']}"),
            ("Total generated", f"{stats['total_generated']}"),
            ("Congested cells", f"{stats['congested']}"),
            ("Traffic density", f"{stats['density']:.1f}%"),
            ("Avg travel time", f"{stats['avg_travel_time']:.1f} gen"),
            ("Avg speed", f"{stats['avg_speed']:.2f}"),
            ("Courier", stats["courier_status"]),
            ("Stops done", f"{stats['stops_done']}/{stats['stops_total']}"),
            ("Pending / unreach.", f"{stats['stops_pending']} / {stats['stops_unreachable']}"),
            ("Route / time", f"{stats['route_length']} / {stats['courier_time']} gen"),
        ]

        # ---- Measure content so the panels fit exactly ----
        ty = top + 6 + 26
        for b in self.buttons:
            b.rect.x = rx + 12
            b.rect.y = ty
            b.rect.width = ctrl_w - 24
            ty += b.rect.height + 8
        ty += 10 + 26
        for s in self.sliders:
            s.rect.x = rx + 12
            s.rect.y = ty
            s.rect.width = ctrl_w - 24
            ty += s.rect.height + 36
        ctrl_h = min(ty - top + 6, bottom - top)

        stats_bottom = top + 6 + 24 + len(lines) * 19 + 10
        stats_h = min(stats_bottom - top, bottom - top)

        # ---- Panel backgrounds ----
        pygame.draw.rect(self.screen, PANEL, (rx, top, ctrl_w, ctrl_h), border_radius=8)
        pygame.draw.rect(self.screen, PANEL_BORDER, (rx, top, ctrl_w, ctrl_h),
                         width=2, border_radius=8)
        pygame.draw.rect(self.screen, PANEL, (stats_x, top, stats_w, stats_h),
                         border_radius=8)
        pygame.draw.rect(self.screen, PANEL_BORDER, (stats_x, top, stats_w, stats_h),
                         width=2, border_radius=8)

        # ---- Controls + parameters ----
        ty = top + 6
        draw_text(self.screen, "Controls", rx + 12, ty, self.title_font)
        ty += 26
        for b in self.buttons:
            b.draw(self.screen)
            ty += b.rect.height + 8

        ty += 10
        draw_text(self.screen, "Parameters", rx + 12, ty, self.title_font)
        ty += 26
        for s in self.sliders:
            s.draw(self.screen)
            ty += s.rect.height + 36

        # ---- Statistics ----
        ty = top + 6
        draw_text(self.screen, "Real-time statistics", stats_x + 12, ty, self.title_font)
        ty += 24
        for label, value in lines:
            draw_text(self.screen, f"{label}:", stats_x + 12, ty, self.small_font, TEXT_MUTED)
            draw_text(self.screen, value, stats_x + 12 + 150, ty, self.small_font, TEXT)
            ty += 19

    def _apply_ui_params(self):
        self.sim.gen_rate = self.sliders[0].value
        self.sim.set_max_vehicles(int(self.sliders[1].value))
        self.sim.set_light_durations(int(self.sliders[2].value), int(self.sliders[3].value))
        self.sim.speed = self.sliders[4].value
        self.sim.initial_density = self.sliders[5].value

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    self.sim.toggle_pause()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                cell = self._cell_at(event.pos)
                if cell is not None:
                    if event.button == 1:
                        self.sim.ca.toggle_stop(*cell)
                    else:
                        self.sim.ca.place_courier(*cell)
            for b in self.buttons:
                b.handle(event)
            for s in self.sliders:
                s.handle(event)

    def run(self):
        while self.running:
            self._handle_events()
            self._apply_ui_params()

            mx, my = pygame.mouse.get_pos()
            for b in self.buttons:
                b.update_hover((mx, my))

            self.screen.fill(BG)
            self.draw_grid()
            self.draw_panel()

            if self.sim.running and not self.sim.paused:
                self._step_accumulator += self.sim.speed
                # Small tolerance avoids float drift (e.g. ten 0.1 steps).
                while self._step_accumulator + 1e-9 >= 1.0:
                    self.sim.step()
                    self._step_accumulator -= 1.0
            else:
                self._step_accumulator = 0.0

            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()

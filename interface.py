"""Pygame graphical interface for the traffic simulation.

Renders the city grid, vehicles, traffic lights and obstacles, a control
panel with buttons and configurable parameters, a real-time statistics
panel and four bar charts built from recorded simulation data.
"""
from __future__ import annotations

import random

import pygame

from cellular_automaton import (
    EMPTY, VEHICLE, RED_LIGHT, GREEN_LIGHT, OBSTACLE,
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


def draw_bar_chart(surface, rect, values, labels, title, color, font, title_font,
                   vmax=None, show_values=False):
    """Draw a vertical bar chart inside ``rect``. All charts are bar charts."""
    pygame.draw.rect(surface, PANEL, rect, border_radius=6)
    pygame.draw.rect(surface, PANEL_BORDER, rect, width=2, border_radius=6)
    draw_text(surface, title, rect.x + 10, rect.y + 7, title_font, TEXT)

    if not values:
        draw_text(surface, "no data", rect.x + 10, rect.y + 32, font, TEXT_MUTED)
        return

    plot_top = rect.y + 34
    plot_bottom = rect.bottom - 22
    plot_height = plot_bottom - plot_top
    n = len(values)
    mx = vmax if vmax else (max(values) or 1)
    step = (rect.width - 20) / n
    bar_w = max(4, step - 7)

    for i, val in enumerate(values):
        h = int((val / mx) * plot_height) if mx else 0
        bx = rect.x + 10 + i * step
        by = plot_bottom - h
        pygame.draw.rect(surface, color, (bx, by, bar_w, h), border_radius=2)
        if show_values:
            draw_text(surface, f"{val:.0f}", bx, by - 15, font, TEXT_MUTED)
        if i < len(labels):
            draw_text(surface, labels[i], bx, plot_bottom + 3, font, TEXT_MUTED)


# ------------------------------------------------------------------ interface
class UserInterface:
    def __init__(self, sim):
        self.sim = sim
        pygame.init()
        self.font = pygame.font.SysFont(None, 20)
        self.small_font = pygame.font.SysFont(None, 17)
        self.title_font = pygame.font.SysFont(None, 22)

        self.width = 1450
        self.height = 1000
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("2D Cellular Automaton - Urban Traffic Flow")
        self.clock = pygame.time.Clock()

        self.cell_size = 14
        self.grid_origin = (20, 20)

        self.buttons = []
        self.sliders = []
        self.scenario_buttons = []

        self._build_controls()
        self.show_charts = True
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
        self.btn_charts = add("Toggle Charts", self._toggle_charts)
        by += (bh + gap) * 6 + 14
        self.scenario_by = by + 4
        for i, key in enumerate(("A", "B", "C")):
            b = Button((bx + i * 52, self.scenario_by, 46, 26), key, self.font,
                       lambda k=key: self._set_scenario(k))
            self.scenario_buttons.append(b)
        self.scenario_by += 36

        # Sliders / configurable parameters.
        self.sliders.append(Slider((bx, self.scenario_by, bw, 20),
                                   self.sim.gen_rate, 0.0, 1.0,
                                   self.small_font, "Generation rate",
                                   lambda v: f"{v:.2f}"))
        self.scenario_by += 56
        self.sliders.append(Slider((bx, self.scenario_by, bw, 20),
                                   float(self.sim.max_vehicles), 1, 300,
                                   self.small_font, "Max vehicles",
                                   lambda v: f"{int(v)}"))
        self.scenario_by += 56
        self.sliders.append(Slider((bx, self.scenario_by, bw, 20),
                                   float(self.sim.red_duration), 10, 300,
                                   self.small_font, "Red duration",
                                   lambda v: f"{int(v)}"))
        self.scenario_by += 56
        self.sliders.append(Slider((bx, self.scenario_by, bw, 20),
                                   float(self.sim.green_duration), 10, 300,
                                   self.small_font, "Green duration",
                                   lambda v: f"{int(v)}"))
        self.scenario_by += 56
        self.sliders.append(Slider((bx, self.scenario_by, bw, 20),
                                   self.sim.speed, 1.0, 10.0,
                                   self.small_font, "Sim. speed",
                                   lambda v: f"{v:.1f}x"))
        self.scenario_by += 56
        self.sliders.append(Slider((bx, self.scenario_by, bw, 20),
                                   self.sim.initial_density, 0.0, 1.0,
                                   self.small_font, "Initial density",
                                   lambda v: f"{v:.2f}"))
        self.params_bottom = self.scenario_by + 30

    def _set_scenario(self, key):
        self.sim.set_scenario(key)
        self.sim.reset()

    def _spawn_one(self):
        if self.sim.entries:
            r, c, d = random.choice(self.sim.entries)
            self.sim.ca.spawn_vehicle(r, c, d)

    def _clear_vehicles(self):
        self.sim.ca.vehicles.clear()
        self.sim.ca.grid[self.sim.ca.grid == VEHICLE] = EMPTY

    def _toggle_charts(self):
        self.show_charts = not self.show_charts

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

        gw = ca.cols * cs
        gh = ca.rows * cs
        pygame.draw.rect(self.screen, PANEL_BORDER, (ox, oy, gw, gh), width=2)

    def draw_panel(self):
        px = self.grid_origin[0] + self.sim.ca.cols * self.cell_size + 30
        pw = self.width - px - 20
        panel_rect = pygame.Rect(px, 20, pw, self.height - 40)
        pygame.draw.rect(self.screen, PANEL, panel_rect, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_BORDER, panel_rect, width=2, border_radius=8)

        ty = 26
        draw_text(self.screen, "Controls", px + 12, ty, self.title_font)
        ty += 26
        for b in self.buttons:
            b.rect.x = px + 12
            b.rect.y = ty
            b.draw(self.screen)
            ty += b.rect.height + 8

        ty += 10
        draw_text(self.screen, "Scenario (A=Low, B=Medium, C=High)", px + 12, ty, self.small_font)
        ty += 20
        for i, b in enumerate(self.scenario_buttons):
            b.rect.x = px + 12 + i * 52
            b.rect.y = ty
            b.draw(self.screen)
        ty += 36

        draw_text(self.screen, "Parameters", px + 12, ty, self.title_font)
        ty += 26
        for s in self.sliders:
            s.rect.x = px + 12
            s.rect.y = ty
            s.draw(self.screen)
            ty += s.rect.height + 36

        ty += 10
        draw_text(self.screen, "Real-time statistics", px + 12, ty, self.title_font)
        ty += 24
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
        ]
        for label, value in lines:
            draw_text(self.screen, f"{label}:", px + 12, ty, self.small_font, TEXT_MUTED)
            draw_text(self.screen, value, px + 12 + 150, ty, self.small_font, TEXT)
            ty += 19

        chart_top = ty + 14
        chart_bottom = self.height - 24
        return px, pw, chart_top, chart_bottom

    def draw_charts(self, cx, cw, chart_top, chart_bottom):
        hist = self.sim.history()
        active = hist["active"]
        exited = hist["exited"]
        congested = hist["congested"]
        density = hist["density"]
        total_gen = hist["generations"] and self.sim.current_stats()["total_generated"] or 0
        total_ex = self.sim.current_stats()["total_exited"]

        ch = (chart_bottom - chart_top - 14) / 2
        cw2 = (cw - 24) / 2

        # 1. Active vs Exited (current).
        rect1 = pygame.Rect(cx, chart_top, cw2, ch)
        cur_active = active[-1] if active else 0
        cur_exited = exited[-1] if exited else 0
        draw_bar_chart(self.screen, rect1, [cur_active, cur_exited],
                       ["Active", "Exited"],
                       "1) Active vs Exited vehicles", (60, 110, 255),
                       self.small_font, self.title_font)

        # 2. Congestion over recent intervals.
        rect2 = pygame.Rect(cx + cw2 + 12, chart_top, cw2, ch)
        recent = congested[-10:] if congested else [0]
        labels2 = [f"t-{len(recent)-i}" for i in range(len(recent))]
        draw_bar_chart(self.screen, rect2, recent, labels2,
                       "2) Congested cells (recent)", (225, 60, 60),
                       self.small_font, self.title_font, show_values=True)

        # 3. Generation vs Departure.
        rect3 = pygame.Rect(cx, chart_top + ch + 14, cw2, ch)
        draw_bar_chart(self.screen, rect3, [total_gen, total_ex],
                       ["Generated", "Departed"],
                       "3) Generated vs Departed", (60, 180, 90),
                       self.small_font, self.title_font)

        # 4. Traffic density under current light configuration (recent).
        rect4 = pygame.Rect(cx + cw2 + 12, chart_top + ch + 14, cw2, ch)
        recent_d = density[-10:] if density else [0]
        labels4 = [f"t-{len(recent_d)-i}" for i in range(len(recent_d))]
        draw_bar_chart(self.screen, rect4, recent_d, labels4,
                       "4) Density % (current light config)", (220, 150, 40),
                       self.small_font, self.title_font, show_values=True)

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
            for b in self.buttons:
                b.handle(event)
            for b in self.scenario_buttons:
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
            for b in self.scenario_buttons:
                b.update_hover((mx, my))

            self.screen.fill(BG)
            self.draw_grid()
            cx, cw, chart_top, chart_bottom = self.draw_panel()

            steps = max(1, int(round(self.sim.speed)))
            if self.sim.running and not self.sim.paused:
                for _ in range(steps):
                    self.sim.step()

            if self.show_charts:
                self.draw_charts(cx, cw, chart_top, chart_bottom)

            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()

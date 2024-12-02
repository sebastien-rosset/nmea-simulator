#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk
import math
import numpy as np
from datetime import datetime
import time


class ControlPanel(tk.Frame):
    def __init__(self, master, simulator):
        super().__init__(master)
        self.simulator = simulator

        # True Wind Controls
        tws_frame = ttk.LabelFrame(self, text="True Wind")
        tws_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(tws_frame, text="TWS (knots):").grid(row=0, column=0, padx=5)
        self.tws_var = tk.DoubleVar(value=15.0)
        self.tws_slider = ttk.Scale(
            tws_frame,
            from_=0,
            to=60,
            variable=self.tws_var,
            orient="horizontal",
            command=self.update_simulator,
        )
        self.tws_slider.grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(tws_frame, text="TWD (degrees):").grid(row=1, column=0, padx=5)
        self.twd_var = tk.DoubleVar(value=180.0)
        self.twd_slider = ttk.Scale(
            tws_frame,
            from_=0,
            to=359,
            variable=self.twd_var,
            orient="horizontal",
            command=self.update_simulator,
        )
        self.twd_slider.grid(row=1, column=1, sticky="ew", padx=5)

        # Boat Motion Controls
        boat_frame = ttk.LabelFrame(self, text="Boat Motion")
        boat_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(boat_frame, text="SOG (knots):").grid(row=0, column=0, padx=5)
        self.sog_var = tk.DoubleVar(value=6.0)
        self.sog_slider = ttk.Scale(
            boat_frame,
            from_=0,
            to=15,
            variable=self.sog_var,
            orient="horizontal",
            command=self.update_simulator,
        )
        self.sog_slider.grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Label(boat_frame, text="COG (degrees):").grid(row=1, column=0, padx=5)
        self.cog_var = tk.DoubleVar(value=90.0)
        self.cog_slider = ttk.Scale(
            boat_frame,
            from_=0,
            to=359,
            variable=self.cog_var,
            orient="horizontal",
            command=self.update_simulator,
        )
        self.cog_slider.grid(row=1, column=1, sticky="ew", padx=5)

        # Mast Roll Effect Control
        roll_frame = ttk.LabelFrame(self, text="Roll Effect")
        roll_frame.pack(fill="x", padx=5, pady=5)

        self.roll_effect_var = tk.BooleanVar(value=True)
        self.roll_effect_check = ttk.Checkbutton(
            roll_frame,
            text="Enable Mast Roll Effect",
            variable=self.roll_effect_var,
            command=self.update_simulator,
        )
        self.roll_effect_check.pack(padx=5, pady=5)

        # Configure grid weights
        tws_frame.columnconfigure(1, weight=1)
        boat_frame.columnconfigure(1, weight=1)

    def update_simulator(self, *args):
        self.simulator.update_parameters(
            tws=self.tws_var.get(),
            twd=self.twd_var.get(),
            sog=self.sog_var.get(),
            cog=self.cog_var.get(),
            roll_effect=self.roll_effect_var.get(),
        )


class BoatDisplay(tk.Frame):
    def __init__(self, master, simulator):
        super().__init__(master)
        self.simulator = simulator

        # Configure the boat display
        self.canvas_size = (400, 300)  # width, height
        self.center = (self.canvas_size[0] // 2, self.canvas_size[1] // 2)

        # Create canvas
        self.canvas = tk.Canvas(
            self, width=self.canvas_size[0], height=self.canvas_size[1], bg="lightblue"
        )
        self.canvas.pack(pady=10)

        # Boat dimensions
        self.boat_width = 60
        self.boat_height = 20
        self.mast_height = 150  # pixels

        # Create boat elements
        self.hull = None
        self.mast = None
        self.waves = []
        self.heel_indicator = None
        self.heel_text = None
        self.create_waves()

        # Add heel angle label
        self.heel_label = tk.Label(self, text="Heel: 0°", font=("Arial", 12))
        self.heel_label.pack()

        # Start updates
        self.update_display()

    def create_waves(self):
        # Previous wave creation code remains the same
        wave_points = []
        for i in range(0, self.canvas_size[0] + 20, 20):
            wave_points.extend([i, self.center[1]])
        self.waves = self.canvas.create_line(
            wave_points, smooth=True, fill="blue", width=2
        )

    def draw_heel_indicator(self, x, y, roll_deg):
        # Delete old heel indicator if it exists
        if self.heel_indicator:
            self.canvas.delete(self.heel_indicator)
        if self.heel_text:
            self.canvas.delete(self.heel_text)

        # Draw arc for heel indicator
        radius = 40
        start_angle = -90 - 45  # Start 45 degrees to port
        end_angle = -90 + 45  # End 45 degrees to starboard

        # Create arc
        self.heel_indicator = self.canvas.create_arc(
            x - radius,
            y - radius,
            x + radius,
            y + radius,
            start=start_angle,
            extent=90,
            style="arc",
            outline="red",
            width=2,
        )

        # Draw indicator line
        line_x = x + radius * math.cos(math.radians(-90 + roll_deg))
        line_y = y + radius * math.sin(math.radians(-90 + roll_deg))
        self.heel_indicator = self.canvas.create_line(
            x, y, line_x, line_y, fill="red", width=2, arrow="last"
        )

        # Add heel angle text
        self.heel_text = self.canvas.create_text(
            x,
            y - radius - 10,
            text=f"{abs(roll_deg):.1f}°{'P' if roll_deg < 0 else 'S'}",
            font=("Arial", 10),
            fill="red",
        )

    def update_display(self):
        t = time.time()

        # Calculate roll angle
        roll = self.simulator.max_roll * np.sin(
            2 * np.pi * t / self.simulator.wave_period
        )
        roll_deg = math.degrees(roll)

        # Update wave position
        wave_points = []
        wave_amplitude = 20
        for i in range(0, self.canvas_size[0] + 20, 10):
            x = i
            y = self.center[1] + wave_amplitude * math.sin(
                2 * math.pi * (x / 100 - t / self.simulator.wave_period)
            )
            wave_points.extend([x, y])
        self.canvas.coords(self.waves, *wave_points)

        # Calculate boat position
        boat_center_y = self.center[1] + 10 * math.sin(
            2 * math.pi * t / self.simulator.wave_period
        )

        # Delete old boat elements
        if self.hull:
            self.canvas.delete(self.hull)
        if self.mast:
            self.canvas.delete(self.mast)

        # Draw hull
        hull_points = self.calculate_hull_points(
            self.center[0], boat_center_y, roll_deg
        )
        self.hull = self.canvas.create_polygon(hull_points, fill="gray")

        # Draw mast
        mast_base = (self.center[0], boat_center_y)
        mast_top = (
            self.center[0] + self.mast_height * math.sin(math.radians(roll_deg)),
            boat_center_y - self.mast_height * math.cos(math.radians(roll_deg)),
        )
        self.mast = self.canvas.create_line(
            mast_base[0], mast_base[1], mast_top[0], mast_top[1], fill="black", width=3
        )

        # Update heel indicator
        self.draw_heel_indicator(self.center[0], boat_center_y, roll_deg)

        # Update heel angle label
        self.heel_label.config(
            text=f"Heel: {abs(roll_deg):.1f}°{'Port' if roll_deg < 0 else 'Starboard'}"
        )

        # Schedule next update
        self.after(50, self.update_display)

    def calculate_hull_points(self, x, y, roll_deg):
        # Previous hull point calculation code remains the same
        points = [
            (-self.boat_width // 2, -self.boat_height // 2),
            (self.boat_width // 2, -self.boat_height // 2),
            (self.boat_width // 2, self.boat_height // 2),
            (-self.boat_width // 2, self.boat_height // 2),
        ]

        rotated_points = []
        for px, py in points:
            angle = math.radians(roll_deg)
            rx = px * math.cos(angle) - py * math.sin(angle)
            ry = px * math.sin(angle) + py * math.cos(angle)
            rotated_points.extend([x + rx, y + ry])

        return rotated_points


class WindDisplay(tk.Tk):
    def __init__(self, simulator):
        super().__init__()

        self.simulator = simulator
        self.title("Wind and Motion Simulator")

        # Create main container
        container = tk.Frame(self)
        container.pack(side="top", fill="both", expand=True)

        # Add control panel
        self.control_panel = ControlPanel(container, simulator)
        self.control_panel.pack(fill="x", padx=10, pady=5)

        # Configure the compass display
        self.canvas_size = 400
        self.center = self.canvas_size // 2
        self.compass_radius = 150

        # Create compass canvas
        self.canvas = tk.Canvas(
            container, width=self.canvas_size, height=self.canvas_size, bg="white"
        )
        self.canvas.pack(pady=20)

        # Create boat motion display
        self.boat_display = BoatDisplay(container, simulator)
        self.boat_display.pack()

        # Create data labels
        self.tws_label = tk.Label(container, text="TWS: 0.0 kts", font=("Arial", 14))
        self.tws_label.pack()
        self.twa_label = tk.Label(container, text="TWA: 0°", font=("Arial", 14))
        self.twa_label.pack()
        self.aws_label = tk.Label(container, text="AWS: 0.0 kts", font=("Arial", 14))
        self.aws_label.pack()
        self.awa_label = tk.Label(container, text="AWA: 0°", font=("Arial", 14))
        self.awa_label.pack()
        self.time_label = tk.Label(container, text="", font=("Arial", 10))
        self.time_label.pack()

        # Draw static compass elements
        self.draw_compass()

        # Create arrows for wind direction
        self.true_wind_arrow = self.canvas.create_line(
            self.center,
            self.center,
            self.center,
            self.center - self.compass_radius,
            arrow="last",
            width=3,
            fill="red",
        )
        self.apparent_wind_arrow = self.canvas.create_line(
            self.center,
            self.center,
            self.center,
            self.center - self.compass_radius,
            arrow="last",
            width=3,
            fill="blue",
        )

        # Start updates
        self.update_display()

    def draw_compass(self):
        # Draw compass circle
        self.canvas.create_oval(
            self.center - self.compass_radius,
            self.center - self.compass_radius,
            self.center + self.compass_radius,
            self.center + self.compass_radius,
            width=2,
        )

        # Draw compass points
        for i in range(0, 360, 30):
            angle = math.radians(i)
            # Outer point
            x1 = self.center + self.compass_radius * math.sin(angle)
            y1 = self.center - self.compass_radius * math.cos(angle)
            # Inner point
            x2 = self.center + (self.compass_radius - 10) * math.sin(angle)
            y2 = self.center - (self.compass_radius - 10) * math.cos(angle)
            # Draw tick
            self.canvas.create_line(x1, y1, x2, y2, width=2)

            # Add cardinal directions
            if i % 90 == 0:
                direction = (
                    "N" if i == 0 else "E" if i == 90 else "S" if i == 180 else "W"
                )
                text_x = self.center + (self.compass_radius - 30) * math.sin(angle)
                text_y = self.center - (self.compass_radius - 30) * math.cos(angle)
                self.canvas.create_text(
                    text_x, text_y, text=direction, font=("Arial", 12, "bold")
                )

    def update_arrow(self, arrow, angle, color):
        x = self.center + self.compass_radius * math.sin(math.radians(angle))
        y = self.center - self.compass_radius * math.cos(math.radians(angle))
        self.canvas.coords(arrow, self.center, self.center, x, y)
        self.canvas.itemconfig(arrow, fill=color)

    def update_display(self):
        t = time.time()
        tws, twd, aws, awa = self.simulator.calculate_all_wind(t)

        # Update arrows
        self.update_arrow(self.true_wind_arrow, twd, "red")
        self.update_arrow(self.apparent_wind_arrow, awa, "blue")

        # Update labels
        self.tws_label.config(text=f"TWS: {tws:.1f} kts")
        self.twa_label.config(text=f"TWA: {(twd - self.simulator.cog):.0f}°")
        self.aws_label.config(text=f"AWS: {aws:.1f} kts")
        self.awa_label.config(text=f"AWA: {awa:.0f}°")
        self.time_label.config(text=datetime.now().strftime("%H:%M:%S"))

        # Schedule next update
        self.after(100, self.update_display)


class WaveMotionSimulator:
    def __init__(self, mast_height=19.3, wave_height=2.0, wave_period=8.0):
        self.mast_height = mast_height
        self.wave_height = wave_height
        self.wave_period = wave_period

        # Wind parameters
        self.tws = 15.0  # True wind speed in knots
        self.twd = 180.0  # True wind direction in degrees
        self.sog = 6.0  # Speed over ground in knots
        self.cog = 90.0  # Course over ground in degrees
        self.roll_effect = True

        # Motion parameters
        self.base_max_roll = np.deg2rad(4)
        self.max_roll = self.base_max_roll * self.wave_height
        self.roll_damping = 0.7

    def update_parameters(
        self, tws=None, twd=None, sog=None, cog=None, roll_effect=None
    ):
        """Update simulation parameters"""
        if tws is not None:
            self.tws = tws
        if twd is not None:
            self.twd = twd
        if sog is not None:
            self.sog = sog
        if cog is not None:
            self.cog = cog
        if roll_effect is not None:
            self.roll_effect = roll_effect

    def calculate_apparent_wind(
        self, boat_speed, boat_direction, wind_speed, wind_direction
    ):
        """Calculate apparent wind speed and angle from true wind and boat motion"""
        # Convert to radians
        boat_dir_rad = math.radians(boat_direction)
        wind_dir_rad = math.radians(wind_direction)

        # Convert to vector components
        boat_x = boat_speed * math.sin(boat_dir_rad)
        boat_y = boat_speed * math.cos(boat_dir_rad)
        wind_x = wind_speed * math.sin(wind_dir_rad)
        wind_y = wind_speed * math.cos(wind_dir_rad)

        # Calculate relative wind components
        rel_x = wind_x - boat_x
        rel_y = wind_y - boat_y

        # Calculate apparent wind speed and direction
        aws = math.sqrt(rel_x**2 + rel_y**2)
        awa = math.degrees(math.atan2(rel_x, rel_y))
        if awa < 0:
            awa += 360

        return aws, awa

    def calculate_all_wind(self, t):
        """Calculate both true and apparent wind parameters"""
        # Convert speeds from knots to m/s for internal calculations
        tws_ms = self.tws * 0.514444
        sog_ms = self.sog * 0.514444

        # Calculate base apparent wind
        aws, awa = self.calculate_apparent_wind(sog_ms, self.cog, tws_ms, self.twd)

        # Add roll effect if enabled
        if self.roll_effect:
            roll = (
                self.max_roll
                * np.sin(2 * np.pi * t / self.wave_period)
                * np.exp(
                    -self.roll_damping * abs(np.sin(2 * np.pi * t / self.wave_period))
                )
            )
            roll_rate = (
                self.max_roll
                * (2 * np.pi / self.wave_period)
                * np.cos(2 * np.pi * t / self.wave_period)
            )

            # Calculate vertical velocity at masthead due to roll
            roll_velocity = roll_rate * self.mast_height

            # Add roll velocity to apparent wind speed
            aws = math.sqrt(aws**2 + roll_velocity**2)

        # Convert speed back to knots for display
        aws_kts = aws / 0.514444

        return self.tws, self.twd, aws_kts, awa


if __name__ == "__main__":
    # Create simulator instance
    simulator = WaveMotionSimulator(
        mast_height=19.3,  # Your Beneteau First 40 mast height
        wave_height=2.0,  # 2 meter significant wave height
        wave_period=8.0,  # 8 second wave period
    )

    # Create and run the display
    app = WindDisplay(simulator)
    app.mainloop()

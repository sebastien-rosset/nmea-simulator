#!/usr/bin/env python3

import tkinter as tk
import math
import numpy as np
from datetime import datetime
import time

c# Previous imports remain the same
import tkinter as tk
import math
import numpy as np
from datetime import datetime
import time

# WindDisplay and WaveMotionSimulator classes remain the same

class BoatDisplay(tk.Frame):
    def __init__(self, master, simulator):
        super().__init__(master)
        self.simulator = simulator
        
        # Configure the boat display
        self.canvas_size = (400, 300)  # width, height
        self.center = (self.canvas_size[0] // 2, self.canvas_size[1] // 2)
        
        # Create canvas
        self.canvas = tk.Canvas(self, width=self.canvas_size[0], 
                              height=self.canvas_size[1], bg='lightblue')
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
        self.heel_label = tk.Label(self, text="Heel: 0°", font=('Arial', 12))
        self.heel_label.pack()
        
        # Start updates
        self.update_display()
    
    def create_waves(self):
        # Previous wave creation code remains the same
        wave_points = []
        for i in range(0, self.canvas_size[0] + 20, 20):
            wave_points.extend([i, self.center[1]])
        self.waves = self.canvas.create_line(wave_points, smooth=True, 
                                           fill='blue', width=2)
    
    def draw_heel_indicator(self, x, y, roll_deg):
        # Delete old heel indicator if it exists
        if self.heel_indicator:
            self.canvas.delete(self.heel_indicator)
        if self.heel_text:
            self.canvas.delete(self.heel_text)
        
        # Draw arc for heel indicator
        radius = 40
        start_angle = -90 - 45  # Start 45 degrees to port
        end_angle = -90 + 45    # End 45 degrees to starboard
        
        # Create arc
        self.heel_indicator = self.canvas.create_arc(
            x - radius, y - radius,
            x + radius, y + radius,
            start=start_angle, extent=90,
            style='arc', outline='red', width=2
        )
        
        # Draw indicator line
        line_x = x + radius * math.cos(math.radians(-90 + roll_deg))
        line_y = y + radius * math.sin(math.radians(-90 + roll_deg))
        self.heel_indicator = self.canvas.create_line(
            x, y, line_x, line_y,
            fill='red', width=2, arrow='last'
        )
        
        # Add heel angle text
        self.heel_text = self.canvas.create_text(
            x, y - radius - 10,
            text=f"{abs(roll_deg):.1f}°{'P' if roll_deg < 0 else 'S'}",
            font=('Arial', 10), fill='red'
        )
    
    def update_display(self):
        t = time.time()
        
        # Calculate roll angle
        roll = self.simulator.max_roll * np.sin(2 * np.pi * t / self.simulator.wave_period)
        roll_deg = math.degrees(roll)
        
        # Update wave position
        wave_points = []
        wave_amplitude = 20
        for i in range(0, self.canvas_size[0] + 20, 10):
            x = i
            y = self.center[1] + wave_amplitude * math.sin(
                2 * math.pi * (x / 100 - t / self.simulator.wave_period))
            wave_points.extend([x, y])
        self.canvas.coords(self.waves, *wave_points)
        
        # Calculate boat position
        boat_center_y = self.center[1] + 10 * math.sin(
            2 * math.pi * t / self.simulator.wave_period)
        
        # Delete old boat elements
        if self.hull:
            self.canvas.delete(self.hull)
        if self.mast:
            self.canvas.delete(self.mast)
        
        # Draw hull
        hull_points = self.calculate_hull_points(self.center[0], boat_center_y, roll_deg)
        self.hull = self.canvas.create_polygon(hull_points, fill='gray')
        
        # Draw mast
        mast_base = (self.center[0], boat_center_y)
        mast_top = (
            self.center[0] + self.mast_height * math.sin(math.radians(roll_deg)),
            boat_center_y - self.mast_height * math.cos(math.radians(roll_deg))
        )
        self.mast = self.canvas.create_line(mast_base[0], mast_base[1], 
                                          mast_top[0], mast_top[1], 
                                          fill='black', width=3)
        
        # Update heel indicator
        self.draw_heel_indicator(self.center[0], boat_center_y, roll_deg)
        
        # Update heel angle label
        self.heel_label.config(
            text=f"Heel: {abs(roll_deg):.1f}°{'Port' if roll_deg < 0 else 'Starboard'}")
        
        # Schedule next update
        self.after(50, self.update_display)

    def calculate_hull_points(self, x, y, roll_deg):
        # Previous hull point calculation code remains the same
        points = [
            (-self.boat_width//2, -self.boat_height//2),
            (self.boat_width//2, -self.boat_height//2),
            (self.boat_width//2, self.boat_height//2),
            (-self.boat_width//2, self.boat_height//2)
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
        
        # Configure the compass display
        self.canvas_size = 400
        self.center = self.canvas_size // 2
        self.compass_radius = 150
        
        # Create compass canvas
        self.canvas = tk.Canvas(container, width=self.canvas_size, 
                              height=self.canvas_size, bg='white')
        self.canvas.pack(pady=20)
        
        # Create boat motion display
        self.boat_display = BoatDisplay(container, simulator)
        self.boat_display.pack()
        
        # Create data labels
        self.aws_label = tk.Label(container, text="AWS: 0.0 m/s", font=('Arial', 14))
        self.aws_label.pack()
        self.awa_label = tk.Label(container, text="AWA: 0°", font=('Arial', 14))
        self.awa_label.pack()
        self.time_label = tk.Label(container, text="", font=('Arial', 10))
        self.time_label.pack()
        
        # Draw static compass elements
        self.draw_compass()
        
        # Create arrow for wind direction
        self.arrow = self.canvas.create_line(self.center, self.center, 
                                           self.center, self.center - self.compass_radius,
                                           arrow='last', width=3, fill='blue')
        
        # Start updates
        self.update_display()
    
    def draw_compass(self):
        # Draw compass circle
        self.canvas.create_oval(
            self.center - self.compass_radius,
            self.center - self.compass_radius,
            self.center + self.compass_radius,
            self.center + self.compass_radius,
            width=2
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
                direction = 'N' if i == 0 else 'E' if i == 90 else 'S' if i == 180 else 'W'
                text_x = self.center + (self.compass_radius - 30) * math.sin(angle)
                text_y = self.center - (self.compass_radius - 30) * math.cos(angle)
                self.canvas.create_text(text_x, text_y, text=direction, 
                                      font=('Arial', 12, 'bold'))
    
    def update_arrow(self, angle):
        # Calculate arrow endpoints
        x = self.center + self.compass_radius * math.sin(math.radians(angle))
        y = self.center - self.compass_radius * math.cos(math.radians(angle))
        self.canvas.coords(self.arrow, self.center, self.center, x, y)
    
    def update_display(self):
        # Get new data from simulator
        t = time.time()
        speed, direction = self.simulator.calculate_apparent_wind(t)
        
        # Update arrow
        self.update_arrow(direction)
        
        # Update labels
        self.aws_label.config(text=f"AWS: {speed:.1f} m/s")
        self.awa_label.config(text=f"AWA: {direction:.0f}°")
        self.time_label.config(text=datetime.now().strftime('%H:%M:%S'))
        
        # Schedule next update
        self.after(100, self.update_display)

class WaveMotionSimulator:
    def __init__(self, mast_height=19.3, wave_height=2.0, wave_period=8.0):
        self.mast_height = mast_height
        self.wave_height = wave_height
        self.wave_period = wave_period
        
        # Derived parameters
        self.max_roll = np.deg2rad(25)  # Maximum roll angle in radians
        self.max_pitch = np.deg2rad(15)  # Maximum pitch angle in radians
        
    def calculate_apparent_wind(self, t):
        """Calculate apparent wind speed and direction at time t"""
        # Calculate boat motion components
        roll = self.max_roll * np.sin(2 * np.pi * t / self.wave_period)
        pitch = self.max_pitch * np.sin(2 * np.pi * t / self.wave_period + np.pi/4)
        
        # Calculate vertical velocity at masthead due to roll
        roll_velocity = self.mast_height * np.cos(roll) * (
            2 * np.pi / self.wave_period) * self.max_roll * np.cos(
            2 * np.pi * t / self.wave_period)
        
        # Calculate fore/aft velocity at masthead due to pitch
        pitch_velocity = self.mast_height * np.cos(pitch) * (
            2 * np.pi / self.wave_period) * self.max_pitch * np.cos(
            2 * np.pi * t / self.wave_period + np.pi/4)
        
        # Calculate apparent wind speed (vector sum of velocities)
        apparent_wind_speed = np.sqrt(roll_velocity**2 + pitch_velocity**2)
        
        # Calculate apparent wind direction
        apparent_wind_direction = np.rad2deg(np.arctan2(roll_velocity, pitch_velocity))
        # Convert to compass bearing (0-360)
        apparent_wind_direction = (apparent_wind_direction + 360) % 360
        
        return apparent_wind_speed, apparent_wind_direction

if __name__ == "__main__":
    # Create simulator instance
    simulator = WaveMotionSimulator(
        mast_height=19.3,  # Your Beneteau First 40 mast height
        wave_height=2.0,   # 2 meter significant wave height
        wave_period=8.0    # 8 second wave period
    )
    
    # Create and run the display
    app = WindDisplay(simulator)
    app.mainloop()
#!/usr/bin/env python3

import tkinter as tk
import math
import numpy as np
from datetime import datetime
import time

class WindDisplay(tk.Tk):
    def __init__(self, simulator):
        super().__init__()
        
        self.simulator = simulator
        self.title("Wind Display")
        
        # Configure the main window
        self.canvas_size = 400
        self.center = self.canvas_size // 2
        self.compass_radius = 150
        
        # Create canvas
        self.canvas = tk.Canvas(self, width=self.canvas_size, height=self.canvas_size, 
                              bg='white')
        self.canvas.pack(pady=20)
        
        # Create data labels
        self.aws_label = tk.Label(self, text="AWS: 0.0 m/s", font=('Arial', 14))
        self.aws_label.pack()
        self.awa_label = tk.Label(self, text="AWA: 0°", font=('Arial', 14))
        self.awa_label.pack()
        self.time_label = tk.Label(self, text="", font=('Arial', 10))
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
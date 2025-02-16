"""
NMEA Navigation Simulator
A simulator for generating NMEA and AIS messages for testing marine electronics.
"""

from .simulator import BasicNavSimulator
from .models.ais_vessel import AISVessel
from .models.speed_segment import SpeedSegment

__version__ = "0.1.0"
__author__ = "Your Name"

# Export main classes for easier imports
__all__ = [
    "BasicNavSimulator",
    "AISVessel",
    "SpeedSegment",
]

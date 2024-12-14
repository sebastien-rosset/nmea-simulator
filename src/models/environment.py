from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Current:
    """Water current information"""
    speed: float  # knots
    direction: float  # degrees true (direction flowing TOWARDS)
    
@dataclass
class Wind:
    """Wind information"""
    speed: float  # knots
    direction: float  # degrees true (direction coming FROM)

@dataclass
class Environment:
    """Environmental conditions container"""
    current: Current
    wind: Wind
    timestamp: datetime
    
class EnvironmentManager:
    """Manages environmental conditions for the simulation"""
    
    def __init__(self):
        self._current = Current(speed=0.0, direction=0.0)
        self._wind = Wind(speed=0.0, direction=0.0)
        self._timestamp = datetime.utcnow()
    
    def set_current(self, speed: float, direction: float):
        """
        Set water current parameters.
        
        Args:
            speed: Current speed in knots
            direction: Current direction in degrees true (direction flowing TOWARDS)
        """
        # Store direction as normalized 0-360
        normalized_direction = direction % 360
        self._current = Current(speed=speed, direction=normalized_direction)
        self._timestamp = datetime.utcnow()
    
    def set_wind(self, speed: float, direction: float):
        """
        Set wind parameters.
        
        Args:
            speed: Wind speed in knots
            direction: Wind direction in degrees true (direction coming FROM)
        """
        normalized_direction = direction % 360
        self._wind = Wind(speed=speed, direction=normalized_direction)
        self._timestamp = datetime.utcnow()
    
    @property
    def environment(self) -> Environment:
        """Get current environmental conditions"""
        return Environment(
            current=self._current,
            wind=self._wind,
            timestamp=self._timestamp
        )
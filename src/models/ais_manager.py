import time
import logging
from typing import List, Optional
from socket import socket
from .ais_vessel import AISVessel

class AISManager:
    """Manages AIS vessel simulation and message generation"""
    
    def __init__(self, update_interval: float = 10.0):
        """
        Initialize AIS manager.
        
        Args:
            update_interval: Seconds between AIS updates (default 10.0)
        """
        self.vessels: List[AISVessel] = []
        self.update_interval = update_interval
        self.last_update = 0
        
    def add_vessel(self, vessel: AISVessel):
        """Add a vessel to the AIS simulation"""
        self.vessels.append(vessel)
        logging.info(f"Added AIS vessel: {vessel.mmsi} - {vessel.vessel_name}")
        
    def add_vessels(self, vessels: List[AISVessel]):
        """Add multiple vessels to the AIS simulation"""
        for vessel in vessels:
            self.add_vessel(vessel)
            
    def remove_vessel(self, mmsi: int):
        """Remove a vessel by MMSI"""
        self.vessels = [v for v in self.vessels if v.mmsi != mmsi]
        
    def get_vessel(self, mmsi: int) -> Optional[AISVessel]:
        """Get vessel by MMSI"""
        for vessel in self.vessels:
            if vessel.mmsi == mmsi:
                return vessel
        return None

    def update_vessels(self, current_time: float, sock: socket, 
                      target_address: tuple) -> bool:
        """
        Update all AIS vessels and send messages.
        
        Args:
            current_time: Current simulation time
            sock: UDP socket for sending messages
            target_address: (host, port) tuple for message destination
            
        Returns:
            bool: True if updates were performed
        """
        # Initialize last_update if it's 0
        if self.last_update == 0:
            self.last_update = current_time
            return False

        # Only update at specified interval
        if current_time - self.last_update < self.update_interval:
            return False

        # Calculate actual time elapsed since last update
        actual_delta_time = current_time - self.last_update

        # Update each vessel
        for vessel in self.vessels:
            # Update vessel position using actual elapsed time
            vessel.update_position(actual_delta_time)

            # Update vessel status
            vessel.update_navigation_status()

            # Generate and send all AIS messages
            for message in vessel.generate_messages():
                logging.debug(f"AIS NMEA: {message.strip()}")
                sock.sendto(message.encode(), target_address)

        self.last_update = current_time
        return True
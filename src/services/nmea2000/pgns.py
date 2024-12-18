class PGN:
    """NMEA 2000 Parameter Group Numbers"""

    SYSTEM_TIME = 126992
    VESSEL_HEADING = 127250
    RATE_OF_TURN = 127251
    RUDDER = 127245
    SPEED = 128259
    WATER_DEPTH = 128267
    POSITION_RAPID = 129025
    COG_SOG_RAPID = 129026
    GNSS_POSITION = 129029
    XTE = 129283
    NAVIGATION_DATA = 129284
    WIND_DATA = 130306
    ENVIRONMENTAL = 130310
    ENVIRONMENTAL_PARAMS = 130311
    TEMPERATURE = 130312

    # PGN descriptions
    DESCRIPTIONS = {
        SYSTEM_TIME: "System Time",
        VESSEL_HEADING: "Vessel Heading",
        RATE_OF_TURN: "Rate of Turn",
        RUDDER: "Rudder",
        SPEED: "Speed",
        WATER_DEPTH: "Water Depth",
        POSITION_RAPID: "Position Rapid Update",
        COG_SOG_RAPID: "COG & SOG Rapid Update",
        GNSS_POSITION: "GNSS Position Data",
        XTE: "Cross Track Error",
        NAVIGATION_DATA: "Navigation Data",
        WIND_DATA: "Wind Data",
        ENVIRONMENTAL: "Environmental Parameters",
        ENVIRONMENTAL_PARAMS: "Environmental Parameters",
        TEMPERATURE: "Temperature",
    }

    @classmethod
    def get_description(cls, pgn: int) -> str:
        """Get human-readable description for a PGN"""
        return cls.DESCRIPTIONS.get(pgn, f"PGN {pgn}")

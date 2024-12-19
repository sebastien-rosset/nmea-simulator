import unittest
import logging
import struct
import math
from datetime import datetime
from src.services.nmea2000 import NMEA2000Message, NMEA2000Formatter, PGN
from src.services.nmea2000.converter import NMEA2000Converter
from src.services.nmea2000.utils import (
    encode_angle,
    decode_angle,
    encode_wind_speed,
    decode_wind_speed,
    encode_latlon,
    decode_latlon,
)


class TestNMEA2000Messages(unittest.TestCase):
    def setUp(self):
        self.formatter = NMEA2000Formatter()
        self.converter = NMEA2000Converter()
        # Enable debug logging
        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
        )

    def test_can_frame_structure(self):
        """Test basic CAN frame structure"""
        message = NMEA2000Message(
            pgn=PGN.VESSEL_HEADING,
            priority=2,
            source=0,
            destination=255,
            data=b"\xFF\x00\x00\x00\x00\x00\x00\x00",
        )

        frame = self.formatter.format_message(message)

        # Frame should be at least 13 bytes:
        # 4 bytes CAN ID + 1 byte length + 8 bytes data
        self.assertGreaterEqual(len(frame), 13)

        # Check CAN ID structure (29-bit)
        can_id = int.from_bytes(frame[0:4], "big")
        priority = (can_id >> 26) & 0x7
        pdu_format = (can_id >> 16) & 0xFF
        pdu_specific = (can_id >> 8) & 0xFF
        source_addr = can_id & 0xFF

        self.assertEqual(priority, 2)
        self.assertEqual(source_addr, 0)

    def test_position_rapid_message(self):
        """Test Position Rapid Update (PGN 129025) format"""
        lat = 37.8245
        lon = -122.3781

        # Convert lat/lon to raw integer values
        lat_raw = int(lat * 1e7)  # Convert to 1/10000000 degrees
        lon_raw = int(lon * 1e7)  # Convert to 1/10000000 degrees

        # For negative values, we need to handle two's complement
        if lat_raw < 0:
            lat_raw = lat_raw + (1 << 32)  # Convert to unsigned 32-bit
        if lon_raw < 0:
            lon_raw = lon_raw + (1 << 32)  # Convert to unsigned 32-bit

        logging.debug(f"Original: lat={lat}, lon={lon}")
        logging.debug(f"Raw integers: lat_raw={lat_raw}, lon_raw={lon_raw}")

        message = NMEA2000Message(
            pgn=PGN.POSITION_RAPID,
            priority=2,
            source=0,
            destination=255,
            data=struct.pack(
                "<II",  # Unsigned integers
                lat_raw & 0xFFFFFFFF,  # Ensure 32-bit value
                lon_raw & 0xFFFFFFFF,  # Ensure 32-bit value
            ),
        )

        frame = self.formatter.format_message(message)

        # Check data length (should be exactly 8 bytes)
        self.assertEqual(frame[4], 8)  # Length byte

        # Decode position data
        pos_data = frame[5:13]  # Skip header and length
        decoded_lat_raw, decoded_lon_raw = struct.unpack("<II", pos_data)

        # Convert back to signed values if necessary
        if decoded_lat_raw & (1 << 31):  # If highest bit is set
            decoded_lat_raw = decoded_lat_raw - (1 << 32)
        if decoded_lon_raw & (1 << 31):  # If highest bit is set
            decoded_lon_raw = decoded_lon_raw - (1 << 32)

        # Convert back to degrees
        decoded_lat = decoded_lat_raw / 1e7
        decoded_lon = decoded_lon_raw / 1e7

        logging.debug(
            f"Decoded raw: lat_raw={decoded_lat_raw}, lon_raw={decoded_lon_raw}"
        )
        logging.debug(f"Decoded degrees: lat={decoded_lat}, lon={decoded_lon}")

        # Compare with original values
        self.assertAlmostEqual(decoded_lat, lat, places=7)
        self.assertAlmostEqual(decoded_lon, lon, places=7)

    def test_cog_sog_message(self):
        """Test COG & SOG Rapid Update (PGN 129026) format"""
        cog = 45.7  # Course over ground in degrees
        sog = 10.5  # Speed over ground in knots

        # Normalize COG to 0-360 range
        cog = cog % 360

        # Convert to radians (NMEA 2000 uses radians)
        cog_rad = math.radians(cog)

        # Pack as radians (0 to 2π mapped to 0 to 65535)
        cog_raw = int((cog_rad / (2 * math.pi)) * 65535)
        sog_raw = int(sog * 100)  # Convert to 1/100 knot

        logging.debug(f"Original: cog={cog}, sog={sog}")
        logging.debug(f"Radians: cog_rad={cog_rad}")
        logging.debug(f"Raw values: cog_raw={cog_raw}, sog_raw={sog_raw}")

        message = NMEA2000Message(
            pgn=PGN.COG_SOG_RAPID,
            priority=2,
            source=0,
            destination=255,
            data=struct.pack(
                "<BBHH",
                0xFF,  # SID
                0,  # COG Reference (0 = True)
                cog_raw,  # COG in radians scaled to 16 bits
                sog_raw,  # SOG in 1/100 knot
            ),
        )

        frame = self.formatter.format_message(message)

        # Check data length
        self.assertEqual(frame[4], 6)

        # Decode data
        cog_sog_data = frame[5:11]
        sid, ref, decoded_cog_raw, decoded_sog_raw = struct.unpack(
            "<BBHH", cog_sog_data
        )

        # Convert back to degrees
        decoded_cog_rad = (decoded_cog_raw / 65535.0) * 2 * math.pi
        decoded_cog = math.degrees(decoded_cog_rad) % 360
        decoded_sog = decoded_sog_raw / 100.0

        logging.debug(
            f"Decoded raw: cog_raw={decoded_cog_raw}, sog_raw={decoded_sog_raw}"
        )
        logging.debug(f"Decoded values: cog={decoded_cog}, sog={decoded_sog}")

        self.assertEqual(sid, 0xFF)
        self.assertEqual(ref, 0)
        # Use 2 decimal places for angular values
        self.assertAlmostEqual(decoded_cog, cog, places=2)
        self.assertAlmostEqual(decoded_sog, sog, places=2)

    def test_vessel_heading_message(self):
        """Test Vessel Heading (PGN 127250) format"""
        heading = 175.5  # Degrees
        deviation = 2.0  # Degrees
        variation = -15.0  # Degrees

        # Normalize angles to 0-360
        heading = heading % 360
        deviation = deviation % 360
        variation = variation % 360

        # Convert to radians
        heading_rad = math.radians(heading)
        deviation_rad = math.radians(deviation)
        variation_rad = math.radians(variation)

        # Convert to 16-bit values (0 to 2π mapped to 0 to 65535)
        heading_raw = int((heading_rad / (2 * math.pi)) * 65535)
        deviation_raw = int((deviation_rad / (2 * math.pi)) * 65535)
        variation_raw = int((variation_rad / (2 * math.pi)) * 65535)

        logging.debug(f"Original: heading={heading}, dev={deviation}, var={variation}")
        logging.debug(
            f"Raw values: heading={heading_raw}, dev={deviation_raw}, var={variation_raw}"
        )

        message = NMEA2000Message(
            pgn=PGN.VESSEL_HEADING,
            priority=2,
            source=0,
            destination=255,
            data=struct.pack(
                "<BBHHHB",  # All angles as unsigned short
                0xFF,  # SID
                0,  # Heading Sensor Reference (0 = True)
                heading_raw,
                deviation_raw,
                variation_raw,
                0xFF,  # Reserved
            ),
        )

        frame = self.formatter.format_message(message)

        # Check data length
        self.assertEqual(frame[4], 9)

        # Decode heading data
        heading_data = frame[5:14]  # Skip header and length
        sid, ref, decoded_heading_raw, decoded_dev_raw, decoded_var_raw, reserved = (
            struct.unpack("<BBHHHB", heading_data)
        )

        # Convert back to degrees
        decoded_heading = (
            math.degrees((decoded_heading_raw / 65535.0) * 2 * math.pi) % 360
        )
        decoded_dev = math.degrees((decoded_dev_raw / 65535.0) * 2 * math.pi) % 360
        decoded_var = math.degrees((decoded_var_raw / 65535.0) * 2 * math.pi) % 360

        logging.debug(
            f"Decoded raw: heading={decoded_heading_raw}, dev={decoded_dev_raw}, var={decoded_var_raw}"
        )
        logging.debug(
            f"Decoded degrees: heading={decoded_heading}, dev={decoded_dev}, var={decoded_var}"
        )

        self.assertEqual(sid, 0xFF)
        self.assertEqual(ref, 0)
        # Use 2 decimal places for angular values
        self.assertAlmostEqual(decoded_heading, heading, places=2)
        self.assertAlmostEqual(decoded_dev, deviation, places=2)
        self.assertAlmostEqual(decoded_var, variation, places=2)

    def test_wind_data_message(self):
        """Test Wind Data (PGN 130306) format"""
        wind_speed = 15.7  # Knots
        wind_angle = 45.5  # Degrees

        # Convert using utility functions
        speed_raw = encode_wind_speed(wind_speed)
        angle_raw = encode_angle(wind_angle)

        logging.debug(f"Original: speed={wind_speed}kts, angle={wind_angle}°")
        logging.debug(f"Raw values: speed={speed_raw}, angle={angle_raw}")

        message = NMEA2000Message(
            pgn=PGN.WIND_DATA,
            priority=2,
            source=0,
            destination=255,
            data=struct.pack(
                "<BBHHH",
                0xFF,  # SID
                0,  # Wind Reference (0 = True)
                speed_raw,  # Wind Speed in 0.01 m/s
                angle_raw,  # Wind Angle in radians scaled to 16-bit
                0xFFFF,  # Reserved
            ),
        )

        frame = self.formatter.format_message(message)

        # Check data length (should be 8 bytes)
        self.assertEqual(frame[4], 8)

        # Decode wind data
        wind_data = frame[5:13]  # Skip header and length
        sid, ref, decoded_speed_raw, decoded_angle_raw, reserved = struct.unpack(
            "<BBHHH", wind_data
        )

        # Convert back to original units using utility functions
        decoded_speed_kts = decode_wind_speed(decoded_speed_raw)
        decoded_angle = decode_angle(decoded_angle_raw)

        logging.debug(
            f"Decoded raw: speed={decoded_speed_raw}, angle={decoded_angle_raw}"
        )
        logging.debug(
            f"Decoded values: speed={decoded_speed_kts}kts, angle={decoded_angle}°"
        )

        # Verify message structure
        self.assertEqual(sid, 0xFF)
        self.assertEqual(ref, 0)
        self.assertEqual(reserved, 0xFFFF)

        # Verify values match original input
        self.assertEqual(decoded_speed_kts, wind_speed)
        self.assertAlmostEqual(decoded_angle, wind_angle, places=2)


if __name__ == "__main__":
    unittest.main()

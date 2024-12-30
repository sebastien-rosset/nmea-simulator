# NMEA Simulator

A Python-based NMEA simulator for generating and testing NMEA maritime messages. This tool allows you to simulate various NMEA messages for testing marine electronics and applications.

## Features

- Generate standard NMEA messages
- Configurable message parameters
- Real-time simulation of vessel data
- Support for multiple NMEA sentence types
- GUI interface for easy control
- Customizable simulation scenarios

## Installation

This project uses Poetry for dependency management. To install:

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/nmea-simulator.git
   cd nmea-simulator
   ```

2. Install Poetry if you haven't already:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

3. Install dependencies:
   ```bash
   poetry install
   ```

## Requirements

- Python 3.12 or higher
- Dependencies (automatically installed by Poetry):
  - bitstring
  - numpy
  - tkinter
  - PyYAML

## Usage

1. Activate the Poetry virtual environment:
   ```bash
   poetry shell
   ```

2. Run the simulator:
   ```bash
   python main.py
   ```

## Configuration

The simulator can be configured using YAML files in the `config` directory. Example configuration:

1. [sf-bay-nmea-0183.yaml](config/sf-bay-nmea-0183.yaml)
2. [sf-bay-nmea-2000.yaml](config/sf-bay-nmea-2000.yaml)

## Project Structure

```
nmea-simulator/
├── config/        # Configuration files
├── src/           # Source code
├── tests/         # Test files
├── main.py        # Main entry point
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

## Author

Sebastien Rosset

## Copyright

Copyright (C) 2024 Sebastien Rosset

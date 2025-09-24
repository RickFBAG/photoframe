# Smart Display for Inky Impression 7.3"

Smart Display is a modular information board for the Inky Impression 7.3" (2025 edition) paired with a Raspberry Pi Zero 2 W.  
It renders a daily agenda, a concise news feed, and a market overview while keeping room for additional widgets in the future.  
The system is designed to run unattended, refreshing itself on a configurable cadence and exposing a lightweight configuration UI on the local network.

## Features

- **Agenda view** sourced from iCalendar feeds with focus on time, title, and location.
- **News feed** that ingests any RSS/Atom source and surfaces succinct headlines.
- **Market overview** displaying the latest quote and day change for a configured index or ticker (defaults to the "ETF All World" tracker).
- **Full-colour layout** tuned for the Inky Impression 7.3" panel (800×480) with clear typography and balanced colour palette.
- **Extensible widget framework**: shared widget lifecycle, layout management, and styling primitives make it straightforward to add new widgets.
- **Web-based control panel** served by the Pi for updating data sources, refresh intervals, and widget availability without SSH access.

## Hardware Requirements

- Raspberry Pi Zero 2 W running Raspberry Pi OS (Bookworm or later recommended).
- Inky Impression 7.3" (2025 edition) connected to the Pi's GPIO header.
- Reliable network connection for retrieving calendar, news, and market data feeds.

## Software Requirements

- Python 3.11+
- System packages: `libatlas-base-dev` (for NumPy used by the `inky` library), `libjpeg-dev`, `zlib1g-dev`, and fonts such as `fonts-dejavu`.

## Installation

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip libatlas-base-dev libjpeg-dev zlib1g-dev fonts-dejavu

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .
# On the Raspberry Pi with an Inky Impression attached install hardware drivers as well:
# pip install .[hardware]
```

The `pip install .` step uses the `pyproject.toml` provided in this repository to pull all required Python dependencies, including Pillow and Flask. Install the optional `hardware` extra (`pip install .[hardware]`) on the Raspberry Pi to add the Inky drivers.

## Configuration

Configuration is stored in `config/config.json`. The first run creates the file with sensible defaults.  
You can edit the file directly or use the built-in control panel.

Key options include:

- **Refresh cadence:** Global refresh interval in minutes for the display loop.
- **Widget toggles:** Enable/disable agenda, news, or market widgets.
- **Data sources:**
  - Agenda: list of iCalendar feed URLs plus per-feed look-ahead days and maximum events.
  - News: RSS/Atom feed URL and number of headlines to show.
  - Market: ticker symbol (default `EUNL.AS` for a global all-world ETF) and historical window.
- **Display options:** Rotation, border colour, and fallback image output when running without the Inky hardware attached.

Example snippet:

```json
{
  "refresh_minutes": 10,
  "display": {
    "rotation": 180,
    "border_colour": "white"
  },
  "agenda": {
    "enabled": true,
    "lookahead_days": 3,
    "max_events": 5,
    "calendars": [
      {
        "name": "Personal",
        "url": "https://calendar.google.com/calendar/ical/.../basic.ics"
      }
    ]
  }
}
```

When no events or headlines are available the widgets fall back to informative placeholders so the display still communicates its status.

## Running the Display Loop

After installation and configuration:

```bash
source .venv/bin/activate
python -m smart_display.app
```

The application runs an infinite refresh cycle.  
On each cycle it:

1. Reloads the latest configuration.
2. Fetches data for each active widget.
3. Renders the composed layout to an off-screen Pillow image.
4. Pushes the image to the Inky Impression panel (or saves to `output/latest.png` when the panel is not detected).

Use `CTRL+C` to stop the loop.

## Configuration Web UI

Start the configuration service on the Pi:

```bash
source .venv/bin/activate
python -m smart_display.web.server
```

The UI listens on `http://<raspberry-pi-ip>:8080` by default.  
It exposes:

- A responsive dashboard showing the current configuration.
- Forms for editing widget settings and refresh intervals.
- Buttons to trigger an on-demand refresh cycle or reboot the display process (implemented via HTTP hooks).

All changes are persisted to `config/config.json` and applied on the next refresh cycle of the main app.

> Run the UI alongside the display loop by launching it via systemd or tmux.  
> The web service is lightweight (Flask + vanilla HTML/JS) and suitable for the Pi Zero 2 W.

## Adding New Widgets

Widgets share a common lifecycle defined in `smart_display/widgets/base.py`:

1. Fetch data via a provider (`smart_display/data/*`).
2. Render within a bounding box using the shared colour palette and font utilities.

To add a widget:

1. Create a new provider in `smart_display/data/` that implements `fetch()` returning serialisable data.
2. Implement a widget class inheriting `Widget` and register it in `smart_display/widgets/factory.py` (or extend `WIDGET_REGISTRY`).
3. Update the configuration schema to expose the widget settings.
4. Adjust the layout in `smart_display/display/layout.py` to allocate a region on the canvas.

The main loop automatically picks up registered widgets that are enabled in the configuration file.

## Development & Testing

Install the optional development dependencies and run the test suite:

```bash
pip install .[dev]
pytest
```

The included tests cover configuration round-trips, layout calculations, and data provider fallbacks.  
Extend the suite as you add new widgets or features.

## Deployment Notes

- Use `systemd` services to start both the display loop and the configuration UI on boot.
- Configure log rotation for `/var/log/smart-display.log` if you redirect logs there.
- Keep update intervals mindful of API limits for calendar/news/market providers.
- The Pi Zero 2 W benefits from enabling swap (512 MB) to accommodate the Inky library and Pillow when handling large refreshes.

## License

This project is released under the MIT License.  
See [LICENSE](LICENSE) for details.


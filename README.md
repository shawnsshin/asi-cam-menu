# ASI Camera Menu-Driven Control

A terminal-based menu-driven Python script for controlling ZWO ASI cameras. This tool provides an interactive interface for configuring camera settings, capturing images in FITS format, and managing temperature control.

## Features

- Interactive terminal menu interface
- Real-time camera status monitoring (temperature, settings, cooler status)
- Temperature control and stabilization check
- Single image capture with verification
- Sequential capture mode (autorun) with temperature logging
- **Live preview** with auto or manual real-time exposure adjustment (OpenCV)
- FITS file output with metadata headers
- Configurable camera settings (gain, exposure, offset, USB bandwidth)
- JSON-based configuration management
- Supports both cooled and non-cooled ASI cameras

## Menu Structure

When you run the script, you'll see this menu in your terminal:

```
======================================================================
ASI CAMERA CONTROL MENU
======================================================================
1. View Camera Status
2. Temperature Control (Enable/Disable Cooler)
3. Change Camera Settings
4. Single Image Capture
5. Sequential Capture (Autorun)
6. Change Output Directory
7. Save Current Settings to Config
8. Live Preview
0. Exit
======================================================================
```

### Example Terminal Output

```
CAMERA STATUS
======================================================================

Camera Model: ZWO ASI533 Pro
Camera ID: 0
Max Resolution: 3008x3008

--- Temperature & Cooler ---
Current Temperature: 0.0°C
Cooler Status: ON
Target Temperature: 0.0°C
Cooler Power: 45%

--- Camera Settings ---
Gain: 100
Exposure: 1000000 μs (1.000 s)
Offset: 1
Bandwidth: 40
Image Type: RAW16

--- Output Settings ---
Output Directory: /path/to/captures
Next capture folder: /path/to/captures/20260109_143052
```

## Installation

### 1. Create Conda Environment

```bash
conda create -n asi_camera python=3.12
conda activate asi_camera
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Install ZWO ASI SDK

Download the ZWO ASI SDK from the official website or using the following link:
- [ZWO ASI SDK Download](https://dl.zwoastro.com/software?app=DeveloperCameraSdk&platform=windows86&region=Overseas)

Extract the SDK and note the path to the library file:
- **Windows**: `ASICamera2.dll`
- **macOS**: `libASICamera2.dylib`
- **Linux**: `libASICamera2.so`

### 4. Configure Library Path

Edit `menu_camera.py` and update the `LIBRARY_PATH` variable with the path to your SDK library:

```python
LIBRARY_PATH = '/path/to/your/libASICamera2.dll'  # Update this path
```

## Usage

### Run the Script

```bash
conda activate asi_camera
python menu_camera.py
```

### Configuration

The script uses a JSON configuration file (`config/camera_config.json`) to store default settings. If the file doesn't exist, it will be created automatically with default values on first run.

You can modify camera settings through the menu and save them using option 7.

### Live Preview

Select option 8 to open a live camera feed for checking object placement, focus, and framing. Choose between:

- **Auto Exposure**: Camera adjusts exposure automatically. Use `+`/`-` to adjust target brightness.
- **Manual Exposure**: Adjust exposure in real time with `+`/`-` keys (2x steps).

Press `a` to toggle between modes, `q` or `ESC` to quit. Uses RAW8 for faster frame rates and restores original settings on exit.

### Capturing Images

**Single Capture**: Select option 4 to capture a single image with current settings.

**Sequential Capture**: Select option 5 to capture multiple images automatically. You'll be prompted for:
- Number of images to capture
- Inter-capture delay (seconds)

Images are saved as FITS files with timestamped folders in the output directory.

## Output

- **FITS files**: Images are saved in FITS format with comprehensive headers including exposure time, gain, offset, temperature, and timing information
- **Temperature logs**: During sequential capture on cooled cameras, temperature is logged in CSV format in a `temp_log` subdirectory
- **Organized folders**: Each capture session creates a timestamped folder (e.g., `20260109_143052`)

## Requirements

- Python 3.12
- ZWO ASI Camera (connected via USB)
- ZWO ASI SDK library
- See `requirements.txt` for Python package dependencies

## Directory Structure

```
asi_sdk/
├── menu_camera.py          # Main script
├── requirements.txt        # Python dependencies
├── utils/                  # Utility modules
│   ├── temperature_control.py
│   ├── capture_utils.py
│   ├── temp_logger.py
│   └── live_preview.py
├── config/                 # Configuration files (auto-created)
│   └── camera_config.json
└── captures/              # Output directory (auto-created)
    └── YYYYMMDD_HHMMSS/   # Timestamped capture sessions
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

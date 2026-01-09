"""Menu-driven ASI camera control program."""

import sys
import os
import json
import signal
import time
import logging
from datetime import datetime
from pathlib import Path
import numpy as np
from astropy.io import fits
from tkinter import Tk, filedialog

# Suppress zwoasi warnings
logging.getLogger().setLevel(logging.ERROR)

import zwoasi as asi

# Import utilities
sys.path.insert(0, os.path.dirname(__file__))
from utils.temperature_control import stabilize_temperature, disable_cooler
from utils.capture_utils import capture_with_verification
from utils.temp_logger import TemperatureLogger

# Library path
LIBRARY_PATH = '/path/to/your/libASICamera2.dll'  # Update this path
CONFIG_FILE = 'config/camera_config.json'

# Global state
camera = None
cooler_enabled = False
config = None


def load_config(config_file=CONFIG_FILE):
    """Load configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Config file not found: {config_file}")
        print("Creating default configuration file...")

        # Create config directory if it doesn't exist
        config_path = Path(config_file)
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Get default config and save it
        default_config = get_default_config()
        if save_config(default_config, config_file):
            print(f"Default config file created: {config_file}")
        else:
            print("Failed to create config file. Using default configuration in memory.")

        return default_config
    except json.JSONDecodeError as e:
        print(f"Error parsing config file: {e}")
        print("Using default configuration.")
        return get_default_config()


def save_config(config, config_file=CONFIG_FILE):
    """Save configuration to JSON file."""
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def get_default_config():
    """Get default configuration."""
    return {
        "camera": {
            "gain": 100,
            "exposure_us": 1000000,
            "offset": 1,
            "bandwidth": 40
        },
        "temperature": {
            "use_cooler": False,
            "target_temp": 0,
            "temp_tolerance": 0.5,
            "idle_time": 420,
            "check_duration": 60
        },
        "capture": {
            "image_type": "RAW16",
            "output_dir": "captures",
            "filename_prefix": "image",
            "max_retries": 3,
            "check_dropped_frames": True
        },
        "autorun": {
            "num_images": 100,
            "inter_capture_delay": 1,
            "temp_log_interval": 5.0
        }
    }


def initialize_camera():
    """Initialize camera and apply settings from config."""
    global camera, config

    print("\n" + "=" * 70)
    print("INITIALIZING CAMERA")
    print("=" * 70)

    # Initialize SDK
    asi.init(LIBRARY_PATH)

    # Connect to camera
    camera = asi.Camera(0)

    # Wait for temperature sensor initialization
    print("Waiting for temperature sensor initialization...")
    time.sleep(0.5)

    # Get camera info
    camera_info = camera.get_camera_property()
    print(f"Camera: {camera_info['Name']}")
    print(f"Camera ID: {camera_info['CameraID']}")

    # Apply settings from config
    print("\nApplying settings from configuration...")
    apply_camera_settings(config['camera'])

    print("Camera initialized successfully!")
    return camera


def apply_camera_settings(settings):
    """Apply camera settings."""
    camera.set_control_value(asi.ASI_GAIN, settings['gain'])
    camera.set_control_value(asi.ASI_EXPOSURE, settings['exposure_us'])
    camera.set_control_value(asi.ASI_OFFSET, settings['offset'])
    camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, settings['bandwidth'])

    # Set image type
    if config['capture']['image_type'] == 'RAW16':
        camera.set_image_type(asi.ASI_IMG_RAW16)
    elif config['capture']['image_type'] == 'RAW8':
        camera.set_image_type(asi.ASI_IMG_RAW8)
    else:
        camera.set_image_type(asi.ASI_IMG_RAW16)


def show_menu():
    """Display main menu."""
    print("\n" + "=" * 70)
    print("ASI CAMERA CONTROL MENU")
    print("=" * 70)
    print("1. View Camera Status")
    print("2. Temperature Control (Enable/Disable Cooler)")
    print("3. Change Camera Settings")
    print("4. Single Image Capture")
    print("5. Sequential Capture (Autorun)")
    print("6. Change Output Directory")
    print("7. Save Current Settings to Config")
    print("0. Exit")
    print("=" * 70)


def option_view_status():
    """Option 1: View camera status."""
    print("\n" + "=" * 70)
    print("CAMERA STATUS")
    print("=" * 70)

    # Camera info
    camera_info = camera.get_camera_property()
    print(f"\nCamera Model: {camera_info['Name']}")
    print(f"Camera ID: {camera_info['CameraID']}")
    print(f"Max Resolution: {camera_info['MaxWidth']}x{camera_info['MaxHeight']}")

    # Temperature and cooler
    print("\n--- Temperature & Cooler ---")
    temp = camera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10.0
    cooler_power = camera.get_control_value(asi.ASI_COOLER_POWER_PERC)[0]
    cooler_on = camera.get_control_value(asi.ASI_COOLER_ON)[0]

    print(f"Current Temperature: {temp:.1f}°C")
    print(f"Cooler Status: {'ON' if cooler_on else 'OFF'}")
    if cooler_on:
        target_temp = camera.get_control_value(asi.ASI_TARGET_TEMP)[0] / 10.0
        print(f"Target Temperature: {target_temp:.1f}°C")
        print(f"Cooler Power: {cooler_power}%")

    # Camera settings
    print("\n--- Camera Settings ---")
    gain = camera.get_control_value(asi.ASI_GAIN)[0]
    exposure_us = camera.get_control_value(asi.ASI_EXPOSURE)[0]
    offset = camera.get_control_value(asi.ASI_OFFSET)[0]
    bandwidth = camera.get_control_value(asi.ASI_BANDWIDTHOVERLOAD)[0]

    print(f"Gain: {gain}")
    print(f"Exposure: {exposure_us} μs ({exposure_us/1_000_000:.3f} s)")
    print(f"Offset: {offset}")
    print(f"Bandwidth: {bandwidth}")
    print(f"Image Type: {config['capture']['image_type']}")

    # Output settings
    print("\n--- Output Settings ---")
    output_dir = Path(config['capture']['output_dir']).resolve()
    print(f"Output Directory: {output_dir}")
    next_dir = output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"Next capture folder: {next_dir}")


def option_temperature_control():
    """Option 2: Temperature control."""
    global cooler_enabled

    print("\n" + "=" * 70)
    print("TEMPERATURE CONTROL")
    print("=" * 70)

    # Check current status
    cooler_on = camera.get_control_value(asi.ASI_COOLER_ON)[0]
    temp = camera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10.0

    print(f"\nCurrent Temperature: {temp:.1f}°C")
    print(f"Cooler Status: {'ON' if cooler_on else 'OFF'}")

    print("\n1. Enable Cooler")
    print("2. Disable Cooler")
    print("0. Back to Main Menu")

    choice = input("\nSelect option: ").strip()

    if choice == "1":
        # Enable cooler
        target_temp = input(f"Enter target temperature (default: {config['temperature']['target_temp']}°C): ").strip()
        if target_temp == "":
            target_temp = config['temperature']['target_temp']
        else:
            try:
                target_temp = float(target_temp)
            except ValueError:
                print("Invalid temperature. Using default.")
                target_temp = config['temperature']['target_temp']

        print(f"\nEnabling cooler and stabilizing to {target_temp:.1f}°C...")
        print("This may take several minutes. Please wait...\n")

        cooler_enabled = stabilize_temperature(
            camera,
            target_temp=target_temp,
            use_cooler=True,
            temp_tolerance=config['temperature']['temp_tolerance'],
            idle_time=config['temperature']['idle_time'],
            check_duration=config['temperature']['check_duration']
        )

        if cooler_enabled:
            print("\nCooler enabled and temperature stabilized!")
        else:
            print("\nCooler disabled (use_cooler=False in function).")

    elif choice == "2":
        # Disable cooler
        if cooler_on:
            print("\nDisabling cooler...")
            disable_cooler(camera)
            cooler_enabled = False
            print("Cooler disabled.")
        else:
            print("\nCooler is already off.")

    elif choice == "0":
        return
    else:
        print("Invalid option.")


def option_change_settings():
    """Option 3: Change camera settings."""
    global config

    while True:
        print("\n" + "=" * 70)
        print("CHANGE CAMERA SETTINGS")
        print("=" * 70)

        # Display current settings
        gain = camera.get_control_value(asi.ASI_GAIN)[0]
        exposure_us = camera.get_control_value(asi.ASI_EXPOSURE)[0]
        offset = camera.get_control_value(asi.ASI_OFFSET)[0]
        bandwidth = camera.get_control_value(asi.ASI_BANDWIDTHOVERLOAD)[0]

        print(f"\nCurrent Settings:")
        print(f"  1. Gain: {gain} (range: 0-600)")
        print(f"  2. Exposure: {exposure_us} μs ({exposure_us/1_000_000:.3f} s)")
        print(f"  3. Offset: {offset} (range: 0-100)")
        print(f"  4. Bandwidth: {bandwidth} (range: 40-100)")
        print(f"  0. Back to Main Menu")

        choice = input("\nSelect setting to change: ").strip()

        if choice == "1":
            # Change gain
            new_value = input(f"Enter new gain (0-600, current: {gain}): ").strip()
            try:
                new_value = int(new_value)
                if 0 <= new_value <= 600:
                    camera.set_control_value(asi.ASI_GAIN, new_value)
                    config['camera']['gain'] = new_value
                    print(f"Gain set to {new_value}")
                else:
                    print("Gain must be between 0 and 600.")
            except ValueError:
                print("Invalid value.")

        elif choice == "2":
            # Change exposure
            new_value = input(f"Enter new exposure in μs (current: {exposure_us}): ").strip()
            try:
                new_value = int(new_value)
                if new_value > 0:
                    camera.set_control_value(asi.ASI_EXPOSURE, new_value)
                    config['camera']['exposure_us'] = new_value
                    print(f"Exposure set to {new_value} μs ({new_value/1_000_000:.3f} s)")
                else:
                    print("Exposure must be positive.")
            except ValueError:
                print("Invalid value.")

        elif choice == "3":
            # Change offset
            new_value = input(f"Enter new offset (0-100, current: {offset}): ").strip()
            try:
                new_value = int(new_value)
                if 0 <= new_value <= 100:
                    camera.set_control_value(asi.ASI_OFFSET, new_value)
                    config['camera']['offset'] = new_value
                    print(f"Offset set to {new_value}")
                else:
                    print("Offset must be between 0 and 100.")
            except ValueError:
                print("Invalid value.")

        elif choice == "4":
            # Change bandwidth
            new_value = input(f"Enter new bandwidth (40-100, current: {bandwidth}): ").strip()
            try:
                new_value = int(new_value)
                if 40 <= new_value <= 100:
                    camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, new_value)
                    config['camera']['bandwidth'] = new_value
                    print(f"Bandwidth set to {new_value}")
                else:
                    print("Bandwidth must be between 40 and 100.")
            except ValueError:
                print("Invalid value.")

        elif choice == "0":
            break
        else:
            print("Invalid option.")


def option_single_capture():
    """Option 4: Single image capture."""
    print("\n" + "=" * 70)
    print("SINGLE IMAGE CAPTURE")
    print("=" * 70)

    # Create output directory
    output_dir = Path(config['capture']['output_dir']) / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        print("\nCapturing image...")

        # Capture image
        img_array, timing = capture_with_verification(
            camera,
            max_retries=config['capture']['max_retries'],
            check_dropped_frames=config['capture']['check_dropped_frames']
        )

        # Get current settings for FITS header
        gain = camera.get_control_value(asi.ASI_GAIN)[0]
        offset = camera.get_control_value(asi.ASI_OFFSET)[0]
        bandwidth = camera.get_control_value(asi.ASI_BANDWIDTHOVERLOAD)[0]
        temp = camera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10.0

        # Create FITS file
        filename = output_dir / f"{config['capture']['filename_prefix']}_001.fits"

        # Create FITS header
        header = fits.Header()
        header['EXPOSURE'] = (timing['set_exposure_us'], 'Exposure time in us')
        header['GAIN'] = (gain, 'The ratio of output / input')
        header['OFFSET'] = (offset, 'Brightness offset')
        header['USBBW'] = (bandwidth, 'USB bandwidth setting')
        header['CMOSTEMP'] = (temp, 'CMOS sensor temperature in C')
        header['DATE-OBS'] = (timing['capture_start_time'].isoformat(), 'UTC start of observation')
        header['EXPTIME'] = (timing['set_exposure_s'], 'Light collection time (s)')
        header['EXPMEAS'] = (round(timing['exposure_plus_readout_s'], 6), 'Measured time incl. readout (s)')
        header['DRPFRM'] = (timing['dropped_frames'], 'Dropped frames count')
        header['COLORTYP'] = ('RAW16', 'Color space, such as RAW8,RAW16,RGB24')
        header['INPUTFMT'] = ('FITS', 'Format of file from which image was read')

        # Save FITS file
        hdu = fits.PrimaryHDU(img_array, header=header)
        hdu.writeto(filename, overwrite=True)

        print(f"\nImage saved: {filename}")
        print(f"Image shape: {img_array.shape}")
        print(f"Data type: {img_array.dtype}")
        print(f"\nTiming:")
        print(f"  Set exposure: {timing['set_exposure_s']:.3f} s")
        print(f"  Exposure + readout: {timing['exposure_plus_readout_s']:.3f} s")
        print(f"  Transfer time: {timing['transfer_time_s']:.3f} s")
        print(f"  Total time: {timing['total_time_s']:.3f} s")
        print(f"  Dropped frames: {timing['dropped_frames']}")

    except Exception as e:
        print(f"Error during capture: {e}")


def option_sequential_capture():
    """Option 5: Sequential capture (autorun)."""
    print("\n" + "=" * 70)
    print("SEQUENTIAL CAPTURE (AUTORUN)")
    print("=" * 70)

    # Get parameters
    num_images_str = input(f"Number of images (default: {config['autorun']['num_images']}): ").strip()
    if num_images_str == "":
        num_images = config['autorun']['num_images']
    else:
        try:
            num_images = int(num_images_str)
        except ValueError:
            print("Invalid number. Using default.")
            num_images = config['autorun']['num_images']

    delay_str = input(f"Inter-capture delay in seconds (default: {config['autorun']['inter_capture_delay']}): ").strip()
    if delay_str == "":
        delay = config['autorun']['inter_capture_delay']
    else:
        try:
            delay = float(delay_str)
        except ValueError:
            print("Invalid delay. Using default.")
            delay = config['autorun']['inter_capture_delay']

    # Create output directory
    output_dir = Path(config['capture']['output_dir']) / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create temp_log subdirectory
    temp_log_dir = output_dir / "temp_log"
    temp_log_dir.mkdir(exist_ok=True)

    print(f"\nCapturing {num_images} images to {output_dir}")
    print(f"Inter-capture delay: {delay} s")
    print("Starting capture sequence...\n")

    successful_captures = 0
    failed_captures = 0
    start_time = time.time()

    for i in range(1, num_images + 1):
        print(f"\n{'─' * 70}")
        print(f"IMAGE {i}/{num_images}")
        print(f"{'─' * 70}")

        try:
            # Create temperature logger
            log_file = temp_log_dir / f"temp_log_{i:04d}.csv"
            temp_logger = TemperatureLogger(
                camera,
                log_file,
                interval=config['autorun']['temp_log_interval']
            )

            # Start exposure and temperature logging
            exposure_start = time.time()
            camera.start_exposure()
            temp_logger.start(exposure_start)

            # Poll for completion
            while camera.get_exposure_status() == asi.ASI_EXP_WORKING:
                time.sleep(0.001)

            # Stop logger
            temp_logger.stop()

            # Check status and get data
            exposure_end = time.time()
            status = camera.get_exposure_status()
            if status != asi.ASI_EXP_SUCCESS:
                raise asi.ZWO_CaptureError(f'Exposure failed with status {status}', status)

            # Get data
            data = camera.get_data_after_exposure()

            # Convert to numpy array
            whbi = camera.get_roi_format()
            shape = [whbi[1], whbi[0]]
            if whbi[3] == asi.ASI_IMG_RAW16:
                img_array = np.frombuffer(data, dtype=np.uint16)
            elif whbi[3] == asi.ASI_IMG_RAW8:
                img_array = np.frombuffer(data, dtype=np.uint8)
            else:
                img_array = np.frombuffer(data, dtype=np.uint8)
            img_array = img_array.reshape(shape)

            # Get settings for FITS header
            gain = camera.get_control_value(asi.ASI_GAIN)[0]
            exposure_us = camera.get_control_value(asi.ASI_EXPOSURE)[0]
            offset = camera.get_control_value(asi.ASI_OFFSET)[0]
            bandwidth = camera.get_control_value(asi.ASI_BANDWIDTHOVERLOAD)[0]
            temp = camera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10.0

            # Create FITS file
            filename = output_dir / f"{config['capture']['filename_prefix']}_{i:04d}.fits"

            # Create FITS header
            header = fits.Header()
            header['EXPOSURE'] = (exposure_us, 'Exposure time in us')
            header['GAIN'] = (gain, 'The ratio of output / input')
            header['OFFSET'] = (offset, 'Brightness offset')
            header['USBBW'] = (bandwidth, 'USB bandwidth setting')
            header['CMOSTEMP'] = (temp, 'CMOS sensor temperature in C')
            header['DATE-OBS'] = (datetime.fromtimestamp(exposure_start).isoformat(), 'UTC start of observation')
            header['EXPTIME'] = (exposure_us / 1_000_000, 'Light collection time (s)')
            header['COLORTYP'] = ('RAW16', 'Color space, such as RAW8,RAW16,RGB24')
            header['INPUTFMT'] = ('FITS', 'Format of file from which image was read')
            header['IMGNUM'] = (i, 'Image number in sequence')

            # Save FITS file
            hdu = fits.PrimaryHDU(img_array, header=header)
            hdu.writeto(filename, overwrite=True)

            print(f"✓ Image saved: {filename.name}")
            print(f"  Temperature log: temp_log/{log_file.name}")
            print(f"  Exposure + Readout time: {exposure_end - exposure_start:.3f} s")
            print(f"  Temperature: {temp:.1f}°C")

            successful_captures += 1

            # Inter-capture delay
            if i < num_images and delay > 0:
                print(f"  Waiting {delay} s before next capture...")
                time.sleep(delay)

        except Exception as e:
            print(f"✗ ERROR: {e}")
            failed_captures += 1

    # Summary
    end_time = time.time()
    total_time = end_time - start_time

    print(f"\n{'=' * 70}")
    print("CAPTURE SEQUENCE COMPLETE")
    print(f"{'=' * 70}")
    print(f"Successful captures: {successful_captures}/{num_images}")
    print(f"Failed captures: {failed_captures}/{num_images}")
    print(f"Total time: {total_time:.1f} s")
    print(f"Average time per image: {total_time/num_images:.1f} s")
    print(f"Output directory: {output_dir}")


def option_change_output_directory():
    """Option 6: Change output directory."""
    global config

    print("\n" + "=" * 70)
    print("CHANGE OUTPUT DIRECTORY")
    print("=" * 70)

    current_dir = Path(config['capture']['output_dir']).resolve()
    print(f"\nCurrent directory: {current_dir}")
    print("\nOpening file browser...")

    # Hide the tkinter root window
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    # Open directory browser
    new_dir = filedialog.askdirectory(
        title="Select Output Directory",
        initialdir=str(current_dir)
    )

    # Destroy the tkinter window
    root.destroy()

    if new_dir:
        # Update config with new directory
        config['capture']['output_dir'] = new_dir
        print(f"\nOutput directory changed to: {new_dir}")

        # Ask if user wants to save to config file
        save_choice = input("Save as default in config file? (y/n): ").strip().lower()
        if save_choice == 'y':
            if save_config(config):
                print("Config file updated.")
            else:
                print("Failed to update config file.")
        else:
            print("Change applied for this session only.")
    else:
        print("\nNo directory selected. Output directory unchanged.")


def option_save_config():
    """Option 7: Save current settings to config."""
    print("\n" + "=" * 70)
    print("SAVE SETTINGS TO CONFIG")
    print("=" * 70)

    print("\nCurrent settings will be saved to config file.")
    confirm = input("Continue? (y/n): ").strip().lower()

    if confirm == 'y':
        if save_config(config):
            print(f"Settings saved to {CONFIG_FILE}")
        else:
            print("Failed to save settings.")
    else:
        print("Save cancelled.")


def shutdown(_signum=None, _frame=None):
    """Graceful shutdown handler."""
    global camera, cooler_enabled

    print("\n\nShutting down...")

    if camera and cooler_enabled:
        print("Disabling cooler...")
        disable_cooler(camera)

    print("Camera session ended. Goodbye!")
    sys.exit(0)


def main():
    """Main program loop."""
    global camera, cooler_enabled, config

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("\n" + "=" * 70)
    print("ASI CAMERA MENU-DRIVEN CONTROL PROGRAM")
    print("=" * 70)

    # Load configuration
    config = load_config()

    # Initialize camera
    try:
        camera = initialize_camera()
    except Exception as e:
        print(f"Error initializing camera: {e}")
        sys.exit(1)

    # Optional: Enable cooler at startup if configured
    if config['temperature']['use_cooler']:
        print("\n" + "=" * 70)
        print("TEMPERATURE CONTROL (Startup)")
        print("=" * 70)
        print("\nCooler is configured to start at startup.")
        print(f"Target temperature: {config['temperature']['target_temp']}°C")

        start_cooler = input("Enable cooler now? (y/n): ").strip().lower()
        if start_cooler == 'y':
            print("\nEnabling cooler and stabilizing temperature...")
            print("This may take several minutes. Please wait...\n")

            cooler_enabled = stabilize_temperature(
                camera,
                target_temp=config['temperature']['target_temp'],
                use_cooler=True,
                temp_tolerance=config['temperature']['temp_tolerance'],
                idle_time=config['temperature']['idle_time'],
                check_duration=config['temperature']['check_duration']
            )

            if cooler_enabled:
                print("\nCooler enabled and temperature stabilized!")

    # Main menu loop
    while True:
        try:
            show_menu()
            choice = input("\nSelect option: ").strip()

            if choice == "1":
                option_view_status()
            elif choice == "2":
                option_temperature_control()
            elif choice == "3":
                option_change_settings()
            elif choice == "4":
                option_single_capture()
            elif choice == "5":
                option_sequential_capture()
            elif choice == "6":
                option_change_output_directory()
            elif choice == "7":
                option_save_config()
            elif choice == "0":
                shutdown()
            else:
                print("Invalid option. Please try again.")

        except KeyboardInterrupt:
            shutdown()
        except Exception as e:
            print(f"\nError: {e}")
            print("Returning to main menu...")


if __name__ == "__main__":
    main()

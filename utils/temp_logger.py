"""Temperature logging during camera exposures."""

import threading
import time
from datetime import datetime
import zwoasi as asi


class TemperatureLogger:
    """
    Logs camera temperature and cooler power during exposure in a background thread.

    This class creates a background thread that periodically polls the camera's
    temperature sensor and cooler power percentage during an exposure, writing
    the data to a CSV file.
    """

    def __init__(self, camera, log_file, interval=5.0):
        """
        Initialize the temperature logger.

        Args:
            camera: ZWO ASI camera object
            log_file: Path to CSV file for logging
            interval: Polling interval in seconds (default: 5.0)
        """
        self.camera = camera
        self.log_file = log_file
        self.interval = interval
        self.stop_flag = threading.Event()
        self.thread = None

    def start(self, exposure_start_time):
        """
        Start logging temperature in a background thread.

        Args:
            exposure_start_time: Time when exposure started (from time.time())
        """
        self.stop_flag.clear()
        self.thread = threading.Thread(
            target=self._log_loop,
            args=(exposure_start_time,),
            daemon=True  # Thread will exit when main program exits
        )
        self.thread.start()

    def stop(self):
        """Stop logging and wait for thread to finish."""
        self.stop_flag.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)  # Wait max 2 seconds

    def _log_loop(self, exposure_start_time):
        """
        Internal logging loop that runs in background thread.

        Args:
            exposure_start_time: Time when exposure started (from time.time())
        """
        try:
            with open(self.log_file, 'w') as f:
                # Write CSV header
                f.write("timestamp,elapsed_time_s,temperature_c,cooler_power_pct\n")

                while not self.stop_flag.is_set():
                    try:
                        # Get current time and calculate elapsed
                        current_time = time.time()
                        elapsed = current_time - exposure_start_time

                        # Read temperature and cooler power from camera
                        temp = self.camera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10.0
                        cooler = self.camera.get_control_value(asi.ASI_COOLER_POWER_PERC)[0]

                        # Write data point
                        timestamp = datetime.now().isoformat()
                        f.write(f"{timestamp},{elapsed:.3f},{temp:.2f},{cooler}\n")
                        f.flush()  # Ensure data written immediately

                    except Exception as e:
                        # Log errors but continue
                        f.write(f"# Error reading temperature: {e}\n")
                        f.flush()

                    # Sleep for interval or until stop flag
                    self.stop_flag.wait(self.interval)

        except Exception as e:
            print(f"Temperature logger error: {e}")

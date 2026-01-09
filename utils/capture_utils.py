"""Image capture utilities for ZWO ASI cameras."""

import zwoasi as asi
import time
import numpy as np
from datetime import datetime


def capture_with_timing(camera, initial_sleep=0.01, poll_interval=0.001):
    """
    Capture an image and measure actual exposure time separately from data transfer.

    This function measures the time between start_exposure() and when the camera
    reports ASI_EXP_SUCCESS status. This timing includes:

    1. Actual light collection (the exposure time you set)
    2. Sensor readout preparation (affected by BandWidth setting)

    The sensor readout preparation can add significant time (0.5-1.2s for full frame)
    depending on your BandWidth setting:
    - BandWidth=40: ~1.2s readout overhead (most stable)
    - BandWidth=100: ~0.6s readout overhead (faster but less stable)

    This overhead is NORMAL and doesn't affect image quality - the sensor stops
    collecting light after the configured exposure time. The extra time is just
    the camera preparing data for transfer.

    Args:
        camera: ZWO ASI camera object
        initial_sleep: Initial sleep after starting exposure (default: 0.01s)
        poll_interval: Polling interval for checking exposure status (default: 0.001s)

    Returns:
        tuple: (image_array, timing_dict) where timing_dict contains:
            - 'set_exposure_us': Configured exposure time in microseconds
            - 'set_exposure_s': Configured exposure time in seconds
            - 'exposure_plus_readout_s': Measured time until camera ready (includes readout)
            - 'transfer_time_s': Time to transfer data over USB
            - 'total_time_s': Total time (exposure + readout + transfer)
            - 'readout_time_s': Difference between set and measured (s) (readout time)
            - 'dropped_frames': Number of dropped frames detected
            - 'capture_start_time': datetime object of when exposure started
    """
    # Get configured exposure time
    set_exposure_us = camera.get_control_value(asi.ASI_EXPOSURE)[0]
    set_exposure_s = set_exposure_us / 1_000_000

    # Check for dropped frames before starting
    dropped_before = camera.get_dropped_frames()

    # Ensure camera is in clean state (stop any previous exposure)
    # This is safe to call even if no exposure is running
    try:
        camera.stop_exposure()
    except asi.ZWO_Error:
        pass  # Ignore error if no exposure was running

    # Start exposure and begin timing
    # Record both wall-clock time and high-res timestamp
    exposure_start = time.time()
    exposure_start_datetime = datetime.now()
    camera.start_exposure()
    last_temp_check = time.time()
    temp_log_interval = 1.0  # Log temperature every 1 second

    # Initial sleep to avoid busy-waiting immediately
    if initial_sleep:
        time.sleep(initial_sleep)

    # Poll until exposure completes (but before data transfer)
    while camera.get_exposure_status() == asi.ASI_EXP_WORKING:
        current_time = time.time()

        # Only check temperature periodically
        if current_time - last_temp_check >= temp_log_interval:
            temp = camera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10.0
            print(f"Temp: {temp:.1f}°C at {current_time - exposure_start:.1f}s")
            last_temp_check = current_time

        time.sleep(poll_interval)

    # Exposure just finished - record time before data transfer
    exposure_end = time.time()
    exposure_plus_readout_s = exposure_end - exposure_start

    # Check if exposure was successful
    status = camera.get_exposure_status()
    if status != asi.ASI_EXP_SUCCESS:
        raise asi.ZWO_CaptureError(f'Exposure failed with status {status}', status)

    # Now retrieve the data (USB transfer happens here)
    transfer_start = time.time()
    data = camera.get_data_after_exposure()
    transfer_end = time.time()
    transfer_time_s = transfer_end - transfer_start

    # Check for dropped frames after capture
    dropped_after = camera.get_dropped_frames()
    dropped_frames = dropped_after - dropped_before

    # Convert data to numpy array
    whbi = camera.get_roi_format()
    shape = [whbi[1], whbi[0]]  # height, width

    if whbi[3] == asi.ASI_IMG_RAW8 or whbi[3] == asi.ASI_IMG_Y8:
        img_array = np.frombuffer(data, dtype=np.uint8)
    elif whbi[3] == asi.ASI_IMG_RAW16:
        img_array = np.frombuffer(data, dtype=np.uint16)
    elif whbi[3] == asi.ASI_IMG_RGB24:
        img_array = np.frombuffer(data, dtype=np.uint8)
        shape.append(3)
    else:
        raise ValueError('Unsupported image type')

    img_array = img_array.reshape(shape)

    # Calculate timing metrics
    total_time_s = exposure_end - exposure_start + transfer_time_s
    readout_time_s = (exposure_plus_readout_s - set_exposure_s)

    timing = {
        'set_exposure_us': set_exposure_us,
        'set_exposure_s': set_exposure_s,
        'exposure_plus_readout_s': exposure_plus_readout_s,
        'transfer_time_s': transfer_time_s,
        'total_time_s': total_time_s,
        'readout_time_s': readout_time_s,
        'dropped_frames': dropped_frames,
        'capture_start_time': exposure_start_datetime
    }

    return img_array, timing


def capture_with_verification(camera, max_retries=2,
                             poll_interval=0.001, check_dropped_frames=True):
    """
    Capture an image with exposure time verification and dropped frame detection.

    This function verifies exposure timing consistency and detects dropped frames.
    The measured time includes both light collection and sensor readout (affected
    by BandWidth setting).

    Args:
        camera: ZWO ASI camera object
        max_retries: Maximum number of capture attempts (default: 2)
        poll_interval: Polling interval for checking exposure status (default: 0.001s)
        check_dropped_frames: Raise error if frames are dropped (default: True)

    Returns:
        tuple: (image_array, timing_dict) - see capture_with_timing() for timing_dict format
    """
    # Get expected exposure time
    expected_exposure_us = camera.get_control_value(asi.ASI_EXPOSURE)[0]
    expected_exposure_sec = expected_exposure_us / 1_000_000

    print(f"Expected exposure time: {expected_exposure_sec:.6f} seconds ({expected_exposure_us} μs)")

    img_array = None
    timing = None
    first_timing = None  # Store first attempt timing for consistency checking

    for attempt in range(1, max_retries + 1):
        print(f"\nCapture attempt {attempt}/{max_retries}...")

        try:
            # Capture with detailed timing
            img_array, timing = capture_with_timing(camera, poll_interval=poll_interval)

            # Store first timing for consistency comparison
            if first_timing is None:
                first_timing = timing['exposure_plus_readout_s']

            # Print detailed timing breakdown
            print(f"Measured time:       {timing['exposure_plus_readout_s']:.6f} seconds (includes readout)")
            print(f"USB transfer time:   {timing['transfer_time_s']:.6f} seconds")
            print(f"Total capture time:  {timing['total_time_s']:.6f} seconds")

            # Check for dropped frames
            if timing['dropped_frames'] > 0:
                print(f"⚠ WARNING: {timing['dropped_frames']} frame(s) dropped!")
                if check_dropped_frames:
                    if attempt < max_retries:
                        print("Retrying due to dropped frames...")
                        continue
                    else:
                        raise asi.ZWO_CaptureError(
                            f"Dropped {timing['dropped_frames']} frames",
                            asi.ASI_EXP_FAILED
                        )

            # Check timing consistency (detect real problems, not bandwidth variations)
            timing_diff = abs(timing['exposure_plus_readout_s'] - first_timing)
            if attempt > 1 and timing_diff > 0.1:  # More than 100ms variation between attempts
                print(f"⚠ WARNING: Timing inconsistent between attempts ({timing_diff:.3f}s difference)")
                if attempt < max_retries:
                    print("Retrying due to timing inconsistency...")
                    continue

            # Capture successful
            print("✓ Capture successful!")
            break

        except asi.ZWO_CaptureError as e:
            print(f"✗ Capture failed: {e}")
            if attempt < max_retries:
                print("Retrying...")
                time.sleep(0.1)  # Brief delay before retry
            else:
                raise

    return img_array, timing

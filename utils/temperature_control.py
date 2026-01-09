"""Temperature control module for ZWO ASI cameras."""

import zwoasi as asi
import time


def stabilize_temperature(camera, target_temp, use_cooler=True,
                         temp_tolerance=0.5, idle_time=300, check_duration=60):
    """
    Enable cooler and wait for temperature to stabilize.

    Args:
        camera: ZWO ASI camera object
        target_temp: Target temperature in °C
        use_cooler: Whether to enable cooling (default: True)
        temp_tolerance: Acceptable temperature deviation in °C (default: 0.5)
        idle_time: Seconds to wait after reaching target before stability check (default: 300)
        check_duration: Seconds to verify stability (default: 60)

    Returns:
        bool: True if temperature stabilized successfully, False if cooler disabled

    Raises:
        SystemExit: If temperature fails to stabilize
    """
    if not use_cooler:
        print("Cooler disabled, using ambient temperature")
        return False

    print(f"Enabling cooler, target temperature: {target_temp}°C")
    camera.set_control_value(asi.ASI_TARGET_TEMP, int(target_temp * 10))
    camera.set_control_value(asi.ASI_COOLER_ON, 1)

    # Wait for temperature to stabilize
    print("Waiting for temperature to stabilize...")

    # Step 1: Wait for temperature to reach target range
    print("Step 1: Waiting for temperature to reach target range...")
    while True:
        current_temp = camera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10.0
        cooler_power = camera.get_control_value(asi.ASI_COOLER_POWER_PERC)[0]
        print(f"  Current: {current_temp:.1f}°C, Target: {target_temp}°C, Cooler power: {cooler_power}%")

        if abs(current_temp - target_temp) <= temp_tolerance:
            print(f"Temperature reached target range!")
            break

        time.sleep(10)

    # Step 2: Idle time - wait for thermal stabilization
    print(f"Step 2: Idling at temperature for {idle_time} seconds...")
    start_idle = time.time()
    while time.time() - start_idle < idle_time:
        current_temp = camera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10.0
        cooler_power = camera.get_control_value(asi.ASI_COOLER_POWER_PERC)[0]
        elapsed = int(time.time() - start_idle)
        print(f"  [{elapsed}s/{idle_time}s] Current: {current_temp:.1f}°C, Target: {target_temp}°C, Cooler power: {cooler_power}%")
        time.sleep(10)

    # Step 3: Verify stability over CHECK_DURATION
    print(f"Step 3: Verifying stability over {check_duration} seconds...")
    start_check = time.time()
    all_stable = True

    while time.time() - start_check < check_duration:
        time.sleep(5)
        temp_check = camera.get_control_value(asi.ASI_TEMPERATURE)[0] / 10.0
        cooler_power_check = camera.get_control_value(asi.ASI_COOLER_POWER_PERC)[0]
        elapsed = int(time.time() - start_check)
        print(f"  [{elapsed}s/{check_duration}s] Current: {temp_check:.1f}°C, Target: {target_temp}°C, Cooler power: {cooler_power_check}%")

        if abs(temp_check - target_temp) > temp_tolerance:
            print("Temperature drifted outside tolerance!")
            all_stable = False
            break

    if all_stable:
        print("Temperature stabilized and verified!")
        return True
    else:
        # Turn off cooler before exiting
        camera.set_control_value(asi.ASI_COOLER_ON, 0)
        print("ERROR: Temperature not stable. Aborting capture.")
        exit(1)


def disable_cooler(camera):
    """Turn off the camera cooler."""
    print("Turning off cooler...")
    camera.set_control_value(asi.ASI_COOLER_ON, 0)

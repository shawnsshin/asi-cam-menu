"""Live preview for checking focus, object placement, and framing."""

import time
import numpy as np
import zwoasi as asi


def live_preview(camera, get_temperature_fn):
    """Run live camera preview with auto or manual exposure control.

    Args:
        camera: Initialized zwoasi.Camera instance.
        get_temperature_fn: Callable returning temperature in °C or None.
    """
    try:
        import cv2
    except ImportError:
        print("\nOpenCV is required for live preview.")
        print("Install with: pip install opencv-python")
        return

    print("\n" + "=" * 70)
    print("LIVE PREVIEW")
    print("=" * 70)
    print("\nLive camera feed for checking object placement, focus, and framing.")
    print("(Uses RAW8 mode for faster frame rate during preview)")
    print("\nSelect exposure mode:")
    print("  1. Auto Exposure (camera adjusts automatically)")
    print("  2. Manual Exposure (adjust in real time with keyboard)")
    print("  0. Back to Main Menu")

    choice = input("\nSelect mode: ").strip()
    if choice not in ("1", "2"):
        return

    auto_mode = (choice == "1")

    # Save original settings to restore after preview
    orig_exposure, orig_exp_auto = camera.get_control_value(asi.ASI_EXPOSURE)
    orig_image_type = camera.get_roi_format()[3]

    try:
        # Switch to RAW8 for faster preview
        camera.set_image_type(asi.ASI_IMG_RAW8)

        # Cap initial exposure for responsiveness
        exposure_us = orig_exposure
        if exposure_us > 5_000_000:
            print(f"\nCurrent exposure ({exposure_us / 1e6:.1f}s) is long for live preview.")
            print("Starting with 1s. Adjust with +/- keys.")
            exposure_us = 1_000_000

        target_brightness = 120

        if auto_mode:
            camera.set_control_value(asi.ASI_EXPOSURE, exposure_us, auto=True)
            camera.set_control_value(asi.ASI_AUTO_MAX_EXP, 5_000_000)
            camera.set_control_value(asi.ASI_AUTO_MAX_GAIN, 300)
            camera.set_control_value(asi.ASI_AUTO_TARGET_BRIGHTNESS, target_brightness)
        else:
            camera.set_control_value(asi.ASI_EXPOSURE, exposure_us, auto=False)

        # Start video capture
        camera.start_video_capture()

        window_name = 'ASI Camera - Live Preview'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 800, 800)

        print("\nLive preview started!")
        print("\u2500" * 40)
        print("Controls:")
        print("  a         Toggle auto/manual exposure")
        print("  +/= , -   Exposure up/down (2x) [manual]")
        print("            Target brightness +/- 10 [auto]")
        print("  q / ESC   Quit preview")
        print("\u2500" * 40)

        frame_count = 0
        fps_timer = time.time()
        fps = 0.0
        last_info_time = 0
        display_exp_us = exposure_us
        display_temp = get_temperature_fn()
        last_display = None

        while True:
            # Short timeout so we can check keypresses frequently.
            # Without this, long exposures block the entire loop and
            # keypresses (like 'q' to quit) are never processed.
            got_frame = False
            try:
                frame = camera.capture_video_frame(timeout=200)
                got_frame = True
                # Drain any buffered frames so we always show the latest one.
                # Video mode accumulates frames in an internal buffer; if we
                # process slower than the camera produces, we'd show stale
                # frames with increasing latency.
                while True:
                    try:
                        frame = camera.capture_video_frame(timeout=10)
                    except Exception:
                        break
            except Exception:
                pass

            if got_frame:
                # Resize first for performance
                h, w = frame.shape[:2]
                if max(h, w) > 800:
                    scale = 800.0 / max(h, w)
                    frame = cv2.resize(frame, (int(w * scale), int(h * scale)),
                                       interpolation=cv2.INTER_NEAREST)

                # Auto-stretch to 8-bit for display
                display = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

                # Update FPS counter
                frame_count += 1
                now = time.time()
                if now - fps_timer >= 1.0:
                    fps = frame_count / (now - fps_timer)
                    frame_count = 0
                    fps_timer = now

                # Refresh camera info periodically
                if now - last_info_time >= 2.0:
                    display_exp_us = camera.get_control_value(asi.ASI_EXPOSURE)[0]
                    display_temp = get_temperature_fn()
                    last_info_time = now

                # Format exposure for overlay
                if display_exp_us >= 1_000_000:
                    exp_str = f"{display_exp_us / 1e6:.2f}s"
                elif display_exp_us >= 1000:
                    exp_str = f"{display_exp_us / 1000:.1f}ms"
                else:
                    exp_str = f"{display_exp_us}us"

                mode_str = "AUTO" if auto_mode else "MANUAL"
                temp_str = f"{display_temp:.1f}C" if display_temp is not None else "N/A"
                line1 = f"{mode_str} | Exp: {exp_str} | {temp_str} | {fps:.1f} FPS"
                if auto_mode:
                    line2 = f"[a] mode  [+/-] brightness ({target_brightness})  [q] quit"
                else:
                    line2 = "[a] mode  [+/-] exposure  [q] quit"

                # Draw overlay (white text on grayscale)
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.5
                thick = 1
                y_pos = 20
                for text in (line1, line2):
                    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thick)
                    cv2.rectangle(display, (4, y_pos - th - 4), (8 + tw, y_pos + 4), 0, -1)
                    cv2.putText(display, text, (6, y_pos), font, font_scale,
                                255, thick, cv2.LINE_AA)
                    y_pos += th + 12

                last_display = display

            # Always show something (even if no new frame this iteration)
            if last_display is not None:
                cv2.imshow(window_name, last_display)

            # Check for keypresses every iteration (not blocked by frame capture)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q') or key == 27:  # q or ESC
                break

            # Check if window was closed via X button
            try:
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break

            if key == ord('a'):
                auto_mode = not auto_mode
                cur_exp = camera.get_control_value(asi.ASI_EXPOSURE)[0]
                if auto_mode:
                    camera.set_control_value(asi.ASI_EXPOSURE, cur_exp, auto=True)
                    print("  -> AUTO exposure")
                else:
                    camera.set_control_value(asi.ASI_EXPOSURE, cur_exp, auto=False)
                    print(f"  -> MANUAL exposure (Exp: {cur_exp}us)")

            elif key in (ord('+'), ord('=')):
                if auto_mode:
                    target_brightness = min(target_brightness + 10, 255)
                    camera.set_control_value(asi.ASI_AUTO_TARGET_BRIGHTNESS, target_brightness)
                else:
                    cur_exp = camera.get_control_value(asi.ASI_EXPOSURE)[0]
                    new_exp = min(cur_exp * 2, 30_000_000)
                    camera.set_control_value(asi.ASI_EXPOSURE, int(new_exp))
                    display_exp_us = int(new_exp)

            elif key == ord('-'):
                if auto_mode:
                    target_brightness = max(target_brightness - 10, 10)
                    camera.set_control_value(asi.ASI_AUTO_TARGET_BRIGHTNESS, target_brightness)
                else:
                    cur_exp = camera.get_control_value(asi.ASI_EXPOSURE)[0]
                    new_exp = max(cur_exp // 2, 100)
                    camera.set_control_value(asi.ASI_EXPOSURE, int(new_exp))
                    display_exp_us = int(new_exp)

    finally:
        try:
            camera.stop_video_capture()
        except Exception:
            pass
        cv2.destroyAllWindows()
        cv2.waitKey(1)  # Flush remaining GUI events so window actually closes

        # Restore original settings
        camera.set_image_type(orig_image_type)
        camera.set_control_value(asi.ASI_EXPOSURE, orig_exposure, auto=bool(orig_exp_auto))

        print("\nLive preview ended. Original settings restored.")

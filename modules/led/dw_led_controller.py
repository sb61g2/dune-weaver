"""
Dune Weaver LED Controller - Embedded NeoPixel LED controller for Raspberry Pi
Provides direct GPIO control of WS2812B LED strips with beautiful effects
"""
import threading
import time
import logging
from typing import Optional, Dict, List, Tuple
from .dw_leds.segment import Segment
from .dw_leds.effects.basic_effects import get_effect, get_all_effects, FRAMETIME
from .dw_leds.utils.palettes import get_palette_name, PALETTE_NAMES
from .dw_leds.utils.colors import rgb_to_color

logger = logging.getLogger(__name__)


class _DualWS2811RGBCCTProxy:
    """
    Proxy for dual WS2811 RGBCCT strips where each logical segment uses TWO physical pixels:
    - Physical pixel 2*i: RGB (3 bytes)
    - Physical pixel 2*i+1: CCT white channels (2-3 bytes for WW/CW)

    This allows the effect engine to work with N logical RGB pixels while the strip
    actually has 2N physical pixels.
    """

    def __init__(self, physical_pixels, logical_count: int, pixel_order: str):
        """
        Args:
            physical_pixels: The actual NeoPixel object (with 2*logical_count pixels)
            logical_count: Number of logical RGB segments
            pixel_order: RGB channel order (GRB, RGB, BRG, etc.)
        """
        self._physical = physical_pixels
        self._logical_count = logical_count
        self.pixel_order = pixel_order

        # Global white channel values (applied to all CCT pixels)
        self._ww = 0  # Warm white (0-255)
        self._cw = 0  # Cool white (0-255)

        # Separate brightness controls (0.0 - 1.0)
        self._rgb_brightness = 1.0
        self._white_brightness = 1.0

        # Keep physical brightness at 1.0 to allow software control
        self._physical.brightness = 1.0

    def __len__(self):
        """Return logical count (not physical)"""
        return self._logical_count

    def __getitem__(self, index):
        """Get logical RGB pixel at index"""
        if index < 0 or index >= self._logical_count:
            return (0, 0, 0)
        # Read from physical pixel 2*index (RGB chip)
        return self._physical[2 * index]

    def __setitem__(self, index, value):
        """
        Set logical pixel at index.
        Writes RGB to physical 2*index and WW/CW to physical 2*index+1
        """
        if index < 0 or index >= self._logical_count:
            return

        # Apply RGB brightness scaling
        if isinstance(value, tuple) and len(value) >= 3:
            r, g, b = value[0], value[1], value[2]
            r = int(r * self._rgb_brightness)
            g = int(g * self._rgb_brightness)
            b = int(b * self._rgb_brightness)
            scaled_value = (r, g, b)
        else:
            scaled_value = value

        # Write RGB to first chip (physical index 2*i)
        self._physical[2 * index] = scaled_value

        # Apply white brightness scaling and write WW/CW to second chip (physical index 2*i+1)
        # Second chip uses 3 bytes but we only need 2 for WW/CW
        # Pack as (CW, WW, 0) - channels are swapped on hardware
        ww_scaled = int(self._ww * self._white_brightness)
        cw_scaled = int(self._cw * self._white_brightness)
        self._physical[2 * index + 1] = (cw_scaled, ww_scaled, 0)

    def show(self):
        """Update all physical pixels"""
        self._physical.show()

    def fill(self, color):
        """Fill all logical pixels with color"""
        for i in range(self._logical_count):
            self[i] = color

    def deinit(self):
        """Deinitialize the physical NeoPixel object"""
        if hasattr(self._physical, 'deinit'):
            self._physical.deinit()

    def stop(self):
        """Stop/deinitialize (alias for compatibility)"""
        self.deinit()

    def set_cct(self, ww: int = 0, cw: int = 0):
        """
        Set global white channel values (0-255 each).
        These are applied to all CCT pixels immediately.
        """
        self._ww = max(0, min(255, ww))
        self._cw = max(0, min(255, cw))
        # Update all white channel pixels immediately
        self._update_all_white_channels()

    def set_white_temperature(self, kelvin: int = 4000, level: int = 255):
        """
        Set white light by color temperature and brightness.

        Args:
            kelvin: Color temperature (2700-6500K)
            level: Overall white brightness (0-255)
        """
        # Map kelvin to WW/CW balance
        if kelvin <= 2700:
            ww_ratio = 1.0
        elif kelvin >= 6500:
            ww_ratio = 0.0
        else:
            # Linear interpolation between 2700K (all WW) and 6500K (all CW)
            ww_ratio = 1.0 - (kelvin - 2700) / (6500 - 2700)

        self._ww = int(level * ww_ratio)
        self._cw = int(level * (1.0 - ww_ratio))

        # Update all white channel pixels immediately
        self._update_all_white_channels()

    def _update_all_white_channels(self):
        """Update all WW/CW pixels (odd-numbered physical pixels) with current white values"""
        # Apply white brightness scaling
        ww_scaled = int(self._ww * self._white_brightness)
        cw_scaled = int(self._cw * self._white_brightness)

        for i in range(self._logical_count):
            # Write WW/CW to second chip (physical index 2*i+1)
            # Pack as (CW, WW, 0) - channels are swapped on hardware
            self._physical[2 * i + 1] = (cw_scaled, ww_scaled, 0)

    @property
    def brightness(self):
        """Get RGB brightness (for backward compatibility)"""
        return self._rgb_brightness

    @brightness.setter
    def brightness(self, value):
        """Set RGB brightness (for backward compatibility)"""
        self.set_rgb_brightness(value)

    def set_rgb_brightness(self, value: float):
        """
        Set RGB brightness independently
        Args:
            value: Brightness 0.0-1.0
        """
        self._rgb_brightness = max(0.0, min(1.0, value))
        # Trigger update by re-rendering current frame
        # (effect loop will call show() which updates pixels)

    def set_white_brightness(self, value: float):
        """
        Set white channel brightness independently
        Args:
            value: Brightness 0.0-1.0
        """
        self._white_brightness = max(0.0, min(1.0, value))
        # Update white channels immediately
        self._update_all_white_channels()
        self._physical.show()


class DWLEDController:
    """Dune Weaver LED Controller for NeoPixel LED strips"""

    def __init__(self, num_leds: int = 60, gpio_pin: int = 18, brightness: float = 0.35,
                 pixel_order: str = "GRB", speed: int = 128, intensity: int = 128,
                 dual_ws2811_rgbcct: bool = False):
        """
        Initialize Dune Weaver LED controller

        Args:
            num_leds: Number of logical LED segments (for dual WS2811, actual physical count is 2x)
            gpio_pin: GPIO pin number (BCM numbering: 12, 13, 18, or 19)
            brightness: Global brightness (0.0 - 1.0)
            pixel_order: Pixel color order (RGB, GRB, BRG for 3-byte)
            speed: Effect speed 0-255 (default: 128)
            intensity: Effect intensity 0-255 (default: 128)
            dual_ws2811_rgbcct: Enable dual WS2811 mode for RGBCCT strips
                When True: each logical segment uses 2 physical pixels (RGB + CCT)
        """
        self.num_leds = num_leds
        self.gpio_pin = gpio_pin
        self.brightness = brightness
        self.pixel_order = pixel_order
        self._dual_ws2811_rgbcct = dual_ws2811_rgbcct

        # State
        self._powered_on = False
        self._current_effect_id = 8
        self._current_palette_id = 0
        self._speed = speed
        self._intensity = intensity
        self._color1 = (255, 0, 0)  # Red (primary)
        self._color2 = (0, 0, 0)  # Black (background/off)
        self._color3 = (0, 0, 255)  # Blue (tertiary)

        # Threading
        self._pixels = None
        self._segment = None
        self._effect_thread = None
        self._stop_thread = threading.Event()
        self._lock = threading.Lock()
        self._initialized = False
        self._init_error = None  # Store initialization error message

    def _get_bytes_per_pixel(self, pixel_order: str) -> int:
        """
        Determine bytes per pixel based on pixel order string.

        Args:
            pixel_order: Pixel order string (e.g., GRB, GRBW, GRBWW)

        Returns:
            Number of bytes per pixel (3, 4, or 5)
        """
        # Count unique color channels in the pixel order string
        # Standard channels: R, G, B, W
        # For RGBCCT (dual white): second W represents cool white
        order_upper = pixel_order.upper()

        # RGBCCT strips with dual WS2811 use 5 bytes (R, G, B, WW, CW)
        # We detect this by looking for "WW" in the pixel order or length >= 5
        if "WW" in order_upper or len(order_upper) >= 5:
            return 5
        elif "W" in order_upper or len(order_upper) == 4:
            return 4
        else:
            return 3

    def _initialize_hardware(self):
        """Lazy initialization of NeoPixel hardware"""
        if self._initialized:
            return True

        try:
            import board
            import neopixel

            # Map GPIO pin numbers to board pins
            pin_map = {
                12: board.D12,
                13: board.D13,
                18: board.D18,
                19: board.D19
            }

            if self.gpio_pin not in pin_map:
                error_msg = f"Invalid GPIO pin {self.gpio_pin}. Must be 12, 13, 18, or 19 (PWM-capable pins)"
                self._init_error = error_msg
                logger.error(error_msg)
                return False

            board_pin = pin_map[self.gpio_pin]

            # Initialize NeoPixel strip
            # For dual WS2811 RGBCCT strips: create 2x physical pixels and wrap in proxy

            # Determine physical pixel count
            physical_leds = self.num_leds * 2 if self._dual_ws2811_rgbcct else self.num_leds

            # Use only 3-byte pixel orders (RGB, GRB, BRG)
            pixel_order_to_use = self.pixel_order[:3] if len(self.pixel_order) > 3 else self.pixel_order

            if self._dual_ws2811_rgbcct:
                logger.info(f"Dual WS2811 RGBCCT mode: {self.num_leds} logical segments → {physical_leds} physical pixels, pixel order '{pixel_order_to_use}'")
            else:
                logger.info(f"Standard RGB mode: {physical_leds} pixels, pixel order '{pixel_order_to_use}'")

            # Create physical NeoPixel object
            physical_pixels = neopixel.NeoPixel(
                board_pin,
                physical_leds,
                brightness=self.brightness,
                auto_write=False,
                pixel_order=pixel_order_to_use
            )

            # Wrap in proxy if dual WS2811 mode
            if self._dual_ws2811_rgbcct:
                self._pixels = _DualWS2811RGBCCTProxy(physical_pixels, self.num_leds, pixel_order_to_use)
            else:
                self._pixels = physical_pixels

            # Create segment for the entire strip
            self._segment = Segment(self._pixels, 0, self.num_leds)
            self._segment.speed = self._speed
            self._segment.intensity = self._intensity
            self._segment.palette_id = self._current_palette_id

            # Set colors
            self._segment.colors[0] = rgb_to_color(*self._color1)
            self._segment.colors[1] = rgb_to_color(*self._color2)
            self._segment.colors[2] = rgb_to_color(*self._color3)

            self._initialized = True
            logger.info(f"DW LEDs initialized: {self.num_leds} LEDs on GPIO {self.gpio_pin}")
            return True

        except ImportError as e:
            error_msg = f"Failed to import NeoPixel libraries: {e}. Make sure adafruit-circuitpython-neopixel and Adafruit-Blinka are installed."
            self._init_error = error_msg
            logger.error(error_msg)
            return False
        except Exception as e:
            error_msg = f"Failed to initialize NeoPixel hardware: {e}"
            self._init_error = error_msg
            logger.error(error_msg)
            return False

    def _effect_loop(self):
        """Background thread that runs the current effect"""
        while not self._stop_thread.is_set():
            try:
                with self._lock:
                    if self._pixels and self._segment and self._powered_on:
                        # Get current effect function (allows dynamic effect switching)
                        effect_func = get_effect(self._current_effect_id)

                        # Run effect and get delay
                        delay_ms = effect_func(self._segment)

                        # Update pixels
                        self._pixels.show()

                        # Increment call counter
                        self._segment.call += 1
                    else:
                        delay_ms = 100  # Idle delay when off

                # Sleep for the effect's requested delay
                time.sleep(delay_ms / 1000.0)

            except Exception as e:
                logger.error(f"Error in effect loop: {e}")
                time.sleep(0.1)

    def set_power(self, state: int) -> Dict:
        """
        Set power state

        Args:
            state: 0=Off, 1=On, 2=Toggle

        Returns:
            Dict with status
        """
        if not self._initialize_hardware():
            return {
                "connected": False,
                "error": self._init_error or "Failed to initialize LED hardware"
            }

        with self._lock:
            if state == 2:  # Toggle
                self._powered_on = not self._powered_on
            else:
                self._powered_on = bool(state)

            # Turn off all pixels immediately when powering off
            if not self._powered_on and self._pixels:
                self._pixels.fill((0, 0, 0))
                self._pixels.show()

            # Start effect thread if not running
            if self._powered_on and (self._effect_thread is None or not self._effect_thread.is_alive()):
                self._stop_thread.clear()
                self._effect_thread = threading.Thread(target=self._effect_loop, daemon=True)
                self._effect_thread.start()

        return {
            "connected": True,
            "power_on": self._powered_on,
            "message": f"Power {'on' if self._powered_on else 'off'}"
        }

    def set_brightness(self, value: int) -> Dict:
        """
        Set RGB brightness (for backward compatibility)

        Args:
            value: Brightness 0-100

        Returns:
            Dict with status
        """
        return self.set_rgb_brightness(value)

    def set_rgb_brightness(self, value: int) -> Dict:
        """
        Set RGB brightness independently

        Args:
            value: Brightness 0-100

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        brightness = max(0.0, min(1.0, value / 100.0))

        with self._lock:
            self.brightness = brightness
            if self._pixels:
                if self._dual_ws2811_rgbcct and hasattr(self._pixels, 'set_rgb_brightness'):
                    # Use separate RGB brightness for dual WS2811 mode
                    self._pixels.set_rgb_brightness(brightness)
                else:
                    # Standard mode: set global brightness
                    self._pixels.brightness = brightness

        return {
            "connected": True,
            "brightness": int(brightness * 100),
            "message": "RGB brightness updated"
        }

    def set_white_brightness_level(self, value: int) -> Dict:
        """
        Set white channel brightness independently (RGBCCT mode only)

        Args:
            value: Brightness 0-100

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        if not self._dual_ws2811_rgbcct:
            return {"connected": False, "error": "White brightness control requires RGBCCT mode"}

        brightness = max(0.0, min(1.0, value / 100.0))

        with self._lock:
            if self._pixels and hasattr(self._pixels, 'set_white_brightness'):
                self._pixels.set_white_brightness(brightness)

        return {
            "connected": True,
            "white_brightness": int(brightness * 100),
            "message": "White brightness updated"
        }

    def set_color(self, r: int, g: int, b: int) -> Dict:
        """
        Set solid color (sets effect to Static and color1)

        Args:
            r, g, b: RGB values 0-255

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        with self._lock:
            self._color1 = (r, g, b)
            if self._segment:
                self._segment.colors[0] = rgb_to_color(r, g, b)
                # Switch to static effect
                self._current_effect_id = 0
                self._segment.reset()

            # Auto power on when setting color
            if not self._powered_on:
                self._powered_on = True

            # Ensure effect thread is running
            if self._effect_thread is None or not self._effect_thread.is_alive():
                self._stop_thread.clear()
                self._effect_thread = threading.Thread(target=self._effect_loop, daemon=True)
                self._effect_thread.start()

        return {
            "connected": True,
            "color": [r, g, b],
            "power_on": self._powered_on,
            "message": "Color set"
        }

    def set_colors(self, color1: Optional[Tuple[int, int, int]] = None,
                   color2: Optional[Tuple[int, int, int]] = None,
                   color3: Optional[Tuple[int, int, int]] = None) -> Dict:
        """
        Set effect colors (does not change effect or auto-power on)

        Args:
            color1: Primary color RGB tuple (0-255)
            color2: Secondary/background color RGB tuple (0-255)
            color3: Tertiary color RGB tuple (0-255)

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        colors_set = []
        with self._lock:
            if color1 is not None:
                self._color1 = color1
                if self._segment:
                    self._segment.colors[0] = rgb_to_color(*color1)
                colors_set.append(f"color1={color1}")

            if color2 is not None:
                self._color2 = color2
                if self._segment:
                    self._segment.colors[1] = rgb_to_color(*color2)
                colors_set.append(f"color2={color2}")

            if color3 is not None:
                self._color3 = color3
                if self._segment:
                    self._segment.colors[2] = rgb_to_color(*color3)
                colors_set.append(f"color3={color3}")

            # Reset effect to apply new colors
            if self._segment and colors_set:
                self._segment.reset()

        return {
            "connected": True,
            "colors": {
                "color1": self._color1,
                "color2": self._color2,
                "color3": self._color3
            },
            "message": f"Colors updated: {', '.join(colors_set)}"
        }

    def set_effect(self, effect_id: int, speed: Optional[int] = None,
                   intensity: Optional[int] = None) -> Dict:
        """
        Set active effect

        Args:
            effect_id: Effect ID (0-15)
            speed: Optional speed override (0-255)
            intensity: Optional intensity override (0-255)

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        # Validate effect ID
        effects = get_all_effects()
        if not any(eid == effect_id for eid, _ in effects):
            return {
                "connected": False,
                "message": f"Invalid effect ID: {effect_id}"
            }

        with self._lock:
            self._current_effect_id = effect_id

            if speed is not None:
                self._speed = max(0, min(255, speed))
                if self._segment:
                    self._segment.speed = self._speed

            if intensity is not None:
                self._intensity = max(0, min(255, intensity))
                if self._segment:
                    self._segment.intensity = self._intensity

            # Reset effect state
            if self._segment:
                self._segment.reset()

            # Auto power on when setting effect
            if not self._powered_on:
                self._powered_on = True

            # Ensure effect thread is running
            if self._effect_thread is None or not self._effect_thread.is_alive():
                self._stop_thread.clear()
                self._effect_thread = threading.Thread(target=self._effect_loop, daemon=True)
                self._effect_thread.start()

        effect_name = next(name for eid, name in effects if eid == effect_id)
        return {
            "connected": True,
            "effect_id": effect_id,
            "effect_name": effect_name,
            "power_on": self._powered_on,
            "message": f"Effect set to {effect_name}"
        }

    def set_palette(self, palette_id: int) -> Dict:
        """
        Set color palette

        Args:
            palette_id: Palette ID (0-58)

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        if palette_id < 0 or palette_id >= len(PALETTE_NAMES):
            return {
                "connected": False,
                "message": f"Invalid palette ID: {palette_id}"
            }

        with self._lock:
            self._current_palette_id = palette_id
            if self._segment:
                self._segment.palette_id = palette_id

            # Auto power on when setting palette
            if not self._powered_on:
                self._powered_on = True

            # Ensure effect thread is running
            if self._effect_thread is None or not self._effect_thread.is_alive():
                self._stop_thread.clear()
                self._effect_thread = threading.Thread(target=self._effect_loop, daemon=True)
                self._effect_thread.start()

        palette_name = get_palette_name(palette_id)
        return {
            "connected": True,
            "palette_id": palette_id,
            "palette_name": palette_name,
            "power_on": self._powered_on,
            "message": f"Palette set to {palette_name}"
        }

    def set_speed(self, speed: int) -> Dict:
        """Set effect speed (0-255)"""
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        speed = max(0, min(255, speed))

        with self._lock:
            self._speed = speed
            if self._segment:
                self._segment.speed = speed
                # Reset effect state so speed change takes effect immediately
                self._segment.reset()

        return {
            "connected": True,
            "speed": speed,
            "message": "Speed updated"
        }

    def set_intensity(self, intensity: int) -> Dict:
        """Set effect intensity (0-255)"""
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        intensity = max(0, min(255, intensity))

        with self._lock:
            self._intensity = intensity
            if self._segment:
                self._segment.intensity = intensity
                # Reset effect state so intensity change takes effect immediately
                self._segment.reset()

        return {
            "connected": True,
            "intensity": intensity,
            "message": "Intensity updated"
        }

    def set_color_temperature(self, kelvin: int, level: int = 100) -> Dict:
        """
        Set white color temperature (RGBCCT dual WS2811 mode only)

        Args:
            kelvin: Color temperature in Kelvin (2700-6500)
            level: White brightness level 0-100

        Returns:
            Dict with status
        """
        if not self._initialized:
            if not self._initialize_hardware():
                return {"connected": False, "error": self._init_error or "Hardware not initialized"}

        if not self._dual_ws2811_rgbcct:
            return {
                "connected": True,
                "error": "Color temperature control requires Dual WS2811 RGBCCT mode"
            }

        # Clamp values
        kelvin = max(2700, min(6500, kelvin))
        level = max(0, min(100, level))

        # Convert level 0-100 to 0-255
        level_255 = int((level / 100.0) * 255)

        with self._lock:
            if isinstance(self._pixels, _DualWS2811RGBCCTProxy):
                self._pixels.set_white_temperature(kelvin, level_255)
                # Update all pixels to apply new white temperature
                if self._powered_on:
                    self._pixels.show()

        return {
            "connected": True,
            "color_temperature": kelvin,
            "white_level": level,
            "message": f"Color temperature set to {kelvin}K at {level}% brightness"
        }

    def set_white_mode(self, white_mode: bool, kelvin: int = 4000, level: int = 50) -> Dict:
        """
        Legacy function for backward compatibility - just sets color temperature

        Args:
            white_mode: Ignored (kept for API compatibility)
            kelvin: Color temperature in Kelvin (2700-6500)
            level: White brightness level 0-100

        Returns:
            Dict with status
        """
        # Simply delegate to set_color_temperature
        return self.set_color_temperature(kelvin, level)

    def get_effects(self) -> List[Tuple[int, str]]:
        """Get list of all available effects"""
        return get_all_effects()

    def get_palettes(self) -> List[Tuple[int, str]]:
        """Get list of all available palettes"""
        return [(i, name) for i, name in enumerate(PALETTE_NAMES)]

    def check_status(self) -> Dict:
        """Get current controller status"""
        # Attempt initialization if not already initialized
        if not self._initialized:
            self._initialize_hardware()

        # Get color slots from segment if available
        colors = []
        if self._segment and hasattr(self._segment, 'colors'):
            for color_int in self._segment.colors[:3]:  # Get up to 3 colors
                # Convert integer color to hex string
                r = (color_int >> 16) & 0xFF
                g = (color_int >> 8) & 0xFF
                b = color_int & 0xFF
                colors.append(f"#{r:02x}{g:02x}{b:02x}")
        else:
            colors = ["#ff0000", "#000000", "#0000ff"]  # Defaults

        status = {
            "connected": self._initialized,
            "power_on": self._powered_on,
            "num_leds": self.num_leds,
            "gpio_pin": self.gpio_pin,
            "brightness": int(self.brightness * 100),
            "current_effect": self._current_effect_id,
            "current_palette": self._current_palette_id,
            "speed": self._speed,
            "intensity": self._intensity,
            "colors": colors,
            "effect_running": self._effect_thread is not None and self._effect_thread.is_alive()
        }

        # Include error message if not initialized
        if not self._initialized and self._init_error:
            status["error"] = self._init_error

        return status

    def stop(self):
        """Stop the effect loop and cleanup"""
        self._stop_thread.set()
        if self._effect_thread and self._effect_thread.is_alive():
            self._effect_thread.join(timeout=1.0)

        with self._lock:
            if self._pixels:
                self._pixels.fill((0, 0, 0))
                self._pixels.show()
                self._pixels.deinit()
            self._pixels = None
            self._segment = None
            self._initialized = False


# Helper functions for pattern manager integration
def effect_loading(controller: DWLEDController) -> bool:
    """Show loading effect (Rainbow Cycle)"""
    try:
        controller.set_power(1)
        controller.set_effect(8, speed=100)  # Rainbow Cycle
        return True
    except Exception as e:
        logger.error(f"Error setting loading effect: {e}")
        return False


def effect_idle(controller: DWLEDController, effect_settings: Optional[dict] = None) -> bool:
    """Show idle effect with full settings"""
    try:
        if effect_settings and isinstance(effect_settings, dict):
            # New format: full settings dict
            controller.set_power(1)

            # Set effect
            effect_id = effect_settings.get("effect_id", 0)
            palette_id = effect_settings.get("palette_id", 0)
            speed = effect_settings.get("speed", 128)
            intensity = effect_settings.get("intensity", 128)

            controller.set_effect(effect_id, speed=speed, intensity=intensity)
            controller.set_palette(palette_id)

            # Set colors if provided
            color1 = effect_settings.get("color1")
            if color1:
                # Convert hex to RGB
                r1 = int(color1[1:3], 16)
                g1 = int(color1[3:5], 16)
                b1 = int(color1[5:7], 16)

                color2 = effect_settings.get("color2", "#000000")
                r2 = int(color2[1:3], 16)
                g2 = int(color2[3:5], 16)
                b2 = int(color2[5:7], 16)

                color3 = effect_settings.get("color3", "#0000ff")
                r3 = int(color3[1:3], 16)
                g3 = int(color3[3:5], 16)
                b3 = int(color3[5:7], 16)

                controller.set_colors(
                    color1=(r1, g1, b1),
                    color2=(r2, g2, b2),
                    color3=(r3, g3, b3)
                )

            return True

        # Default: do nothing (keep current LED state)
        return True
    except Exception as e:
        logger.error(f"Error setting idle effect: {e}")
        return False


def effect_connected(controller: DWLEDController) -> bool:
    """Show connected effect (green flash)"""
    try:
        controller.set_power(1)
        controller.set_color(0, 255, 0)  # Green
        controller.set_effect(1, speed=200, intensity=128)  # Blink effect
        time.sleep(1.0)
        return True
    except Exception as e:
        logger.error(f"Error setting connected effect: {e}")
        return False


def effect_playing(controller: DWLEDController, effect_settings: Optional[dict] = None) -> bool:
    """Show playing effect with full settings"""
    try:
        if effect_settings and isinstance(effect_settings, dict):
            # New format: full settings dict
            controller.set_power(1)

            # Set effect
            effect_id = effect_settings.get("effect_id", 0)
            palette_id = effect_settings.get("palette_id", 0)
            speed = effect_settings.get("speed", 128)
            intensity = effect_settings.get("intensity", 128)

            controller.set_effect(effect_id, speed=speed, intensity=intensity)
            controller.set_palette(palette_id)

            # Set colors if provided
            color1 = effect_settings.get("color1")
            if color1:
                # Convert hex to RGB
                r1 = int(color1[1:3], 16)
                g1 = int(color1[3:5], 16)
                b1 = int(color1[5:7], 16)

                color2 = effect_settings.get("color2", "#000000")
                r2 = int(color2[1:3], 16)
                g2 = int(color2[3:5], 16)
                b2 = int(color2[5:7], 16)

                color3 = effect_settings.get("color3", "#0000ff")
                r3 = int(color3[1:3], 16)
                g3 = int(color3[3:5], 16)
                b3 = int(color3[5:7], 16)

                controller.set_colors(
                    color1=(r1, g1, b1),
                    color2=(r2, g2, b2),
                    color3=(r3, g3, b3)
                )

            return True

        # Default: do nothing (keep current LED state)
        return True
    except Exception as e:
        logger.error(f"Error setting playing effect: {e}")
        return False

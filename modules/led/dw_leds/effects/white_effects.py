#!/usr/bin/env python3
"""
White Channel Effects for RGBCCT LED Strips
Provides animation effects for warm/cool white channels
"""
import time
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...dw_led_controller import _DualWS2811RGBCCTProxy

# Effect return value is delay in milliseconds
FRAMETIME = 24  # ~42 FPS, matching RGB effects


def sin16(x: int) -> int:
    """16-bit sine wave approximation (-32767 to 32767)"""
    x = x & 0xFFFF
    if x > 32767:
        x -= 65536
    # Scale to -pi to pi
    angle = (x / 32768.0) * math.pi
    return int(math.sin(angle) * 32767)


def triwave16(x: int) -> int:
    """16-bit triangle wave (0 to 65535)"""
    x = x & 0xFFFF
    if x < 32768:
        return x * 2
    else:
        return (65535 - x) * 2


class WhiteEffect:
    """Base class for white channel effects"""

    def __init__(self, proxy: '_DualWS2811RGBCCTProxy'):
        """
        Initialize white effect

        Args:
            proxy: The _DualWS2811RGBCCTProxy instance to control
        """
        self.proxy = proxy
        self.speed = 128  # 0-255, higher = faster
        self.intensity = 128  # 0-255, effect-specific meaning
        self.start_time = time.time() * 1000  # milliseconds
        self.base_temperature = 4000  # Default center temperature in Kelvin

    def now(self) -> int:
        """Get current time in milliseconds since effect started"""
        return int(time.time() * 1000 - self.start_time)

    def update(self) -> int:
        """
        Update the white channels for this frame
        Returns delay in milliseconds until next update
        """
        raise NotImplementedError("Subclasses must implement update()")


class WhiteTemperatureSweep(WhiteEffect):
    """Smoothly transitions from warm (2700K) to cool (6500K) and back"""

    def update(self) -> int:
        """Update white channels with temperature sweep"""
        # Calculate cycle time based on speed (slower speed = longer cycle)
        # Speed 0 = ~30 seconds, Speed 255 = ~2 seconds
        cycle_time = 30000 - int((self.speed / 255.0) * 28000)

        # Current position in cycle (0 to cycle_time)
        pos = self.now() % cycle_time

        # Calculate progress (0.0 to 1.0) through the cycle
        cycle_progress = pos / cycle_time

        # Use smooth sine wave for more organic temperature transitions
        # Maps 0->1 cycle to 0->1->0 using sine wave (smoother than triangle wave)
        # sin goes from 0 to 1 to 0 as angle goes from 0 to π
        progress = math.sin(cycle_progress * math.pi)

        # Determine temperature range based on intensity
        # Intensity 255 = full range (2700K to 6500K)
        # Intensity 128 = half range centered at 4000K (3150K to 4850K)
        # Intensity 0 = no range (stays at base_temperature)
        min_temp = 2700
        max_temp = 6500
        range_kelvin = max_temp - min_temp

        # Calculate intensity-based range
        intensity_factor = self.intensity / 255.0
        actual_range = range_kelvin * intensity_factor
        center = self.base_temperature

        # Calculate min/max temps centered around base_temperature
        temp_min = max(min_temp, center - actual_range / 2)
        temp_max = min(max_temp, center + actual_range / 2)

        # Calculate current temperature using smooth progress
        current_temp = temp_min + (temp_max - temp_min) * progress

        # Convert temperature to WW/CW ratio
        if current_temp <= 2700:
            ww_ratio = 1.0
        elif current_temp >= 6500:
            ww_ratio = 0.0
        else:
            ww_ratio = 1.0 - (current_temp - 2700) / (6500 - 2700)

        # Set WW/CW at full scale (255) - brightness is controlled separately
        level_255 = 255
        ww = int(level_255 * ww_ratio)
        cw = int(level_255 * (1.0 - ww_ratio))

        # Update proxy
        self.proxy._ww = ww
        self.proxy._cw = cw
        self.proxy._update_all_white_channels()
        self.proxy.show()

        return FRAMETIME


class WhiteTemperaturePulse(WhiteEffect):
    """Rhythmic pulsing between warm and cool temperatures"""

    def update(self) -> int:
        """Update white channels with temperature pulse"""
        # Calculate pulse rate based on speed
        # Speed 0 = slow pulse (~4 seconds), Speed 255 = fast pulse (~0.5 seconds)
        pulse_time = 4000 - int((self.speed / 255.0) * 3500)

        # Current position in pulse cycle
        counter = (self.now() * ((self.speed >> 3) + 10)) & 0xFFFF

        # Create smooth sine wave pulse
        pulse_value = sin16(counter)  # -32767 to 32767
        pulse_normalized = (pulse_value + 32767) / 65535.0  # 0.0 to 1.0

        # Determine temperature range based on intensity
        # Higher intensity = larger temperature swings
        min_temp = 2700
        max_temp = 6500
        center = self.base_temperature

        intensity_factor = self.intensity / 255.0
        temp_range = (max_temp - min_temp) * intensity_factor

        temp_min = max(min_temp, center - temp_range / 2)
        temp_max = min(max_temp, center + temp_range / 2)

        # Calculate current temperature based on pulse
        current_temp = temp_min + (temp_max - temp_min) * pulse_normalized

        # Convert to WW/CW
        if current_temp <= 2700:
            ww_ratio = 1.0
        elif current_temp >= 6500:
            ww_ratio = 0.0
        else:
            ww_ratio = 1.0 - (current_temp - 2700) / (6500 - 2700)

        level_255 = 255
        ww = int(level_255 * ww_ratio)
        cw = int(level_255 * (1.0 - ww_ratio))

        self.proxy._ww = ww
        self.proxy._cw = cw
        self.proxy._update_all_white_channels()
        self.proxy.show()

        return FRAMETIME


class WhiteBrightnessFade(WhiteEffect):
    """Breathing effect that varies brightness while maintaining fixed temperature"""

    def update(self) -> int:
        """Update white channels with brightness fade"""
        # Calculate breathing rate based on speed
        counter = (self.now() * ((self.speed >> 3) + 10)) & 0xFFFF

        # Create smooth sine wave for breathing effect (smoother than triangle wave)
        # sin16 gives -32767 to 32767, convert to 0.0 to 1.0
        brightness_sine = sin16(counter)
        brightness_normalized = (brightness_sine + 32767) / 65535.0

        # Apply easing for more organic breathing effect
        # Use sin² for slower in/out, faster middle
        brightness_normalized = math.sin(brightness_normalized * math.pi / 2) ** 2

        # Intensity controls the brightness range
        # Intensity 255 = full fade (0% to 100%)
        # Intensity 128 = medium fade (25% to 75%)
        # Intensity 0 = no fade (stays at current brightness)
        intensity_factor = self.intensity / 255.0

        # Calculate min/max brightness
        min_brightness = max(0.0, 0.5 - intensity_factor / 2)
        max_brightness = min(1.0, 0.5 + intensity_factor / 2)

        # Map normalized brightness to range
        current_brightness = min_brightness + (max_brightness - min_brightness) * brightness_normalized

        # Use base_temperature for fixed color temperature
        kelvin = self.base_temperature
        if kelvin <= 2700:
            ww_ratio = 1.0
        elif kelvin >= 6500:
            ww_ratio = 0.0
        else:
            ww_ratio = 1.0 - (kelvin - 2700) / (6500 - 2700)

        # Calculate WW/CW at full scale, but will be scaled by brightness in proxy
        level_255 = 255
        ww = int(level_255 * ww_ratio)
        cw = int(level_255 * (1.0 - ww_ratio))

        # Update proxy with new values and brightness
        self.proxy._ww = ww
        self.proxy._cw = cw

        # Temporarily override white brightness for this effect
        # Save the current setting
        saved_brightness = self.proxy._white_brightness

        # Apply effect brightness
        self.proxy._white_brightness = current_brightness
        self.proxy._update_all_white_channels()
        self.proxy.show()

        # Restore original brightness setting (so UI stays in sync)
        self.proxy._white_brightness = saved_brightness

        return FRAMETIME


class WhiteDualChannel(WhiteEffect):
    """Independent WW/CW animations creating alternating or chase-like effects"""

    def update(self) -> int:
        """Update white channels with dual-channel animation"""
        # Calculate animation speed
        counter = self.now() * ((self.speed >> 2) + 5)

        # Create two independent sine waves with phase offset
        # WW channel uses primary sine wave
        ww_counter = counter & 0xFFFF
        ww_sine = sin16(ww_counter)  # -32767 to 32767
        ww_normalized = (ww_sine + 32767) / 65535.0  # 0.0 to 1.0

        # CW channel uses phase-shifted sine wave
        # Phase offset based on intensity (creates different patterns)
        phase_offset = int((self.intensity / 255.0) * 32768)  # 0 to 180 degrees
        cw_counter = (counter + phase_offset) & 0xFFFF
        cw_sine = sin16(cw_counter)
        cw_normalized = (cw_sine + 32767) / 65535.0

        # Map normalized values to WW/CW levels (0-255)
        # Intensity also controls overall amplitude
        intensity_factor = max(0.3, self.intensity / 255.0)  # Minimum 30% to stay visible

        ww = int(255 * ww_normalized * intensity_factor)
        cw = int(255 * cw_normalized * intensity_factor)

        # Update proxy
        self.proxy._ww = ww
        self.proxy._cw = cw
        self.proxy._update_all_white_channels()
        self.proxy.show()

        return FRAMETIME


class WhiteChase(WhiteEffect):
    """Chase effect with warm/cool white segments traveling around the strip with smooth transitions"""

    def __init__(self, proxy: '_DualWS2811RGBCCTProxy'):
        """Initialize chase effect"""
        super().__init__(proxy)
        self.position = 0.0  # Current position of the chase segment (floating-point for smooth motion)

    def update(self) -> int:
        """Update white channels with chase effect"""
        # Get the number of logical LEDs
        num_leds = self.proxy._logical_count

        # Calculate segment size (1/4 of strip, minimum 1 LED)
        segment_size = max(1.0, num_leds / 4.0)

        # Calculate movement speed based on speed parameter
        # Use floating-point position for sub-pixel smooth movement
        # Speed 0 = very slow, Speed 255 = very fast
        speed_factor = (self.speed / 255.0) * 0.5 + 0.01  # 0.01 to 0.51 LEDs per frame

        # Update floating-point position
        self.position = (self.position + speed_factor) % num_leds

        # Intensity controls the contrast between warm and cool
        intensity_factor = self.intensity / 255.0

        # Calculate warm and cool values for background (cool white)
        bg_temp = self.base_temperature + (intensity_factor * 1500)  # Shift cooler
        bg_temp = min(6500, bg_temp)

        if bg_temp <= 2700:
            bg_ww_ratio = 1.0
        elif bg_temp >= 6500:
            bg_ww_ratio = 0.0
        else:
            bg_ww_ratio = 1.0 - (bg_temp - 2700) / (6500 - 2700)

        bg_ww = 255 * bg_ww_ratio
        bg_cw = 255 * (1.0 - bg_ww_ratio)

        # Calculate warm and cool values for chase segment (warm white)
        chase_temp = self.base_temperature - (intensity_factor * 1500)  # Shift warmer
        chase_temp = max(2700, chase_temp)

        if chase_temp <= 2700:
            chase_ww_ratio = 1.0
        elif chase_temp >= 6500:
            chase_ww_ratio = 0.0
        else:
            chase_ww_ratio = 1.0 - (chase_temp - 2700) / (6500 - 2700)

        chase_ww = 255 * chase_ww_ratio
        chase_cw = 255 * (1.0 - chase_ww_ratio)

        # Fade edge size (pixels) - creates smooth leading/trailing edges
        fade_edge = max(1.5, segment_size * 0.3)

        # Update all LEDs with smooth blending
        for i in range(num_leds):
            # Calculate distance from this pixel to the chase segment center
            # Handle wrapping for circular LED strip
            segment_center = self.position + segment_size / 2.0

            # Calculate shortest distance considering wrap-around
            dist = abs(i - segment_center)
            if dist > num_leds / 2:
                dist = num_leds - dist

            # Calculate blend factor based on distance from chase segment
            # 1.0 = fully chase color, 0.0 = fully background color
            half_segment = segment_size / 2.0

            if dist <= half_segment - fade_edge:
                # Fully inside chase segment
                blend = 1.0
            elif dist >= half_segment + fade_edge:
                # Fully outside chase segment (background)
                blend = 0.0
            else:
                # In fade region - smooth transition
                fade_dist = dist - (half_segment - fade_edge)
                blend = 1.0 - (fade_dist / (2.0 * fade_edge))
                blend = max(0.0, min(1.0, blend))  # Clamp to 0-1

            # Blend between chase and background colors
            final_ww = bg_ww + (chase_ww - bg_ww) * blend
            final_cw = bg_cw + (chase_cw - bg_cw) * blend

            # Write to physical pixels, respecting power state and brightness
            self.proxy.write_white_channel(i, final_ww, final_cw)

        # Show the updated pixels
        self.proxy.show()

        return FRAMETIME


class WhiteColorloop(WhiteEffect):
    """Smooth temperature loop across entire strip - like RGB colorloop but with temperature gradient"""

    def __init__(self, proxy: '_DualWS2811RGBCCTProxy'):
        """Initialize colorloop effect"""
        super().__init__(proxy)
        self.gradient_position = 0.0  # Floating-point position for smooth rotation

    def update(self) -> int:
        """Update white channels with temperature gradient loop"""
        # Get the number of logical LEDs
        num_leds = self.proxy._logical_count

        # Calculate animation speed based on speed parameter
        # Use floating-point gradient rotation for smooth movement
        # Speed 0 = very slow rotation, Speed 255 = fast rotation
        speed_factor = (self.speed / 255.0) * 2.0 + 0.05  # 0.05 to 2.05 degrees per frame

        # Update floating-point gradient position (0-255 range for full color cycle)
        self.gradient_position = (self.gradient_position + speed_factor) % 256.0

        # Intensity controls the temperature range
        # 255 = full range (2700K to 6500K)
        # 128 = medium range centered around base_temperature
        # 0 = minimal range (stays near base_temperature)
        intensity_factor = self.intensity / 255.0

        # Calculate temperature range
        min_temp = 2700
        max_temp = 6500
        temp_range = (max_temp - min_temp) * intensity_factor

        # Center the range around base_temperature
        range_min = max(min_temp, self.base_temperature - temp_range / 2)
        range_max = min(max_temp, self.base_temperature + temp_range / 2)

        # Helper function to convert hue (0-255) to temperature and then to WW/CW ratio
        def hue_to_ww_cw(hue_value):
            """Convert hue value (0-255) to WW/CW values with smooth interpolation"""
            # Map hue (0-255) to temperature range
            temp_normalized = (hue_value % 256.0) / 255.0
            current_temp = range_min + (range_max - range_min) * temp_normalized

            # Convert temperature to WW/CW ratio
            if current_temp <= 2700:
                ww_ratio = 1.0
            elif current_temp >= 6500:
                ww_ratio = 0.0
            else:
                ww_ratio = 1.0 - (current_temp - 2700) / (6500 - 2700)

            # Return WW/CW values at full scale (0-255)
            ww = 255 * ww_ratio
            cw = 255 * (1.0 - ww_ratio)
            return ww, cw

        # Update all LEDs with smooth interpolated gradient
        for i in range(num_leds):
            # Calculate floating-point hue position for this pixel
            # Spread gradient evenly across strip
            position_hue = (i / max(1.0, num_leds)) * 256.0

            # Add time-based rotation offset (floating-point for smooth animation)
            pixel_hue = position_hue + self.gradient_position

            # For smoother gradients, blend between adjacent hue values
            # Get integer and fractional parts
            hue_int = int(pixel_hue) % 256
            hue_frac = pixel_hue - int(pixel_hue)

            # Calculate WW/CW for current and next hue values
            ww1, cw1 = hue_to_ww_cw(hue_int)
            ww2, cw2 = hue_to_ww_cw(hue_int + 1)

            # Interpolate between the two hue positions for sub-pixel smoothness
            ww = ww1 + (ww2 - ww1) * hue_frac
            cw = cw1 + (cw2 - cw1) * hue_frac

            # Write to physical pixels, respecting power state and brightness
            self.proxy.write_white_channel(i, ww, cw)

        # Show the updated pixels
        self.proxy.show()

        return FRAMETIME


def get_white_effect(effect_id: int) -> type:
    """
    Get white effect class by ID

    Args:
        effect_id: Effect ID (0-3)

    Returns:
        White effect class
    """
    effects = {
        0: WhiteBrightnessFade,
        1: WhiteChase,
        2: WhiteColorloop,
        3: WhiteDualChannel,
        4: WhiteTemperaturePulse,
        5: WhiteTemperatureSweep
    }
    return effects.get(effect_id, WhiteBrightnessFade)


def get_all_white_effects() -> list:
    """
    Get list of all available white effects

    Returns:
        List of tuples (effect_id, effect_name)
    """
    return [
        (0, "Brightness Fade"),
        (1, "Chase"),
        (2, "Colorloop"),
        (3, "Dual Channel"),
        (4, "Temperature Pulse"),
        (5, "Temperature Sweep")
    ]

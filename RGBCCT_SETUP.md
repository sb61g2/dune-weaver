# RGBCCT LED Strip Setup Guide

This guide explains how to use RGBCCT (RGB + Cool White + Warm White) LED strips with dual WS2811 chips in the Dune Weaver sand table system.

## What are RGBCCT LED Strips?

RGBCCT LED strips combine RGB color LEDs with two separate white LED channels:
- **RGB**: Red, Green, Blue for full color control
- **WW**: Warm White (typically 2700-3000K)
- **CW**: Cool White (typically 6000-6500K)

This allows for:
- Full RGB colors for effects and ambiance
- Adjustable color temperature white light (from warm to cool)
- Better white light quality compared to RGB-only or RGBW strips

## Dual WS2811 Architecture

RGBCCT strips use **dual WS2811 chips** per LED segment:
- Each LED uses **5 bytes of data**: R, G, B, WW, CW
- The data protocol is the same as standard WS281x strips
- Compatible with standard GPIO output on Raspberry Pi

### Common RGBCCT Strip Models

The implementation supports strips like:
- Amazon item B0F18B829B and similar dual WS2811 RGBCCT strips
- 5-channel addressable LED strips with WS2811 controllers
- Strips marketed as "RGBCCT" or "RGB+CCT" with WS2811
- **COB/Neon RGBCCT strips** (24V, multiple LEDs per IC) - See special configuration below

## IMPORTANT: Strip Type Differences

### Individual LED Strips (5V, 1 IC per LED)
- Each LED is individually addressable
- Set `num_leds` to total LED count (e.g., 60, 144, etc.)
- Use 5V power supply
- Direct GPIO connection usually works

### COB/Neon Strips (24V, multiple LEDs per IC)
**Example: 840 LEDs/m with 24 ICs/m**
- Each IC controls a GROUP of LEDs (e.g., 35 LEDs per IC)
- ⚠️ **Set `num_leds` to IC COUNT, not LED count**
  - 30" strip ≈ 18 ICs = set `num_leds` to 18
  - 1m strip = 24 ICs = set `num_leds` to 24
  - 5m strip = 120 ICs = set `num_leds` to 120
- **Use 3-byte pixel order (RGB, GRB, or BRG)** - NOT 5-byte RGBWW
- Requires 24V power supply
- May work without level shifter (3.3V often sufficient for WS2811)
- Only cuts at IC boundaries (check cut marks on strip)

## Hardware Setup

### Wiring

Connect your RGBCCT strip to the Raspberry Pi:

1. **Power**: Connect strip's voltage (+5V/+12V/+24V) and GND to appropriate power supply
   - **IMPORTANT**: Use a separate power supply for the LEDs (not the Pi's power)
   - Match voltage to your strip (5V, 12V, or 24V)
   - Calculate power needs based on strip specifications
   - Example: 24V strip at 135W = 5.6A, use 24V 6-8A supply

2. **Level Shifter** (required for 12V/24V strips):
   - Use 74HCT245 or 74AHCT125 level shifter
   - Converts Pi's 3.3V GPIO signal to 5V for WS2811
   - Wiring:
     ```
     Pi 3.3V → Level Shifter VCC_A (low voltage side)
     Pi 5V   → Level Shifter VCC_B (high voltage side)
     Pi GPIO → Level Shifter A input
     Level Shifter B output → LED Strip DATA
     Pi GND  → Level Shifter GND → LED Power Supply GND
     ```

3. **Data**: Connect to GPIO pin through level shifter:
   - Recommended pins: GPIO 18 (default), GPIO 12, GPIO 13, or GPIO 19
   - For 24V strips: GPIO → Level Shifter → DATA pin
   - For 5V strips: GPIO → 330Ω resistor → DATA pin (level shifter optional but recommended)
   - Keep data wire as short as possible (< 20cm ideal)

4. **Ground**: **CRITICAL** - Common ground required
   - Connect Raspberry Pi GND to LED strip power supply GND
   - This must be connected even with level shifter

### Power Supply Sizing

Example for a 60 LED strip:
- Maximum current: 60 LEDs × 60mA = 3.6A
- Recommended power supply: 5V 5A or 12V 3A (depending on strip voltage)
- Add 20% overhead for safety: 5V 6A or 12V 4A

## Software Configuration

### 1. Settings UI Configuration

1. Navigate to Settings → LED Configuration
2. Enable "Direct GPIO LED Control (DW LEDs)"
3. Configure the following:
   - **Number of LEDs**: Enter the total count (e.g., 60)
   - **GPIO Pin**: Select the data pin (default: 18)
   - **Pixel Color Order**: Select from RGBCCT options:
     - **GRBWW** - Most common for dual WS2811 RGBCCT strips (recommended)
     - **RGBWW** - Alternative variant if colors are incorrect with GRBWW

4. Click "Save LED Configuration"
5. The system will restart the LED controller with new settings

### 2. Testing the Configuration

After configuration:

1. **Power Test**: LEDs should respond to power on/off commands
2. **Color Test**: Try setting different colors to verify RGB channels
3. **White Test**: Effects with white should show proper color temperature

If colors appear incorrect:
- Try switching between GRBWW and RGBWW pixel orders
- Verify your strip's actual pixel order (check manufacturer specs)
- Ensure power supply is adequate

### 3. Pixel Order Reference

The pixel order string tells the controller the byte order for each LED:
- **G**RB**WW**: Green, Red, Blue, Warm White, Cool White
- **R**GB**WW**: Red, Green, Blue, Warm White, Cool White

The last two W's represent Warm White and Cool White channels.

## Using RGBCCT Features

### Color Control

The system handles both RGB colors and white channels independently:
- **R, G, B**: Standard RGB color values for colored effects (0-255 each)
- **W (WW)**: Warm white intensity (0-255)
- **CW**: Cool white intensity (0-255)

### RGB Color Effects

Standard LED effects use the RGB channels:
- All color-based effects (rainbow, solid colors, etc.) use RGB channels
- RGB effects and white channels operate independently
- You can have RGB effects running while also using the white channels

### White Channel Control

The UI provides dedicated controls for the warm/cool white channels:

1. **Enable Dual WS2811 Mode**: Check the "Dual WS2811 RGBCCT Mode" checkbox in LED Configuration
2. **Color Temperature Slider**: Adjust from 2700K (warm, orange-tinted) to 6500K (cool, blue-tinted)
3. **White Brightness**: Control the intensity of the white channels (0-100%)
4. **Apply White Settings**: Click to apply your color temperature and brightness settings

The white channel controls appear automatically when Dual WS2811 mode is enabled. These controls are separate from RGB effects, allowing you to:
- Use warm white for ambient lighting while RGB effects are off
- Mix white light with RGB color effects
- Adjust color temperature for different moods or times of day

## Specific Strip Configurations

### 24V COB/Neon RGBCCT Strip (840 LEDs/m, 24 ICs/m)

**Product Example**: SuperLighting 24V WS2811 RGBCCT COB Neon Strip

**Configuration**:
1. **Identify IC count**:
   - Check specs: ICs per meter (e.g., 24 ICs/m)
   - Measure strip length in meters
   - Calculate: ICs per meter × length in meters
   - Example: 24 ICs/m × 1m = **24** (this is your `num_leds` value!)

2. **Settings**:
   - Number of LEDs: **18** (for 30" strip), **24** (for 1m), or **120** (for 5m roll)
   - GPIO Pin: 18 (or your chosen PWM pin)
   - **Pixel Order: Use RGB or GRB** (3-byte format)
     - Most 24V COB WS2811 strips use 3-byte RGB format
     - RGBWW/GRBWW options will automatically fall back to RGB/GRB
     - Try: **RGB** first, then **GRB**, then **BRG** if colors are wrong
   - Brightness: Start at 35%

3. **Required Hardware**:
   - 24V DC power supply (6-8A for 5m strip)
   - 74HCT245 level shifter (converts 3.3V → 5V)
   - Wiring as shown in Hardware Setup above

4. **Common Issues**:
   - **Only 2 segments light in red**: Using 5-byte pixel order (RGBWW/GRBWW) instead of 3-byte (RGB/GRB)
     - **Solution**: Select RGB, GRB, or BRG from pixel order dropdown
   - **Only some pixels light**: `num_leds` set to LED count instead of IC count
   - **Wrong colors**: Try different 3-byte pixel orders (RGB → GRB → BRG)
   - **Flickering**: Poor power supply or missing common ground

**IMPORTANT for 24V COB Strips**: These strips use **3-byte RGB data format** per IC, not 5-byte RGBCCT. Select RGB, GRB, or BRG pixel orders.

## Troubleshooting

### Only some "pixels" lighting / Only red color
- **24V strips**: You probably set `num_leds` to the LED count instead of IC count
  - Check strip specifications for "ICs per meter"
  - Set `num_leds` to IC count, not LED count
  - Example: 840 LEDs/m with 24 ICs/m = use 24, not 840
- Add level shifter for 24V strips (required)
- Try different pixel orders (RGBWW vs GRBWW)

### No brightness control
- 24V strips need a logic level shifter
- Verify pixel order is correct
- Check that power supply voltage matches strip voltage

### LEDs not responding
- Check power supply connections and voltage
- Verify GPIO pin configuration matches wiring
- Ensure data line resistor is present (330Ω-470Ω)
- Check that ground is shared between Pi and LED power supply

### Wrong colors displayed
- Try different pixel order settings (GRBWW vs RGBWW)
- Verify strip is actually RGBCCT (5-channel) not RGBW (4-channel)
- Check manufacturer specifications for correct byte order

### Flickering or unstable behavior
- Power supply may be insufficient - upgrade to higher amperage
- Data line may be too long - keep under 20cm or use level shifter
- Add a large capacitor (1000μF, 6.3V+) across LED strip power terminals

### Dim output
- Check brightness settings in LED controller
- Verify power supply voltage (should be 5V ±0.25V or 12V ±0.5V)
- Ensure power supply can deliver required current

## Technical Details

### Color Format

Internally, the system uses a 40-bit color representation:
```
Bits 32-39: Cool White (CW)
Bits 24-31: Warm White (WW/W)
Bits 16-23: Red (R)
Bits  8-15: Green (G)
Bits  0-7:  Blue (B)
```

### NeoPixel Library Configuration

The system automatically configures the NeoPixel library with:
- **bpp=5**: 5 bytes per pixel for RGBCCT
- **pixel_order**: GRBWW or RGBWW as selected
- **auto_write=False**: For efficient batch updates

### File Changes Summary

The RGBCCT support was added across several files:
- `modules/led/dw_leds/utils/colors.py` - 5-channel color utilities
- `modules/led/dw_leds/segment.py` - 5-channel pixel handling
- `modules/led/dw_led_controller.py` - RGBCCT initialization
- `templates/settings.html` - UI configuration options

## References

- [Adafruit NeoPixel Library](https://github.com/adafruit/Adafruit_CircuitPython_NeoPixel)
- [WS2811 Datasheet](https://cdn-shop.adafruit.com/datasheets/WS2811.pdf)
- [Raspberry Pi GPIO Pinout](https://pinout.xyz/)

## Need Help?

If you encounter issues:
1. Check the troubleshooting section above
2. Verify your wiring matches the hardware setup section
3. Test with a small number of LEDs first (e.g., 10) to rule out power issues
4. Consult the Dune Weaver GitHub issues page for community support

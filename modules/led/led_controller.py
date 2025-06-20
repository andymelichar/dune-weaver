import requests
import json
from typing import Dict, Optional
import time
import logging
import math
import colorsys
logger = logging.getLogger(__name__)


class LEDController:
    def __init__(self, ip_address: Optional[str] = None):
        self.ip_address = ip_address
        self.position_sync_enabled = False
        self.sync_mode = "position"  # Options: "position", "speed", "progress", "trail", "demo", "localized"
        self.last_sync_time = 0
        self.sync_throttle_ms = 20  # Minimum ms between sync updates (reduced for better responsiveness)
        # Localized mode configuration
        self.total_leds = 60  # Total number of LEDs in strip
        self.segment_width = 8  # Number of LEDs to light up around ball position

    def _get_base_url(self) -> str:
        """Get base URL for WLED JSON API"""
        if not self.ip_address:
            raise ValueError("No WLED IP configured")
        return f"http://{self.ip_address}/json"

    def set_ip(self, ip_address: str) -> None:
        """Update the WLED IP address"""
        self.ip_address = ip_address

    def _send_command(self, state_params: Dict = None) -> Dict:
        """Send command to WLED and return status"""
        try:
            url = self._get_base_url()
            
            # First check current state
            response = requests.get(f"{url}/state", timeout=2)
            response.raise_for_status()
            current_state = response.json()
            
            # If WLED is off and we're trying to set something, turn it on first
            if not current_state.get('on', False) and state_params and 'on' not in state_params:
                # Turn on power first
                requests.post(f"{url}/state", json={"on": True}, timeout=2)
            
            # Now send the actual command if there are parameters
            if state_params:
                response = requests.post(f"{url}/state", json=state_params, timeout=2)
                response.raise_for_status()
                response = requests.get(f"{url}/state", timeout=2)
                response.raise_for_status()
                current_state = response.json()
                
            preset_id = current_state.get('ps', -1)
            playlist_id = current_state.get('pl', -1)

            # Use True as default since WLED is typically on when responding
            is_on = current_state.get('on', True)
            
            return {
                "connected": True,
                "is_on": is_on,
                "preset_id": preset_id,
                "playlist_id": playlist_id,
                "brightness": current_state.get('bri', 0),
                "message": "WLED is ON" if is_on else "WLED is OFF"
            }

        except ValueError as e:
            return {"connected": False, "message": str(e)}
        except requests.RequestException as e:
            return {"connected": False, "message": f"Cannot connect to WLED: {str(e)}"}
        except json.JSONDecodeError as e:
            return {"connected": False, "message": f"Error parsing WLED response: {str(e)}"}

    def check_wled_status(self) -> Dict:
        """Check WLED connection status and brightness"""
        return self._send_command()

    def set_brightness(self, value: int) -> Dict:
        """Set WLED brightness (0-255)"""
        if not 0 <= value <= 255:
            return {"connected": False, "message": "Brightness must be between 0 and 255"}
        return self._send_command({"bri": value})

    def set_power(self, state: int) -> Dict:
        """Set WLED power state (0=Off, 1=On, 2=Toggle)"""
        if state not in [0, 1, 2]:
            return {"connected": False, "message": "Power state must be 0 (Off), 1 (On), or 2 (Toggle)"}
        if state == 2:
            return self._send_command({"on": "t"})  # Toggle
        return self._send_command({"on": bool(state)})

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """Convert hex color string to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) != 6:
            raise ValueError("Hex color must be 6 characters long (without #)")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def set_color(self, r: int = None, g: int = None, b: int = None, w: int = None, hex: str = None) -> Dict:
        """Set WLED color using RGB(W) values or hex color code"""
        if hex is not None:
            try:
                r, g, b = self._hex_to_rgb(hex)
            except ValueError as e:
                return {"connected": False, "message": str(e)}

        # Prepare segment with color
        seg = {"col": [[r or 0, g or 0, b or 0]]}
        if w is not None:
            if not 0 <= w <= 255:
                return {"connected": False, "message": "White value must be between 0 and 255"}
            seg["col"][0].append(w)

        return self._send_command({"seg": [seg]})

    def set_effect(self, effect_index: int, speed: int = None, intensity: int = None, 
                   brightness: int = None, palette: int = None,
                   # Primary color
                   r: int = None, g: int = None, b: int = None, w: int = None, hex: str = None,
                   # Secondary color
                   r2: int = None, g2: int = None, b2: int = None, w2: int = None, hex2: str = None,
                   # Transition
                   transition: int = 0) -> Dict:
        """
        Set WLED effect with optional parameters
        Args:
            effect_index: Effect index (0-101)
            speed: Effect speed (0-255)
            intensity: Effect intensity (0-255)
            brightness: LED brightness (0-255)
            palette: FastLED palette index (0-46)
            r, g, b: Primary RGB color values (0-255)
            w: Primary White value for RGBW (0-255)
            hex: Primary hex color code (e.g., '#ff0000' or 'ff0000')
            r2, g2, b2: Secondary RGB color values (0-255)
            w2: Secondary White value for RGBW (0-255)
            hex2: Secondary hex color code
            transition: Duration of crossfade in 100ms units (e.g. 7 = 700ms). Default 0 for instant change.
        """
        try:
            effect_index = int(effect_index)
        except (ValueError, TypeError):
            return {"connected": False, "message": "Effect index must be a valid integer between 0 and 101"}

        if not 0 <= effect_index <= 101:
            return {"connected": False, "message": "Effect index must be between 0 and 101"}

        # Convert primary hex to RGB if provided
        if hex is not None:
            try:
                r, g, b = self._hex_to_rgb(hex)
            except ValueError as e:
                return {"connected": False, "message": f"Primary color: {str(e)}"}

        # Convert secondary hex to RGB if provided
        if hex2 is not None:
            try:
                r2, g2, b2 = self._hex_to_rgb(hex2)
            except ValueError as e:
                return {"connected": False, "message": f"Secondary color: {str(e)}"}

        # Build segment parameters
        seg = {"fx": effect_index}
        
        if speed is not None:
            if not 0 <= speed <= 255:
                return {"connected": False, "message": "Speed must be between 0 and 255"}
            seg["sx"] = speed
        
        if intensity is not None:
            if not 0 <= intensity <= 255:
                return {"connected": False, "message": "Intensity must be between 0 and 255"}
            seg["ix"] = intensity

        # Prepare colors array
        colors = []
        
        # Add primary color
        primary = [r or 0, g or 0, b or 0]
        if w is not None:
            if not 0 <= w <= 255:
                return {"connected": False, "message": "Primary white value must be between 0 and 255"}
            primary.append(w)
        colors.append(primary)
        
        # Add secondary color if any secondary color parameter is provided
        if any(x is not None for x in [r2, g2, b2, w2, hex2]):
            secondary = [r2 or 0, g2 or 0, b2 or 0]
            if w2 is not None:
                if not 0 <= w2 <= 255:
                    return {"connected": False, "message": "Secondary white value must be between 0 and 255"}
                secondary.append(w2)
            colors.append(secondary)

        if colors:
            seg["col"] = colors

        if palette is not None:
            if not 0 <= palette <= 46:
                return {"connected": False, "message": "Palette index must be between 0 and 46"}
            seg["pal"] = palette

        # Combine with global parameters
        state = {"seg": [seg], "transition": transition}
        if brightness is not None:
            if not 0 <= brightness <= 255:
                return {"connected": False, "message": "Brightness must be between 0 and 255"}
            state["bri"] = brightness

        return self._send_command(state)

    def set_preset(self, preset_id: int) -> bool:
        preset_id = int(preset_id)
        # Send the command and get response
        response = self._send_command({"ps": preset_id})
        logger.debug(response)
        return response

    def enable_position_sync(self, enabled: bool = True, mode: str = "position") -> None:
        """
        Enable or disable position-based LED sync
        Args:
            enabled: Whether to enable position sync
            mode: Sync mode - "position", "speed", "progress", or "trail"
        """
        self.position_sync_enabled = enabled
        if mode in ["position", "speed", "progress", "trail", "demo", "localized"]:
            self.sync_mode = mode
        logger.info(f"Position sync {'enabled' if enabled else 'disabled'} with mode: {self.sync_mode}")

    def configure_localized_mode(self, total_leds: int = 60, segment_width: int = 8) -> None:
        """
        Configure parameters for localized mode
        Args:
            total_leds: Total number of LEDs in the strip
            segment_width: Number of LEDs to light up around the ball position
        """
        self.total_leds = max(1, total_leds)  # Ensure at least 1 LED
        self.segment_width = max(1, min(segment_width, total_leds))  # Ensure valid segment width
        logger.info(f"Localized mode configured: {self.total_leds} LEDs, segment width {self.segment_width}")

    def _should_sync(self) -> bool:
        """Check if enough time has passed since last sync to avoid overwhelming WLED"""
        current_time = time.time() * 1000  # Convert to ms
        if current_time - self.last_sync_time >= self.sync_throttle_ms:
            self.last_sync_time = current_time
            return True
        return False
    
    def _should_sync_with_position_check(self, theta: float, rho: float) -> bool:
        """Advanced throttling that considers position changes"""
        current_time = time.time() * 1000
        
        # Always sync if enough time has passed
        if current_time - self.last_sync_time >= self.sync_throttle_ms:
            self.last_sync_time = current_time
            self._last_theta = theta
            self._last_rho = rho
            return True
        
        # Also sync if position changed significantly (even if time hasn't passed)
        if hasattr(self, '_last_theta') and hasattr(self, '_last_rho'):
            theta_change = abs(theta - self._last_theta)
            rho_change = abs(rho - self._last_rho)
            
            # Sync if position changed significantly
            significant_change_threshold = 0.1  # About 6 degrees or 10% radius change
            if theta_change > significant_change_threshold or rho_change > significant_change_threshold:
                self.last_sync_time = current_time
                self._last_theta = theta
                self._last_rho = rho
                return True
        
        return False

    def _theta_to_hue(self, theta: float) -> int:
        """Convert theta (radians) to HSV hue (0-360)"""
        # Normalize theta to 0-2π range
        normalized_theta = theta % (2 * math.pi)
        # Convert to 0-360 degree range
        hue = int((normalized_theta / (2 * math.pi)) * 360)
        return hue

    def _rho_to_brightness(self, rho: float, min_brightness: int = 50, max_brightness: int = 255) -> int:
        """Convert rho (0-1) to brightness with minimum threshold"""
        # Ensure rho is in 0-1 range
        rho = max(0.0, min(1.0, rho))
        # Map to brightness range with minimum threshold - use higher minimum for visibility
        brightness = int(min_brightness + (rho * (max_brightness - min_brightness)))
        return brightness

    def _hsv_to_rgb(self, h: float, s: float, v: float) -> tuple:
        """Convert HSV to RGB values (0-255)"""
        r, g, b = colorsys.hsv_to_rgb(h / 360.0, s, v)
        return int(r * 255), int(g * 255), int(b * 255)

    def sync_position(self, theta: float, rho: float, progress: float = None, speed: float = None) -> Dict:
        """
        Sync LEDs with ball position
        Args:
            theta: Angular position in radians
            rho: Radial position (0=center, 1=perimeter)
            progress: Optional pattern progress (0-1)
            speed: Optional movement speed for dynamic effects
        """
        # Use smarter throttling, but disable for localized mode if throttle is very low
        if self.sync_mode == "localized" and self.sync_throttle_ms <= 10:
            should_sync = True  # No throttling for localized mode with low throttle
        else:
            should_sync = self._should_sync_with_position_check(theta, rho)
        
        logger.debug(f"🔧 sync_position called: enabled={self.position_sync_enabled}, should_sync={should_sync}, mode={self.sync_mode}")
        
        if not self.position_sync_enabled:
            return {"message": "Position sync disabled"}
        if not should_sync:
            return {"message": "Position sync throttled"}

        try:
            if self.sync_mode == "position":
                return self._sync_position_mode(theta, rho)
            elif self.sync_mode == "speed":
                return self._sync_speed_mode(theta, rho, speed or 0)
            elif self.sync_mode == "progress":
                return self._sync_progress_mode(theta, rho, progress or 0)
            elif self.sync_mode == "trail":
                return self._sync_trail_mode(theta, rho)
            elif self.sync_mode == "demo":
                return self._sync_demo_mode(theta, rho)
            elif self.sync_mode == "localized":
                return self._sync_localized_mode(theta, rho)
            else:
                return {"message": f"Unknown sync mode: {self.sync_mode}"}
        except Exception as e:
            logger.error(f"Error in position sync: {e}")
            return {"connected": False, "message": f"Position sync error: {str(e)}"}

    def _sync_position_mode(self, theta: float, rho: float) -> Dict:
        """Position-based color mapping: hue from angle, brightness from radius"""
        hue = self._theta_to_hue(theta)
        brightness = self._rho_to_brightness(rho)
        r, g, b = self._hsv_to_rgb(hue, 1.0, 1.0)  # Full saturation
        
        logger.debug(f"Position sync: theta={theta:.3f} -> hue={hue}, rho={rho:.3f} -> brightness={brightness}, RGB=({r},{g},{b})")
        
        return self.set_effect(
            effect_index=0,  # Solid color
            r=r, g=g, b=b,
            brightness=brightness,
            transition=0  # Instant change for smooth tracking
        )

    def _sync_speed_mode(self, theta: float, rho: float, speed: float) -> Dict:
        """Speed-based effects: faster movement = more intense effects"""
        hue = self._theta_to_hue(theta)
        # Map speed to effect intensity and speed
        effect_speed = min(255, int(abs(speed) * 50))  # Scale speed appropriately
        effect_intensity = min(255, int(abs(speed) * 100))
        brightness = self._rho_to_brightness(rho)
        r, g, b = self._hsv_to_rgb(hue, 1.0, 1.0)
        
        return self.set_effect(
            effect_index=47,  # Scanner effect that responds well to speed
            r=r, g=g, b=b,
            speed=effect_speed,
            intensity=effect_intensity,
            brightness=brightness
        )

    def _sync_progress_mode(self, theta: float, rho: float, progress: float) -> Dict:
        """Progress-based lighting: color transitions based on pattern completion"""
        # Shift hue based on progress (red -> yellow -> green -> blue -> purple)
        base_hue = self._theta_to_hue(theta)
        progress_hue = (base_hue + int(progress * 120)) % 360  # 120 degree shift over progress
        brightness = self._rho_to_brightness(rho)
        r, g, b = self._hsv_to_rgb(progress_hue, 1.0, 1.0)
        
        return self.set_effect(
            effect_index=0,  # Solid color
            r=r, g=g, b=b,
            brightness=brightness
        )

    def _sync_trail_mode(self, theta: float, rho: float) -> Dict:
        """Trail effect: creates a comet-like trailing effect"""
        hue = self._theta_to_hue(theta)
        brightness = self._rho_to_brightness(rho)
        r, g, b = self._hsv_to_rgb(hue, 1.0, 1.0)
        
        return self.set_effect(
            effect_index=28,  # Comet effect
            r=r, g=g, b=b,
            speed=150,  # Moderate speed for smooth trail
            intensity=200,  # High intensity for visible trail
            brightness=brightness
        )

    def _sync_demo_mode(self, theta: float, rho: float) -> Dict:
        """Demo mode: Very obvious color changes for testing and debugging"""
        hue = self._theta_to_hue(theta)
        
        # Make brightness changes very dramatic
        brightness = 100 + int(rho * 155)  # Range 100-255 for high visibility
        
        # Use pure colors for maximum contrast
        if hue < 60:  # Red zone
            r, g, b = 255, 0, 0
        elif hue < 120:  # Yellow zone  
            r, g, b = 255, 255, 0
        elif hue < 180:  # Green zone
            r, g, b = 0, 255, 0
        elif hue < 240:  # Cyan zone
            r, g, b = 0, 255, 255
        elif hue < 300:  # Blue zone
            r, g, b = 0, 0, 255
        else:  # Magenta zone
            r, g, b = 255, 0, 255
        
        logger.info(f"DEMO MODE: theta={theta:.3f} -> hue={hue} -> color zone, rho={rho:.3f} -> brightness={brightness}")
        
        return self.set_effect(
            effect_index=0,  # Solid color for immediate response
            r=r, g=g, b=b,
            brightness=brightness,
            transition=0  # Instant change
        )

    def _sync_localized_mode(self, theta: float, rho: float) -> Dict:
        """Localized mode: Only light up LEDs near the ball's angular position"""
        # Configuration for LED strip
        total_leds = getattr(self, 'total_leds', 60)  # Default to 60 LEDs, can be configured
        segment_width = getattr(self, 'segment_width', 8)  # How many LEDs to light up around the position
        
        # Convert theta (0 to 2π) to LED position (0 to total_leds-1)
        normalized_theta = theta % (2 * math.pi)
        led_position = int((normalized_theta / (2 * math.pi)) * total_leds)
        
        # Calculate segment boundaries
        half_width = segment_width // 2
        start_led = (led_position - half_width) % total_leds
        end_led = (led_position + half_width) % total_leds
        
        # Get color based on position
        hue = self._theta_to_hue(theta)
        brightness = self._rho_to_brightness(rho)
        r, g, b = self._hsv_to_rgb(hue, 1.0, 1.0)
        
        logger.info(f"LOCALIZED MODE: theta={theta:.3f} -> LED {led_position}/{total_leds}, segment {start_led}-{end_led}, rho={rho:.3f} -> brightness={brightness}")
        
        try:
            # Create segments: one for the active area, one for the rest
            if start_led <= end_led:
                # Normal case: segment doesn't wrap around
                segments = [
                    {
                        "start": 0,
                        "stop": start_led - 1 if start_led > 0 else 0,
                        "col": [[0, 0, 0]],  # Off
                        "fx": 0
                    },
                    {
                        "start": start_led,
                        "stop": end_led,
                        "col": [[r, g, b]],  # Ball color
                        "fx": 0
                    },
                    {
                        "start": end_led + 1,
                        "stop": total_leds - 1,
                        "col": [[0, 0, 0]],  # Off
                        "fx": 0
                    }
                ]
            else:
                # Wrap-around case: segment crosses the 0/max boundary
                segments = [
                    {
                        "start": 0,
                        "stop": end_led,
                        "col": [[r, g, b]],  # Ball color (end part)
                        "fx": 0
                    },
                    {
                        "start": end_led + 1,
                        "stop": start_led - 1,
                        "col": [[0, 0, 0]],  # Off (middle)
                        "fx": 0
                    },
                    {
                        "start": start_led,
                        "stop": total_leds - 1,
                        "col": [[r, g, b]],  # Ball color (start part)
                        "fx": 0
                    }
                ]
            
            # Filter out invalid segments (where start > stop in normal case)
            valid_segments = []
            for seg in segments:
                if seg["start"] <= seg["stop"]:
                    valid_segments.append(seg)
            
            # Send command to WLED
            state_params = {
                "seg": valid_segments,
                "bri": brightness,
                "transition": 0
            }
            
            return self._send_command(state_params)
            
        except Exception as e:
            logger.error(f"Error in localized mode: {e}")
            # Fallback to regular position mode
            return self._sync_position_mode(theta, rho)


def effect_loading(led_controller: LEDController):
    res = led_controller.set_effect(47, hex='#ffa000', hex2='#000000', palette=0, speed=150, intensity=150)
    if res.get('is_on', False):
        return True
    else:
        return False

def effect_idle(led_controller: LEDController):
    led_controller.set_preset(1)


def effect_connected(led_controller: LEDController):
    res = led_controller.set_effect(0, hex='#08ff00', brightness=100)
    time.sleep(1)
    led_controller.set_effect(0, brightness=0)  # Turn off
    time.sleep(0.5)
    res = led_controller.set_effect(0, hex='#08ff00', brightness=100)
    time.sleep(1)
    effect_idle(led_controller)
    if res.get('is_on', False):
        return True
    else:
        return False


def effect_playing(led_controller: LEDController):
    led_controller.set_preset(2)

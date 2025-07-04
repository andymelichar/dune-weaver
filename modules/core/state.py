# state.py
import threading
import json
import os
import logging

logger = logging.getLogger(__name__)

class AppState:
    def __init__(self):
        # Private variables for properties
        self._current_playing_file = None
        self._pause_requested = False
        self._speed = 130
        self._current_playlist = None
        self._current_playlist_name = None  # New variable for playlist name
        
        # Regular state variables
        self.stop_requested = False
        self.pause_condition = threading.Condition()
        self.execution_progress = None
        self.is_clearing = False
        self.current_theta = 0
        self.current_rho = 0
        self.current_playlist_index = 0
        self.playlist_mode = "loop"
        
        # Machine position variables
        self.machine_x = 0.0
        self.machine_y = 0.0
        self.x_steps_per_mm = 0.0
        self.y_steps_per_mm = 0.0
        self.gear_ratio = 10
        # 0 for crash homing, 1 for auto homing
        self.homing = 0
        
        self.STATE_FILE = "state.json"
        self.mqtt_handler = None  # Will be set by the MQTT handler
        self.conn = None
        self.port = None
        self.wled_ip = None
        self.led_controller = None
        self.skip_requested = False
        self.table_type = None
        self._playlist_mode = "loop"
        self._pause_time = 0
        self._clear_pattern = "none"
        # Position sync settings
        self.position_sync_enabled = False
        self.position_sync_mode = "position"
        self.position_sync_throttle_ms = 50
        # Localized mode settings
        self.led_total_leds = 60
        self.led_segment_width = 8
        self.load()

    @property
    def current_playing_file(self):
        return self._current_playing_file

    @current_playing_file.setter
    def current_playing_file(self, value):
        self._current_playing_file = value
        
        # force an empty string (and not None) if we need to unset
        if value == None:
            value = ""
        if self.mqtt_handler:
            is_running = bool(value and not self._pause_requested)
            self.mqtt_handler.update_state(current_file=value, is_running=is_running)

    @property
    def pause_requested(self):
        return self._pause_requested

    @pause_requested.setter
    def pause_requested(self, value):
        self._pause_requested = value
        if self.mqtt_handler:
            is_running = bool(self._current_playing_file and not value)
            self.mqtt_handler.update_state(is_running=is_running)

    @property
    def speed(self):
        return self._speed

    @speed.setter
    def speed(self, value):
        self._speed = value
        if self.mqtt_handler and self.mqtt_handler.is_enabled:
            self.mqtt_handler.client.publish(f"{self.mqtt_handler.speed_topic}/state", value, retain=True)

    @property
    def current_playlist(self):
        return self._current_playlist

    @current_playlist.setter
    def current_playlist(self, value):
        self._current_playlist = value
        
        # force an empty string (and not None) if we need to unset
        if value == None:
            value = ""
            # Also clear the playlist name when playlist is cleared
            self._current_playlist_name = None
        if self.mqtt_handler:
            self.mqtt_handler.update_state(playlist=value, playlist_name=None)

    @property
    def current_playlist_name(self):
        return self._current_playlist_name

    @current_playlist_name.setter
    def current_playlist_name(self, value):
        self._current_playlist_name = value
        if self.mqtt_handler:
            self.mqtt_handler.update_state(playlist_name=value)

    @property
    def playlist_mode(self):
        return self._playlist_mode

    @playlist_mode.setter
    def playlist_mode(self, value):
        self._playlist_mode = value

    @property
    def pause_time(self):
        return self._pause_time

    @pause_time.setter
    def pause_time(self, value):
        self._pause_time = value

    @property
    def clear_pattern(self):
        return self._clear_pattern

    @clear_pattern.setter
    def clear_pattern(self, value):
        self._clear_pattern = value

    def to_dict(self):
        """Return a dictionary representation of the state."""
        return {
            "stop_requested": self.stop_requested,
            "pause_requested": self._pause_requested,
            "current_playing_file": self._current_playing_file,
            "execution_progress": self.execution_progress,
            "is_clearing": self.is_clearing,
            "current_theta": self.current_theta,
            "current_rho": self.current_rho,
            "speed": self._speed,
            "machine_x": self.machine_x,
            "machine_y": self.machine_y,
            "x_steps_per_mm": self.x_steps_per_mm,
            "y_steps_per_mm": self.y_steps_per_mm,
            "gear_ratio": self.gear_ratio,
            "homing": self.homing,
            "current_playlist": self._current_playlist,
            "current_playlist_name": self._current_playlist_name,
            "current_playlist_index": self.current_playlist_index,
            "playlist_mode": self._playlist_mode,
            "pause_time": self._pause_time,
            "clear_pattern": self._clear_pattern,
            "port": self.port,
            "wled_ip": self.wled_ip,
            "position_sync_enabled": self.position_sync_enabled,
            "position_sync_mode": self.position_sync_mode,
            "position_sync_throttle_ms": self.position_sync_throttle_ms,
            "led_total_leds": self.led_total_leds,
            "led_segment_width": self.led_segment_width
        }

    def from_dict(self, data):
        """Update state from a dictionary."""
        self.stop_requested = data.get("stop_requested", False)
        self._pause_requested = data.get("pause_requested", False)
        self._current_playing_file = data.get("current_playing_file")
        self.execution_progress = data.get("execution_progress")
        self.is_clearing = data.get("is_clearing", False)
        self.current_theta = data.get("current_theta", 0)
        self.current_rho = data.get("current_rho", 0)
        self._speed = data.get("speed", 150)
        self.machine_x = data.get("machine_x", 0.0)
        self.machine_y = data.get("machine_y", 0.0)
        self.x_steps_per_mm = data.get("x_steps_per_mm", 0.0)
        self.y_steps_per_mm = data.get("y_steps_per_mm", 0.0)
        self.gear_ratio = data.get('gear_ratio', 10)
        self.homing = data.get('homing', 0)
        self._current_playlist = data.get("current_playlist")
        self._current_playlist_name = data.get("current_playlist_name")
        self.current_playlist_index = data.get("current_playlist_index")
        self._playlist_mode = data.get("playlist_mode", "loop")
        self._pause_time = data.get("pause_time", 0)
        self._clear_pattern = data.get("clear_pattern", "none")
        self.port = data.get("port", None)
        self.wled_ip = data.get('wled_ip', None)
        # Position sync settings with defaults
        self.position_sync_enabled = data.get("position_sync_enabled", False)
        self.position_sync_mode = data.get("position_sync_mode", "position")
        self.position_sync_throttle_ms = data.get("position_sync_throttle_ms", 50)
        # Localized mode settings with defaults
        self.led_total_leds = data.get("led_total_leds", 60)
        self.led_segment_width = data.get("led_segment_width", 8)

    def save(self):
        """Save the current state to a JSON file."""
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.to_dict(), f)
        except Exception as e:
            print(f"Error saving state to {self.STATE_FILE}: {e}")

    def load(self):
        """Load state from a JSON file. If the file doesn't exist, create it with default values."""
        if not os.path.exists(self.STATE_FILE):
            # File doesn't exist: create one with the current (default) state.
            self.save()
            return
        try:
            with open(self.STATE_FILE, "r") as f:
                data = json.load(f)
            self.from_dict(data)
        except Exception as e:
            print(f"Error loading state from {self.STATE_FILE}: {e}")

    def update_steps_per_mm(self, x_steps, y_steps):
        """Update and save steps per mm values."""
        self.x_steps_per_mm = x_steps
        self.y_steps_per_mm = y_steps
        self.save()

    def reset_state(self):
        """Reset all state variables to their default values."""
        self.__init__()  # Reinitialize the state
        self.save()


# Create a singleton instance that you can import elsewhere:
state = AppState()
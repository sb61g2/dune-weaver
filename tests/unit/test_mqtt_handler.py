"""Tests for Home Assistant MQTT discovery and LED state payloads."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from modules.mqtt.handler import MQTTHandler


def _handler():
    handler = object.__new__(MQTTHandler)
    handler.broker = "mqtt.local"
    handler.discovery_prefix = "homeassistant"
    handler.device_name = "Dune Weaver Mini Pro"
    handler.device_id = "dune_weaver_mini_pro"
    handler.patterns = []
    handler.playlists = []

    handler.running_state_topic = f"{handler.device_id}/state/running"
    handler.serial_state_topic = f"{handler.device_id}/state/serial"
    handler.pattern_select_topic = f"{handler.device_id}/pattern/set"
    handler.playlist_select_topic = f"{handler.device_id}/playlist/set"
    handler.speed_topic = f"{handler.device_id}/speed/set"
    handler.completion_topic = f"{handler.device_id}/state/completion"
    handler.time_remaining_topic = f"{handler.device_id}/state/time_remaining"
    handler.led_power_topic = f"{handler.device_id}/led/power/set"
    handler.led_brightness_topic = f"{handler.device_id}/led/brightness/set"
    handler.led_effect_topic = f"{handler.device_id}/led/effect/set"
    handler.led_speed_topic = f"{handler.device_id}/led/speed/set"
    handler.led_intensity_topic = f"{handler.device_id}/led/intensity/set"
    handler.led_color_topic = f"{handler.device_id}/led/color/set"
    handler.screen_power_topic = f"{handler.device_id}/screen/power/set"
    handler.screen_brightness_topic = f"{handler.device_id}/screen/brightness/set"
    handler.client = MagicMock()
    return handler


def test_discovery_matches_application_speed_range_and_json_light_schema():
    handler = _handler()
    handler._publish_discovery = MagicMock()
    mock_state = SimpleNamespace(
        mqtt_broker="mqtt.local",
        mqtt_enabled=True,
        led_provider="dw_leds",
        led_controller=None,
        screen_controller=None,
    )

    with patch("modules.mqtt.handler.state", mock_state):
        handler.setup_ha_discovery()

    configs = {
        (call.args[0], call.args[1]): call.args[2]
        for call in handler._publish_discovery.call_args_list
    }
    speed = configs[("number", "speed")]
    assert speed["min"] == 10
    assert speed["max"] == 6000
    assert speed["step"] == 10

    led_color = configs[("light", "led_color")]
    assert led_color["schema"] == "json"
    assert led_color["supported_color_modes"] == ["rgb"]
    assert "rgb_state_topic" not in led_color
    assert "rgb_command_topic" not in led_color


def test_led_state_uses_home_assistant_json_light_payload():
    handler = _handler()
    led_controller = MagicMock()
    led_controller.check_status.return_value = {
        "connected": True,
        "power_on": True,
        "colors": ["#00ff00"],
    }
    mock_state = SimpleNamespace(
        led_provider="dw_leds",
        led_controller=led_controller,
    )

    with patch("modules.mqtt.handler.state", mock_state):
        handler._publish_led_state()

    color_topic = f"{handler.device_id}/led/color/state"
    color_calls = [
        call for call in handler.client.publish.call_args_list
        if call.args[0] == color_topic
    ]
    assert len(color_calls) == 1
    assert json.loads(color_calls[0].args[1]) == {
        "state": "ON",
        "color": {"r": 0, "g": 255, "b": 0},
    }
    assert color_calls[0].kwargs["retain"] is True


def test_led_command_accepts_home_assistant_json_light_payload():
    handler = _handler()
    controller = MagicMock()
    led_controller = MagicMock()
    led_controller.get_controller.return_value = controller
    led_controller.check_status.return_value = {
        "connected": True,
        "power_on": True,
        "colors": ["#0a141e"],
    }
    mock_state = SimpleNamespace(
        led_provider="dw_leds",
        led_controller=led_controller,
    )
    message = SimpleNamespace(
        topic=handler.led_color_topic,
        payload=json.dumps({
            "state": "ON",
            "color": {"r": 10, "g": 20, "b": 30},
        }).encode(),
    )

    with patch("modules.mqtt.handler.state", mock_state):
        handler.on_message(None, None, message)

    led_controller.set_power.assert_called_once_with(1)
    controller.set_color.assert_called_once_with(10, 20, 30)

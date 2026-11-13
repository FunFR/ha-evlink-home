"""Constants for the EVlink Home integration."""

DOMAIN = "evlink_home"

STATUSES: dict[str, str] = {
    "Undefined": "undefined",
    "Charging": "charging",
    "PluggedIn": "plugged_in",
    "Unplugged": "unplugged",
    "Joining": "joining",
    "Rebooting": "rebooting",
    "Stopped": "stopped",
    "Paused": "paused",
    "Error": "error",
    "Offline": "offline",
    "SchedulePaused": "schedule_paused",
    "Tripped": "tripped",
    "SuspendedDso": "suspended_dso",
    "SuspendedEv": "suspended_ev",
}
"""State shown for each cloud status of a Wallbox."""

__all__ = (
    "PandoraDeviceTypes",
    "WSMessageType",
    "CommandID",
    "CommandParams",
    "EventType",
    "AlertType",
    "BitStatus",
    "Features",
    "PrimaryEventID",
)

from enum import StrEnum, IntEnum, IntFlag, Flag, auto
from typing import Union, Any


class PandoraDeviceTypes(StrEnum):
    ALARM = "alarm"
    NAV8 = "nav8"
    NAV12 = "nav12"  # @TODO: never before seen


class WSMessageType(StrEnum):
    INITIAL_STATE = "initial-state"
    STATE = "state"
    POINT = "point"
    COMMAND = "command"
    EVENT = "event"
    UPDATE_SETTINGS = "update-settings"


class CommandID(IntEnum):
    """Enumeration of possible services to be executed."""

    # Locking mechanism
    LOCK = 1
    UNLOCK = 2

    # Engine toggles
    START_ENGINE = 4
    STOP_ENGINE = 8

    # Tracking toggle
    ENABLE_TRACKING = 16
    DISABLE_TRACKING = 32

    # Active security toggle
    ENABLE_ACTIVE_SECURITY = 17
    DISABLE_ACTIVE_SECURITY = 18

    # Coolant heater toggle
    TURN_ON_BLOCK_HEATER = 21
    TURN_OFF_BLOCK_HEATER = 22

    # External (timer) channel toggle
    TURN_ON_EXT_CHANNEL = 33
    TURN_OFF_EXT_CHANNEL = 34

    # Service mode toggle
    ENABLE_SERVICE_MODE = 40  # 36?
    DISABLE_SERVICE_MODE = 41  # 37?

    # Status output toggle
    ENABLE_STATUS_OUTPUT = 48
    DISABLE_STATUS_OUTPUT = 49

    # Various commands
    TRIGGER_HORN = 23
    TRIGGER_LIGHT = 24
    TRIGGER_TRUNK = 35
    CHECK = 255

    ERASE_DTC = 57856
    READ_DTC = 57857

    # Additional commands
    ADDITIONAL_COMMAND_1 = 100
    ADDITIONAL_COMMAND_2 = 128

    # Connection toggle
    ENABLE_CONNECTION = 240
    DISABLE_CONNECTION = 15

    # NAV12-specific commands
    NAV12_DISABLE_SERVICE_MODE = 57374
    NAV12_ENABLE_SERVICE_MODE = 57375
    NAV12_TURN_OFF_BLOCK_HEATER = 57353
    NAV12_TURN_ON_BLOCK_HEATER = 57354
    NAV12_RESET_ERRORS = 57408
    NAV12_ENABLE_STATUS_OUTPUT = 57372
    NAV12_DISABLE_STATUS_OUTPUT = 57371

    # Climate-related commands
    CLIMATE_SET_TEMPERATURE = 58624  # Установить температуру
    CLIMATE_SEAT_HEAT_TURN_ON = 58625  # Вкл. подогрев сидений
    CLIMATE_SEAT_HEAT_TURN_OFF = 58626  # Выкл. подогрев сидений
    CLIMATE_SEAT_VENT_TURN_ON = 58627  # Вкл. вентиляцию сидений
    CLIMATE_SEAT_VENT_TURN_OFF = 58628  # Выкл. подогрев сидений
    CLIMATE_GLASS_HEAT_TURN_ON = 58629  # Вкл. подогрев окон и зеркал
    CLIMATE_GLASS_HEAT_TURN_OFF = 58630  # Выкл. подогрев окон и зеркал
    CLIMATE_STEERING_HEAT_TURN_ON = 58631  # Вкл. подогрев руля
    CLIMATE_STEERING_HEAT_TURN_OFF = 58632  # Выкл. подогрев руля
    CLIMATE_AC_TURN_ON = 58633  # Вкл. кондиционер
    CLIMATE_AC_TURN_OFF = 58634  # Выкл. кондиционер
    CLIMATE_SYS_TURN_ON = 58635  # Вкл. климатическую систему
    CLIMATE_SYS_TURN_OFF = 58636  # Выкл. климатическую систему
    CLIMATE_DEFROSTER_TURN_ON = 58637  # Вкл. Defroster
    CLIMATE_DEFROSTER_TURN_OFF = 58638  # Выкл. Defroster
    CLIMATE_MODE_COMFORT = 58639  # Режим комфорт
    CLIMATE_MODE_VENT = 58640  # Режим проветривания салона
    CLIMATE_BATTERY_HEAT_TURN_ON = 58647  # Вкл. подогрев батареи
    CLIMATE_BATTERY_HEAT_TURN_OFF = 58648  # Выкл. подогрев батареи

    # Unknown (untested and incorrectly named) commands
    STAY_HOME_PROPION = 42
    LOW_POWER_MODE = 50
    PS_CALL = 256


class EventType(IntEnum):
    """Enumeration to decode event type."""

    LOCKED = 1
    UNLOCKED = 2
    ALERT = 3
    ENGINE_STARTED = 4
    ENGINE = 5
    GEAR_CHANGE = 6
    SERVICE_MODE = 7
    SETTINGS_CHANGE = 8
    FUEL_REFILL = 9
    COLLISION = 10
    NETWORK_RECEPTION = 11
    EMERGENCY_CALL = 12
    TRUNK_OPEN_ALERT = 17
    VOLTAGE_ALERT = 19
    ACTIVE_SECURITY_ENABLED = 32
    PRE_HEATER_ENABLED = 35


class AlertType(IntEnum):
    """Enumeration to decode alert event type."""

    BATTERY = 1
    EXT_SENSOR_WARNING_ZONE = 2
    EXT_SENSOR_MAIN_ZONE = 3
    CRACK_SENSOR_WARNING_ZONE = 4
    CRACK_SENSOR_MAIN_ZONE = 5
    BRAKE_PEDAL_PRESSED = 6
    HANDBRAKE_ENGAGED = 7
    INCLINE_DETECTED = 8
    MOVEMENT_DETECTED = 9
    ENGINE_IGNITION = 10


class BitStatus(IntFlag):
    """Enumeration to decode `bit_state_1` state parameter."""

    LOCKED = pow(2, 0)
    ALARM = pow(2, 1)
    ENGINE_RUNNING = pow(2, 2)
    IGNITION = pow(2, 3)
    AUTOSTART_ACTIVE = pow(2, 4)  # AutoStart function is currently active
    HANDS_FREE_LOCKING = pow(2, 5)
    HANDS_FREE_UNLOCKING = pow(2, 6)
    GSM_ACTIVE = pow(2, 7)
    GPS_ACTIVE = pow(2, 8)
    TRACKING_ENABLED = pow(2, 9)
    ENGINE_LOCKED = pow(2, 10)
    EXT_SENSOR_ALERT_ZONE = pow(2, 11)
    EXT_SENSOR_MAIN_ZONE = pow(2, 12)
    SENSOR_ALERT_ZONE = pow(2, 13)
    SENSOR_MAIN_ZONE = pow(2, 14)
    AUTOSTART_ENABLED = pow(2, 15)  # AutoStart function is enabled
    INCOMING_SMS_ENABLED = pow(2, 16)  # Incoming SMS messages are allowed
    INCOMING_CALLS_ENABLED = pow(2, 17)  # Incoming calls are allowed
    EXTERIOR_LIGHTS_ACTIVE = pow(2, 18)  # Any exterior lights are active
    SIREN_WARNINGS_ENABLED = pow(2, 19)  # Siren warning signals disabled
    SIREN_SOUND_ENABLED = pow(2, 20)  # All siren signals disabled
    DOOR_DRIVER_OPEN = pow(2, 21)  # Door open: front left
    DOOR_PASSENGER_OPEN = pow(2, 22)  # Door open: front right
    DOOR_BACK_LEFT_OPEN = pow(2, 23)  # Door open: back left
    DOOR_BACK_RIGHT_OPEN = pow(2, 24)  # Door open: back right
    TRUNK_OPEN = pow(2, 25)  # Trunk open
    HOOD_OPEN = pow(2, 26)  # Hood open
    HANDBRAKE_ENGAGED = pow(2, 27)  # Handbrake is engaged
    BRAKES_ENGAGED = pow(2, 28)  # Pedal brake is engaged
    BLOCK_HEATER_ACTIVE = pow(2, 29)  # Pre-start heater active
    ACTIVE_SECURITY_ENABLED = pow(2, 30)  # Active security active
    BLOCK_HEATER_ENABLED = pow(2, 31)  # Pre-start heater function is available
    # ... = pow(2, 32) # ?
    EVACUATION_MODE_ACTIVE = pow(2, 33)  # Evacuation mode active
    SERVICE_MODE_ACTIVE = pow(2, 34)  # Service mode active
    STAY_HOME_ACTIVE = pow(2, 35)  # Stay home mode active
    # (...) = (pow(2, 36), ..., pow(2, 59) # ?
    SECURITY_TAGS_IGNORED = pow(2, 60)  # Ignore security tags
    SECURITY_TAGS_ENFORCED = pow(2, 61)  # Enforce security tags


class Features(Flag):
    ACTIVE_SECURITY = auto()
    AUTO_CHECK = auto()
    AUTO_START = auto()
    BEEPER = auto()
    BLUETOOTH = auto()
    EXT_CHANNEL = auto()
    NETWORK = auto()
    CUSTOM_PHONES = auto()
    EVENTS = auto()
    EXTENDED_PROPERTIES = auto()
    BLOCK_HEATER = auto()
    KEEP_ALIVE = auto()
    LIGHT_TOGGLE = auto()
    NOTIFICATIONS = auto()
    SCHEDULE = auto()
    SENSORS = auto()
    TRACKING = auto()
    TRUNK_TRIGGER = auto()
    NAV = auto()

    @classmethod
    def from_dict(cls, features_dict: dict[str, Union[bool, int]]):
        result = None
        for key, flag in {
            "active_security": cls.ACTIVE_SECURITY,
            "auto_check": cls.AUTO_CHECK,
            "autostart": cls.AUTO_START,
            "beep": cls.BEEPER,
            "bluetooth": cls.BLUETOOTH,
            "channel": cls.EXT_CHANNEL,
            "connection": cls.NETWORK,
            "custom_phones": cls.CUSTOM_PHONES,
            "events": cls.EVENTS,
            "extend_props": cls.EXTENDED_PROPERTIES,
            "heater": cls.BLOCK_HEATER,
            "keep_alive": cls.KEEP_ALIVE,
            "light": cls.LIGHT_TOGGLE,
            "notification": cls.NOTIFICATIONS,
            "schedule": cls.SCHEDULE,
            "sensors": cls.SENSORS,
            "tracking": cls.TRACKING,
            "trunk": cls.TRUNK_TRIGGER,
            "nav": cls.NAV,
        }.items():
            if key in features_dict:
                result = flag if result is None else result | flag

        return result


class PrimaryEventID(IntEnum):
    UNKNOWN = 0
    LOCKING_ENABLED = 1
    LOCKING_DISABLED = 2
    ALERT = 3
    ENGINE_STARTED = 4
    ENGINE_STOPPED = 5
    ENGINE_LOCKED = 6
    SERVICE_MODE_ENABLED = 7
    SETTINGS_CHANGED = 8
    REFUEL = 9
    COLLISION = 10
    GSM_CONNECTION = 11
    EMERGENCY_CALL = 12
    FAILED_START_ATTEMPT = 13
    TRACKING_ENABLED = 14
    TRACKING_DISABLED = 15
    SYSTEM_POWER_LOSS = 16
    SECURE_TRUNK_OPEN = 17
    FACTORY_TESTING = 18
    POWER_DIP = 19
    CHECK_RECEIVED = 20
    SYSTEM_LOGIN = 29
    ACTIVE_SECURITY_ENABLED = 32
    ACTIVE_SECURITY_DISABLED = 33
    ACTIVE_SECURITY_ALERT = 34
    BLOCK_HEATER_ENABLED = 35
    BLOCK_HEATER_DISABLED = 36
    ROUGH_ROAD_CONDITIONS = 37
    DRIVING = 38
    ENGINE_RUNNING_PROLONGATION = 40
    SERVICE_MODE_DISABLED = 41
    GSM_CHANNEL_ENABLED = 42
    GSM_CHANNEL_DISABLED = 43
    NAV_11_STATUS = 48
    DTC_READ_REQUEST = 166
    DTC_READ_ERROR = 167
    DTC_READ_ACTIVE = 168
    DTC_ERASE_REQUEST = 169
    DTC_ERASE_ACTIVE = 170
    SYSTEM_MESSAGE = 176
    ECO_MODE_ENABLED = 177
    ECO_MODE_DISABLED = 178
    TIRE_PRESSURE_LOW = 179
    BLUETOOTH_STATUS = 220
    TAG_REQUIREMENT_ENABLED = 230
    TAG_REQUIREMENT_DISABLED = 231
    TAG_POLLING_ENABLED = 232
    TAG_POLLING_DISABLED = 233
    POINT = 250

    @classmethod
    def _missing_(cls, value: object) -> Any:
        return cls.UNKNOWN


class CommandParams(StrEnum):
    CLIMATE_TEMP = "climate_temp"

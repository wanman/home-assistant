"""
Zwave platform that handles simple door locks.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/lock.zwave/
"""
# Because we do not compile openzwave on CI
# pylint: disable=import-error
import logging
from os import path

import voluptuous as vol

from homeassistant.components.lock import DOMAIN, LockDevice
from homeassistant.components import zwave
from homeassistant.config import load_yaml_config_file
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

ATTR_NOTIFICATION = 'notification'
ATTR_LOCK_STATUS = 'lock_status'
ATTR_CODE_SLOT = 'code_slot'
ATTR_USERCODE = 'usercode'
CONFIG_ADVANCED = 'Advanced'

SERVICE_SET_USERCODE = 'set_usercode'
SERVICE_GET_USERCODE = 'get_usercode'
SERVICE_CLEAR_USERCODE = 'clear_usercode'

POLYCONTROL = 0x10E
DANALOCK_V2_BTZE = 0x2
POLYCONTROL_DANALOCK_V2_BTZE_LOCK = (POLYCONTROL, DANALOCK_V2_BTZE)
WORKAROUND_V2BTZE = 'v2btze'

DEVICE_MAPPINGS = {
    POLYCONTROL_DANALOCK_V2_BTZE_LOCK: WORKAROUND_V2BTZE
}

LOCK_NOTIFICATION = {
    '1': 'Manual Lock',
    '2': 'Manual Unlock',
    '3': 'RF Lock',
    '4': 'RF Unlock',
    '5': 'Keypad Lock',
    '6': 'Keypad Unlock',
    '11': 'Lock Jammed',
    '254': 'Unknown Event'
}

LOCK_ALARM_TYPE = {
    '9': 'Deadbolt Jammed',
    '18': 'Locked with Keypad by user ',
    '19': 'Unlocked with Keypad by user ',
    '21': 'Manually Locked by',
    '22': 'Manually Unlocked by Key or Inside thumb turn',
    '24': 'Locked by RF',
    '25': 'Unlocked by RF',
    '27': 'Auto re-lock',
    '33': 'User deleted: ',
    '112': 'Master code changed or User added: ',
    '113': 'Duplicate Pin-code: ',
    '130': 'RF module, power restored',
    '161': 'Tamper Alarm: ',
    '167': 'Low Battery',
    '168': 'Critical Battery Level',
    '169': 'Battery too low to operate'
}

MANUAL_LOCK_ALARM_LEVEL = {
    '1': 'Key Cylinder or Inside thumb turn',
    '2': 'Touch function (lock and leave)'
}

TAMPER_ALARM_LEVEL = {
    '1': 'Too many keypresses',
    '2': 'Cover removed'
}

LOCK_STATUS = {
    '1': True,
    '2': False,
    '3': True,
    '4': False,
    '5': True,
    '6': False,
    '9': False,
    '18': True,
    '19': False,
    '21': True,
    '22': False,
    '24': True,
    '25': False,
    '27': True
}

ALARM_TYPE_STD = [
    '18',
    '19',
    '33',
    '112',
    '113'
]

SET_USERCODE_SCHEMA = vol.Schema({
    vol.Required(zwave.const.ATTR_NODE_ID): vol.Coerce(int),
    vol.Required(ATTR_CODE_SLOT): vol.Coerce(int),
    vol.Required(ATTR_USERCODE): cv.string,
})

GET_USERCODE_SCHEMA = vol.Schema({
    vol.Required(zwave.const.ATTR_NODE_ID): vol.Coerce(int),
    vol.Required(ATTR_CODE_SLOT): vol.Coerce(int),
})

CLEAR_USERCODE_SCHEMA = vol.Schema({
    vol.Required(zwave.const.ATTR_NODE_ID): vol.Coerce(int),
    vol.Required(ATTR_CODE_SLOT): vol.Coerce(int),
})


# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Find and return Z-Wave locks."""
    if discovery_info is None or zwave.NETWORK is None:
        return

    node = zwave.NETWORK.nodes[discovery_info[zwave.const.ATTR_NODE_ID]]
    value = node.values[discovery_info[zwave.const.ATTR_VALUE_ID]]

    descriptions = load_yaml_config_file(
        path.join(path.dirname(__file__), 'services.yaml'))

    def set_usercode(service):
        """Set the usercode to index X on the lock."""
        node_id = service.data.get(zwave.const.ATTR_NODE_ID)
        lock_node = zwave.NETWORK.nodes[node_id]
        code_slot = service.data.get(ATTR_CODE_SLOT)
        usercode = service.data.get(ATTR_USERCODE)

        for value in lock_node.get_values(
                class_id=zwave.const.COMMAND_CLASS_USER_CODE).values():
            if value.index != code_slot:
                continue
            if len(str(usercode)) > 4:
                _LOGGER.error('Invalid code provided: (%s)'
                              ' usercode must %s or less digits',
                              usercode, len(value.data))
            value.data = str(usercode)
            break

    def get_usercode(service):
        """Get a usercode at index X on the lock."""
        node_id = service.data.get(zwave.const.ATTR_NODE_ID)
        lock_node = zwave.NETWORK.nodes[node_id]
        code_slot = service.data.get(ATTR_CODE_SLOT)

        for value in lock_node.get_values(
                class_id=zwave.const.COMMAND_CLASS_USER_CODE).values():
            if value.index != code_slot:
                continue
            _LOGGER.info('Usercode at slot %s is: %s', value.index, value.data)
            break

    def clear_usercode(service):
        """Set usercode to slot X on the lock."""
        node_id = service.data.get(zwave.const.ATTR_NODE_ID)
        lock_node = zwave.NETWORK.nodes[node_id]
        code_slot = service.data.get(ATTR_CODE_SLOT)
        data = ''

        for value in lock_node.get_values(
                class_id=zwave.const.COMMAND_CLASS_USER_CODE).values():
            if value.index != code_slot:
                continue
            for i in range(len(value.data)):
                data += '\0'
                i += 1
            _LOGGER.debug('Data to clear lock: %s', data)
            value.data = data
            _LOGGER.info('Usercode at slot %s is cleared', value.index)
            break

    if value.command_class != zwave.const.COMMAND_CLASS_DOOR_LOCK:
        return
    if value.type != zwave.const.TYPE_BOOL:
        return
    if value.genre != zwave.const.GENRE_USER:
        return
    if node.has_command_class(zwave.const.COMMAND_CLASS_USER_CODE):
        hass.services.register(DOMAIN,
                               SERVICE_SET_USERCODE,
                               set_usercode,
                               descriptions.get(SERVICE_SET_USERCODE),
                               schema=SET_USERCODE_SCHEMA)
        hass.services.register(DOMAIN,
                               SERVICE_GET_USERCODE,
                               get_usercode,
                               descriptions.get(SERVICE_GET_USERCODE),
                               schema=GET_USERCODE_SCHEMA)
        hass.services.register(DOMAIN,
                               SERVICE_CLEAR_USERCODE,
                               clear_usercode,
                               descriptions.get(SERVICE_CLEAR_USERCODE),
                               schema=CLEAR_USERCODE_SCHEMA)
    value.set_change_verified(False)
    add_devices([ZwaveLock(value)])


class ZwaveLock(zwave.ZWaveDeviceEntity, LockDevice):
    """Representation of a Z-Wave Lock."""

    def __init__(self, value):
        """Initialize the Z-Wave lock device."""
        zwave.ZWaveDeviceEntity.__init__(self, value, DOMAIN)
        self._node = value.node
        self._state = None
        self._notification = None
        self._lock_status = None
        self._v2btze = None

        # Enable appropriate workaround flags for our device
        # Make sure that we have values for the key before converting to int
        if (value.node.manufacturer_id.strip() and
                value.node.product_id.strip()):
            specific_sensor_key = (int(value.node.manufacturer_id, 16),
                                   int(value.node.product_id, 16))
            if specific_sensor_key in DEVICE_MAPPINGS:
                if DEVICE_MAPPINGS[specific_sensor_key] == WORKAROUND_V2BTZE:
                    self._v2btze = 1
                    _LOGGER.debug("Polycontrol Danalock v2 BTZE "
                                  "workaround enabled")
        self.update_properties()

    def update_properties(self):
        """Callback on data changes for node values."""
        self._state = self._value.data
        _LOGGER.debug('Lock state set from Bool value and'
                      ' is %s', self._state)
        notification_data = self.get_value(class_id=zwave.const
                                           .COMMAND_CLASS_ALARM,
                                           label=['Access Control'],
                                           member='data')
        if notification_data:
            self._notification = LOCK_NOTIFICATION.get(str(notification_data))
        if self._v2btze:
            advanced_config = self.get_value(class_id=zwave.const
                                             .COMMAND_CLASS_CONFIGURATION,
                                             index=12,
                                             data=CONFIG_ADVANCED,
                                             member='data')
            if advanced_config:
                self._state = LOCK_STATUS.get(str(notification_data))
                _LOGGER.debug('Lock state set from Access Control '
                              'value and is %s, get=%s',
                              str(notification_data),
                              self.state)

        alarm_type = self.get_value(class_id=zwave.const
                                    .COMMAND_CLASS_ALARM,
                                    label=['Alarm Type'], member='data')
        _LOGGER.debug('Lock alarm_type is %s', str(alarm_type))
        alarm_level = self.get_value(class_id=zwave.const
                                     .COMMAND_CLASS_ALARM,
                                     label=['Alarm Level'], member='data')
        _LOGGER.debug('Lock alarm_level is %s', str(alarm_level))
        if not alarm_type:
            return
        if alarm_type is 21:
            self._lock_status = '{}{}'.format(
                LOCK_ALARM_TYPE.get(str(alarm_type)),
                MANUAL_LOCK_ALARM_LEVEL.get(str(alarm_level)))
        if alarm_type in ALARM_TYPE_STD:
            self._lock_status = '{}{}'.format(
                LOCK_ALARM_TYPE.get(str(alarm_type)), str(alarm_level))
            return
        if alarm_type is 161:
            self._lock_status = '{}{}'.format(
                LOCK_ALARM_TYPE.get(str(alarm_type)),
                TAMPER_ALARM_LEVEL.get(str(alarm_level)))
            return
        if alarm_type != 0:
            self._lock_status = LOCK_ALARM_TYPE.get(str(alarm_type))
            return

    @property
    def is_locked(self):
        """Return true if device is locked."""
        return self._state

    def lock(self, **kwargs):
        """Lock the device."""
        self._value.data = True

    def unlock(self, **kwargs):
        """Unlock the device."""
        self._value.data = False

    @property
    def device_state_attributes(self):
        """Return the device specific state attributes."""
        data = super().device_state_attributes
        if self._notification:
            data[ATTR_NOTIFICATION] = self._notification
        if self._lock_status:
            data[ATTR_LOCK_STATUS] = self._lock_status
        return data

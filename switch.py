from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
import logging

_LOGGER = logging.getLogger(__name__)

# Sub-device switches (plugs, chargers, heaters)
SWITCH_MAP = {
    "PlugInfoList": {
        "status": ("PlugStatus", "Switch"),
    },
    "ChargerInfoList": {
        "status": ("ChargerStatus", "Switch"),
    },
    "HotInfoList": {
        "status": ("HotStatus", "Switch"),
    }
}

# Inverter-level hardware switches controlled via register writes.
# Register addresses confirmed from cloud API (setDeviceParam startAddr).
INVERTER_SWITCH_DEFS = [
    {
        "key": "ac_offgrid",
        "name": "AC Off-Grid Mode",
        "register": 123,
        "state_source": ("SSumInfoList", "ACRelayStatus"),
    },
    {
        "key": "max_feedin",
        "name": "Max Feed-In Power",
        "register": 124,
        "state_source": ("SSumInfoList", "MaxFeedPowerFlag"),
    },
    {
        "key": "discharge",
        "name": "Battery Discharge",
        "register": 125,
        "state_source": ("SSumInfoList", "BasicDisChargeEnable"),
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    device_sn = config_entry.data["device_sn"]

    switches = []

    # Sub-device switches (plugs, chargers, heaters)
    for data_type, field_map in SWITCH_MAP.items():
        raw_data = coordinator.data.get(data_type)
        if not raw_data:
            continue

        if isinstance(raw_data, list):
            for item in raw_data:
                sn = item.get("PlugSN") or item.get("ChargerSN") or item.get("HotSN")
                if not sn:
                    continue

                for key, (path, name) in field_map.items():
                    if item.get(path) is None:
                        continue
                    attr = {
                        "dev_addr": item.get("DevAddr"),
                        # DevType from device data — fallback to 200 (plug) if absent
                        "dev_type": item.get("DevType", 200),
                        "is_third_party": item.get("lsThirdParty", 0),
                        "fans_dev_type": item.get("FansDevType"),
                        "is_interconnect": item.get("IsInterconnect", 0),
                    }
                    switches.append(
                        AECCSwitch(coordinator, device_sn, item, data_type, key, path, name, attr)
                    )

    # Inverter-level hardware switches
    for switch_def in INVERTER_SWITCH_DEFS:
        switches.append(AECCInverterSwitch(coordinator, device_sn, switch_def))

    async_add_entities(switches)


class AECCSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, device_sn, item, data_type, key, path, name, attr):
        super().__init__(coordinator)
        self._item = item
        self._data_type = data_type
        self._device_sn = device_sn
        self._key = key
        self._path = path
        self._name = name
        self._attr = attr
        self._unique_id = self._generate_unique_id(device_sn, item)

    def _generate_unique_id(self, device_sn, item):
        sn = item.get("PlugSN") or item.get("ChargerSN") or item.get("HotSN")
        if sn:
            return f"aecc_{device_sn}_{self._data_type.lower()}_{sn}_{self._key}"
        return f"aecc_{device_sn}_{self._data_type.lower()}_{self._key}"

    def _get_current_item(self):
        """Read fresh item data from the coordinator instead of stale snapshot."""
        raw = self.coordinator.data.get(self._data_type) if self.coordinator.data else None
        if isinstance(raw, list):
            own_sn = (self._item.get("PlugSN") or
                      self._item.get("ChargerSN") or
                      self._item.get("HotSN"))
            for item in raw:
                sn = item.get("PlugSN") or item.get("ChargerSN") or item.get("HotSN")
                if sn == own_sn:
                    return item
        return self._item

    @property
    def name(self):
        sn = self._item.get("PlugSN") or self._item.get("ChargerSN") or self._item.get("HotSN")
        if sn:
            return f"{sn} {self._key.replace('_', ' ').title()}"
        return f"{self._key.replace('_', ' ').title()}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def assumed_state(self) -> bool:
        return False

    @property
    def is_on(self):
        val = self._get_current_item().get(self._path)
        return int(val) == 1 if val is not None else False

    async def async_turn_on(self, **kwargs):
        _LOGGER.info(f"Turning on: {self.name}")
        await self.coordinator.client.turn_on_switch(self._attr)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        _LOGGER.info(f"Turning off: {self.name}")
        await self.coordinator.client.turn_off_switch(self._attr)
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_sn)},
            "name": self._device_sn,
            "model": "Smart Load",
            "manufacturer": "Allwei",
        }

    @property
    def extra_state_attributes(self):
        return self._attr


class AECCInverterSwitch(CoordinatorEntity, SwitchEntity):
    """Inverter-level switch controlled via hardware register writes."""

    def __init__(self, coordinator, device_sn, switch_def):
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._key = switch_def["key"]
        self._switch_name = switch_def["name"]
        self._register = switch_def["register"]
        self._state_source = switch_def["state_source"]
        # Optimistic state: tracks last sent command until coordinator confirms
        self._optimistic_state: bool = False

    @property
    def unique_id(self):
        return f"aecc_{self._device_sn}_inverter_{self._key}"

    @property
    def name(self):
        return self._switch_name

    @property
    def assumed_state(self) -> bool:
        return False

    @property
    def is_on(self) -> bool:
        # Prefer live coordinator data over optimistic state
        data_type, field = self._state_source
        raw = self.coordinator.data.get(data_type) if self.coordinator.data else None
        if isinstance(raw, dict):
            val = raw.get(field)
            if val is not None:
                try:
                    return int(val) == 1
                except (ValueError, TypeError):
                    pass
        # Fall back to last known optimistic state (always a bool, never None)
        return self._optimistic_state

    async def async_turn_on(self, **kwargs):
        _LOGGER.info(f"Inverter switch ON: {self._switch_name} (register {self._register})")
        success = await self.coordinator.client.send_hardware_param(self._register, 1)
        if success:
            self._optimistic_state = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        _LOGGER.info(f"Inverter switch OFF: {self._switch_name} (register {self._register})")
        success = await self.coordinator.client.send_hardware_param(self._register, 0)
        if success:
            self._optimistic_state = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        return {
            "register_address": self._register,
            "state_field": f"{self._state_source[0]}.{self._state_source[1]}",
        }

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._device_sn)},
            "name": self._device_sn,
            "model": "Inverter",
            "manufacturer": "Allwei",
        }

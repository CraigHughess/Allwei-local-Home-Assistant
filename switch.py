from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, STATE_ON
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
# Register addresses confirmed from cloud API analysis (setDeviceParam startAddr).
# State fields are best-effort reads from EnergyParameter response; the switch
# falls back to optimistic tracking if the field is absent in the local response.
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
                    value = item.get(path)
                    if value is None:
                        continue
                    attr = {
                        "dev_addr": item.get("DevAddr"),
                        "is_third_party": item.get("lsThirdParty"),
                        "fans_dev_type": item.get("FansDevType"),
                        "is_interconnect": item.get("IsInterconnect"),
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
        self._unique_id = self._generate_unique_id(device_sn, item)
        self._attr = attr
        _LOGGER.info(f"self._state: {self._item.get(self._path)}")
        self._state= self._item.get(self._path)

    def _generate_unique_id(self, device_sn, item):
        sn = item.get("PlugSN") or item.get("ChargerSN") or item.get("HotSN")
        if sn:
            return f"aecc_{device_sn}_{self._data_type.lower()}_{sn}_{self._key}"
        else:
            return f"aecc_{device_sn}_{self._data_type.lower()}_{self._key}"
    @property
    def name(self):
        sn = self._item.get("PlugSN") or self._item.get("ChargerSN") or self._item.get("HotSN")
        if sn:
            return f"{sn} {self._key.replace('_', ' ').title()}"
        else:
            return f"{self._key.replace('_', ' ').title()}"

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def is_on(self):
          return  True if self._state==1 else False
  # PlugStatus: 1 表示开启

    async def async_turn_on(self, **kwargs):
        """发送打开命令"""
        sn = self._item.get("PlugSN") or self._item.get("ChargerSN") or self._item.get("HotSN")
        if sn:
            _LOGGER.info(f"Turning on switch: {sn}")
            # 假设 client 提供了 turn_on_plug 方法
            await self.coordinator.client.turn_on_switch(self._attr)
            self._state = 1

            await self.coordinator.async_request_refresh()
    async def async_turn_off(self, **kwargs):
        """发送关闭命令"""
        sn = self._item.get("PlugSN") or self._item.get("ChargerSN") or self._item.get("HotSN")
        if sn:
            _LOGGER.info(f"Turning off switch: {sn}")
            await self.coordinator.client.turn_off_switch(self._attr)
            self._state = 0
            await self.coordinator.async_request_refresh()

    @property
    def device_info(self):
        # sn = self._item.get("PlugSN") or self._item.get("ChargerSN") or self._item.get("HotSN")
        return {
            "identifiers": {(DOMAIN, self._device_sn)},
            "name": self._device_sn,
            "model": "smart load",
            "manufacturer": "AECC",
        }
    @property
    def extra_state_attributes(self) :
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
        self._optimistic_state = None

    @property
    def unique_id(self):
        return f"aecc_{self._device_sn}_inverter_{self._key}"

    @property
    def name(self):
        return self._switch_name

    @property
    def is_on(self):
        data_type, field = self._state_source
        raw = self.coordinator.data.get(data_type) if self.coordinator.data else None
        if isinstance(raw, dict):
            val = raw.get(field)
            if val is not None:
                try:
                    return int(val) == 1
                except (ValueError, TypeError):
                    pass
        return self._optimistic_state

    async def async_turn_on(self, **kwargs):
        success = await self.coordinator.client.send_hardware_param(self._register, 1)
        if success:
            self._optimistic_state = True
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        success = await self.coordinator.client.send_hardware_param(self._register, 0)
        if success:
            self._optimistic_state = False
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
            "manufacturer": "AECC",
        }
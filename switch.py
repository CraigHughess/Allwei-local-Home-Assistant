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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    device_sn = config_entry.data["device_sn"]

    switches = []

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
                        "dev_type": item.get("DevType", 200),
                        "is_third_party": item.get("lsThirdParty", 0),
                        "fans_dev_type": item.get("FansDevType"),
                        "is_interconnect": item.get("IsInterconnect", 0),
                    }
                    switches.append(
                        AECCSwitch(coordinator, device_sn, item, data_type, key, path, name, attr)
                    )

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

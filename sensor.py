import logging
from typing import Mapping, Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    UnitOfPower,
    PERCENTAGE,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# 用于映射单位
from homeassistant.const import (
    UnitOfPower,
    PERCENTAGE,
    UnitOfTemperature,
)

SENSOR_MAP = {
    "SSumInfoList": {
        "total_active_power": ("MeterTotalActivePower", UnitOfPower.WATT),
        "pv_power": ("TotalPVPower", UnitOfPower.WATT),
        "pv_charge_power": ("TotalPVChargePower", UnitOfPower.WATT),
        "ac_charge_power": ("TotalACChargePower", UnitOfPower.WATT),
        "smart_load_power": ("TotalSmartLoadElectricalPower", UnitOfPower.WATT),
        "battery_soc": ("AverageBatteryAverageSOC", PERCENTAGE),
        "battery_output_power": ("TotalBatteryOutputPower", UnitOfPower.WATT),
        "grid_output_power": ("TotalGridOutputPower", UnitOfPower.WATT),
        "backup_power": ("TotalBackUpPower", UnitOfPower.WATT),
    },
    "PlugInfoList": {
        "active_power": ("PlugActvePower", UnitOfPower.WATT),
    },
    "ChargerInfoList": {
        "connector_1_status": ("Connector1Status", None),
        "connector_1_power": ("Connector1Power", UnitOfPower.WATT),
        "connector_2_status": ("Connector2Status", None),
        "connector_2_power": ("Connector2Power", UnitOfPower.WATT),
    },
    "HotInfoList": {
        "active_power": ("HotActvePower", UnitOfPower.WATT),
        "max_power": ("HotActvePowerMAX", UnitOfPower.WATT),
        "temperature": ("HotTEMP", UnitOfTemperature.CELSIUS),
        "max_temperature": ("HotTEMPMAX", UnitOfTemperature.CELSIUS),
    }
}


async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    device_sn = config_entry.data["device_sn"]

    sensors = []
    # 遍历map
    for data_type, field_map in SENSOR_MAP.items():
        raw_data = coordinator.data.get(data_type)
        if not raw_data:
            continue  # 数据不存在，跳过

        if isinstance(raw_data, list):
            # 遍历各个设备数组
            for item in raw_data:
                sn = item.get("PlugSN") or item.get("ChargerSN") or item.get("HotSN")
                if not sn:
                    continue  # 缺少 SN，跳过

                for key, (path, unit) in field_map.items():
                    value = item.get(path)
                    if value is None:
                        continue  # 字段缺失，跳过

                    unique_id = f"{device_sn}_{data_type.lower()}_{sn}_{key}"


                    sensors.append(
                        AECCSensor(coordinator, device_sn, item, data_type, key, path, unit)
                    )
        else:
            # 非列表结构（如 SSumInfoList）
            item = raw_data
            for key, (path, unit) in field_map.items():
                value = item.get(path)
                if value is None:
                    continue  # 字段缺失，跳过

                unique_id = f"{device_sn}_{data_type.lower()}_{key}"
                sensors.append(
                    AECCSensor(coordinator, device_sn, item, data_type, key, path, unit)
                )

    async_add_entities(sensors)


class AECCSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, device_sn, item, data_type, key, path, unit):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._item = item
        self._data_type = data_type
        self._device_sn = device_sn
        self._key = key
        self._path = path
        self._unit = unit
        self._unique_id = self._generate_unique_id(device_sn, item)

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
    def native_value(self):
        value = self._item.get(self._path)
        _LOGGER.debug(f"解析的key{self._path} value：{value}")
        if self._data_type == "HotInfoList" and self._path in ["HotTEMP", "HotTEMPMAX"]:
            try:

                return float(value) / 10 if value is not None else 0.0
            except (ValueError, TypeError):
                return 0.0

        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        else:
            return 0.0

    @property
    def native_unit_of_measurement(self):
        return self._unit

    @property
    def device_info(self):
        model_map = {
            "SSumInfoList": "System Summary",
            "PlugInfoList": "Smart Plug",
            "ChargerInfoList": "EV Charger",
            "HotInfoList": "Heater"
        }
        model = model_map.get(self._data_type, self._data_type)

        return {
            "identifiers": {(DOMAIN, self._device_sn)},
            "name": self._device_sn,
            "model": model,
            "manufacturer": "AECC",
        }


# Allwei Local — Home Assistant Integration

> Local-first Home Assistant integration for **Allwei** energy storage systems (ESS).  
> No cloud. No subscription. Direct TCP communication over your local network.

![Allwei Logo](www/local/aecc_local_plugin/logo.png)

---

## Overview

This integration connects Home Assistant **directly** to your Allwei inverter/storage gateway over your local LAN — without routing data through any cloud server. It uses the same JSON-over-TCP protocol the Allwei gateway exposes on port 8899 and discovers devices automatically via **mDNS/Zeroconf** (no manual IP entry required).

### What you get

| Category | Entities |
|---|---|
| **System Summary** | Total active power, PV power, PV charge power, AC charge power, smart load power, battery SOC, battery output power, grid output power, backup power |
| **Smart Plugs** | Active power per plug, on/off switch |
| **EV Charger** | Connector 1 & 2 status, connector 1 & 2 charging power, on/off switch |
| **Heater / Hot Water** | Active power, max power, temperature, max temperature, on/off switch |
| **Inverter Controls** | AC Off-Grid relay, Max Feed-In Power flag, Battery Discharge enable |

All values update every **10 seconds** directly from the device — no polling of a cloud API.

---

## Requirements

- Home Assistant **2023.4** or newer
- Allwei inverter/gateway on the **same local network** as your HA instance
- The gateway must advertise itself via mDNS (`_http._tcp.local.`) — this is the default for all Allwei gateways with firmware supporting local API

---

## Installation

### Option A — HACS (recommended)

1. Open **HACS** → **Integrations** → click the three-dot menu → **Custom repositories**
2. Add this repository URL and select category **Integration**
3. Search for **Allwei Local** and click **Download**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** → search **Allwei Local**

### Option B — Manual

1. Download or clone this repository
2. Copy the entire `aecc_local_plugin` folder into your HA config directory:
   ```
   config/
   └── custom_components/
       └── aecc_local_plugin/   ← copy here
   ```
3. Copy the `www/local/aecc_local_plugin/` folder into your HA `www` directory:
   ```
   config/
   └── www/
       └── local/
           └── aecc_local_plugin/
               └── logo.png
   ```
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** → search **Allwei Local**

---

## Setup

### Automatic discovery (recommended)

If your Allwei gateway is on the same network, Home Assistant will **automatically discover** it and show a notification under **Settings → Devices & Services**. Click **Configure** and confirm the device — done.

The notification shows:
- Device serial number (`s_sn`)
- Local IP address (`s_ip`)
- Device type (inverter, charger, battery, etc.)

### Manual setup (if auto-discovery fails)

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **Allwei Local**
3. Enter the gateway IP and port (default: `8899`)

---

## Entities Reference

### Sensors

#### System Summary

| Entity | Unit | Description |
|---|---|---|
| `Total Active Power` | W | Combined grid meter active power |
| `PV Power` | W | Total PV generation |
| `PV Charge Power` | W | PV energy going to battery |
| `AC Charge Power` | W | Grid energy going to battery |
| `Smart Load Power` | W | Total smart load consumption |
| `Battery SOC` | % | Average battery state of charge |
| `Battery Output Power` | W | Battery discharge power |
| `Grid Output Power` | W | Power exported to / imported from grid |
| `Backup Power` | W | Backup output power |

#### Per-Device (Smart Plug / EV Charger / Heater)

Entities are created dynamically for each sub-device discovered in the `EnergyParameter` response. Each device gets its own entity with the device serial number as prefix.

### Switches

#### Sub-device Switches
| Switch | Description |
|---|---|
| `<PlugSN> Status` | Turn smart plug on/off |
| `<ChargerSN> Status` | Enable/disable EV charger |
| `<HotSN> Status` | Enable/disable heater / hot water controller |

#### Inverter Hardware Switches
These switches write directly to inverter hardware registers over the local TCP connection — the same registers the Allwei cloud app controls remotely.

| Switch | Register | Description |
|---|---|---|
| `AC Off-Grid Mode` | 123 | Enable/disable the off-grid AC output relay |
| `Max Feed-In Power` | 124 | Activate maximum feed-in power flag |
| `Battery Discharge` | 125 | Allow/block battery discharge globally |

> **Note on state display:** The inverter switches use optimistic state tracking if the `EnergyParameter` response does not yet include the corresponding status field (`ACRelayStatus`, `MaxFeedPowerFlag`, `BasicDisChargeEnable`). Once toggled, the displayed state reflects what was sent — it updates to the real device state on the next polling cycle.

---

## How it works

```
Home Assistant
     │  JSON over TCP (LAN, port 8899)
     ▼
Allwei Gateway (auto-discovered via mDNS)
     │  RS485 / internal bus
     ▼
Inverter · Battery · Smart Plugs · EV Charger · Heater
```

1. **Discovery** — the gateway broadcasts an mDNS service record (`_http._tcp.local.`) with device metadata (SN, IP, type).
2. **Data polling** — every 10 s the integration sends `{"Get": "EnergyParameter"}` over a persistent TCP connection and parses the JSON response.
3. **Control** — sub-device on/off uses `{"Set": "SubDeviceControl"}`. Inverter-level switches use `{"Set": "InverterParam"}` with the hardware register address.
4. **Reconnect** — if the TCP connection drops, the integration reconnects automatically before the next data fetch.

---

## Troubleshooting

**Device not discovered automatically**
- Confirm the gateway and HA are on the same subnet (mDNS does not cross subnet boundaries)
- Check that no firewall blocks multicast traffic
- Try a manual setup with the gateway IP instead

**Entities show "Unavailable"**
- Open HA logs and filter for `aecc_local_plugin`
- The raw TCP response is logged at `INFO` level — look for `Received raw response:` to see exactly what the gateway returns
- Verify the gateway port (default `8899`) is reachable: `nc -zv <gateway-ip> 8899`

**Inverter switches show unknown state**
- The gateway may not yet include `ACRelayStatus` / `MaxFeedPowerFlag` / `BasicDisChargeEnable` in the `EnergyParameter` response
- Toggle the switch once — it will track state optimistically until the next full response cycle
- The actual register address is shown in the entity's extra attributes for cross-referencing with the Allwei register map

**Sensor values are 0.0 instead of missing**
- This is by design for numeric sensors when the field is present but null — edit `sensor.py:138` to return `None` instead if you prefer HA to show "Unavailable"

---

## Supported Devices

| Device type code | Device |
|---|---|
| 1 – 49 | Inverter / Off-grid / Storage unit |
| 50 – 54 | Energy meter |
| 55 – 79 | EV charger |
| 80 – 109 | Battery module |
| 110 – 139 | Smart plug |
| 141 – 145 | AC coupler |
| 150 – 155 | Hot water / heater controller |
| 156 – 160 | Relay |

---

## Version history

| Version | Changes |
|---|---|
| 1.1.0 | Added inverter hardware switches (AC relay, feed-in, discharge) |
| 1.0.0 | Initial release — auto-discovery, sensors, sub-device switches |

---

## Contributing

Pull requests are welcome. For major changes, please open an issue first.

When adding new sensor fields:
1. Add the field name and unit to `SENSOR_MAP` in `sensor.py`
2. To find available field names, enable `INFO` logging and run `dump` — the raw `EnergyParameter` response contains all fields the gateway exposes

---

## License

MIT

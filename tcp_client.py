import asyncio
import logging
import json
from typing import Optional, Dict, Any, Tuple
from .tcp_manager import TCPClientManager

_LOGGER = logging.getLogger(__name__)

class AECCDeviceClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.tcp_manager = TCPClientManager.get_instance(host, port, timeout=5)
        self.serial_number = 1
        # Serializes all send+receive cycles so fetch_data and command methods
        # never read from the same StreamReader concurrently.
        self._cmd_lock = asyncio.Lock()

    async def connect(self):
        await self.tcp_manager.connect()

    async def fetch_data(self) -> Optional[Dict[str, Any]]:
        async with self._cmd_lock:
            try:
                _, writer = await self.tcp_manager.get_reader_writer()

                request = {
                    "Get": "EnergyParameter",
                    "SerialNumber": self.serial_number,
                    "CommandSource": "Web"
                }

                writer.write(json.dumps(request).encode() + b'\n')
                await writer.drain()
                _LOGGER.info(f"Sent request: {request}")

                buffer = b''
                while True:
                    reader, _ = await self.tcp_manager.get_reader_writer()
                    chunk = await reader.read(4096)
                    if not chunk:
                        raise ConnectionResetError("Device closed the connection")
                    buffer += chunk
                    try:
                        json_data = json.loads(buffer.decode('utf-8'))
                        _LOGGER.info(f"Received raw response: {json_data}")
                        self.serial_number += 1
                        return json_data
                    except json.JSONDecodeError:
                        await asyncio.sleep(0.1)

            except (ConnectionResetError, OSError, asyncio.IncompleteReadError) as e:
                _LOGGER.warning(f"Connection error during fetch_data: {e}, reconnecting...")
                await self.tcp_manager.reconnect()
                return None
            except Exception as e:
                _LOGGER.error(f"Error fetching data from AECC device: {e}", exc_info=True)
                return None

    async def send_switch_command(self, attr, switch=False) -> bool:
        async with self._cmd_lock:
            try:
                _, writer = await self.tcp_manager.get_reader_writer()
                _LOGGER.info(f"Send switch command: {attr}")
                request = {
                    "Set": "SubDeviceControl",
                    "SerialNumber": self.serial_number,
                    "CommandSource": "Web",
                    "ControlsParameter": {
                        "DevTypeClass": 0x200,
                        "DevAddr": attr['dev_addr'],
                        "IsThirdParty": attr['is_third_party'],
                        "CommSerialNum": 963,
                        "DevType": attr.get('dev_type', 200),
                        "Param": {
                            "Switch": 1 if switch else 0,
                            "IsInterconnect": 0
                        }
                    }
                }
                writer.write(json.dumps(request).encode() + b'\n')
                await writer.drain()
                _LOGGER.info(f"Sent switch command: {request}")

                buffer = b''
                while True:
                    reader, _ = await self.tcp_manager.get_reader_writer()
                    chunk = await reader.read(4096)
                    if not chunk:
                        raise ConnectionResetError("Device closed the connection")
                    buffer += chunk
                    try:
                        json_data = json.loads(buffer.decode('utf-8'))
                        _LOGGER.info(f"Switch command response: {json_data}")
                        self.serial_number += 1
                        if "succeed" in str(json_data):
                            return True
                        else:
                            _LOGGER.warning(f"Switch command failed: {json_data}")
                            return False
                    except json.JSONDecodeError:
                        await asyncio.sleep(0.1)

            except (ConnectionResetError, OSError, asyncio.IncompleteReadError) as e:
                _LOGGER.warning(f"Connection error during send_switch_command: {e}, reconnecting...")
                await self.tcp_manager.reconnect()
                return False
            except Exception as e:
                _LOGGER.error(f"Error sending switch command to AECC device: {e}", exc_info=True)
                return False

    async def turn_on_switch(self, attr) -> bool:
        return await self.send_switch_command(attr, True)

    async def turn_off_switch(self, attr) -> bool:
        return await self.send_switch_command(attr, False)

    async def send_hardware_param(self, start_addr: int, data_val: int) -> bool:
        """Send an inverter register write command (e.g. AC relay, feed-in flag)."""
        async with self._cmd_lock:
            try:
                _, writer = await self.tcp_manager.get_reader_writer()
                request = {
                    "Set": "InverterParam",
                    "SerialNumber": self.serial_number,
                    "CommandSource": "Web",
                    "ControlsParameter": {
                        "StartAddr": start_addr,
                        "Num": 1,
                        "Data": data_val
                    }
                }
                writer.write(json.dumps(request).encode() + b'\n')
                await writer.drain()
                _LOGGER.warning(
                    f"[InverterSwitch] Sent InverterParam: startAddr={start_addr}, data={data_val} | "
                    f"full request: {request}"
                )

                buffer = b''
                deadline = asyncio.get_event_loop().time() + 8
                while True:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        _LOGGER.warning(
                            f"[InverterSwitch] Timeout waiting for gateway response to InverterParam "
                            f"(startAddr={start_addr}). Gateway may not support this command locally."
                        )
                        return False
                    try:
                        reader, _ = await self.tcp_manager.get_reader_writer()
                        chunk = await asyncio.wait_for(reader.read(4096), timeout=remaining)
                    except asyncio.TimeoutError:
                        _LOGGER.warning(
                            f"[InverterSwitch] Timeout waiting for gateway response to InverterParam "
                            f"(startAddr={start_addr}). Gateway may not support this command locally."
                        )
                        return False
                    if not chunk:
                        raise ConnectionResetError("Device closed the connection")
                    buffer += chunk
                    try:
                        json_data = json.loads(buffer.decode('utf-8'))
                        self.serial_number += 1
                        _LOGGER.warning(f"[InverterSwitch] Gateway response: {json_data}")
                        return "succeed" in str(json_data).lower()
                    except json.JSONDecodeError:
                        await asyncio.sleep(0.1)

            except (ConnectionResetError, OSError, asyncio.IncompleteReadError) as e:
                _LOGGER.warning(f"Connection error during send_hardware_param: {e}, reconnecting...")
                await self.tcp_manager.reconnect()
                return False
            except Exception as e:
                _LOGGER.error(f"Error sending hardware param: {e}", exc_info=True)
                return False

    async def disconnect(self):
        await self.tcp_manager.close()

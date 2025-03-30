import inquirer
import platform
import serial
import serial.tools.list_ports
import asyncio
import threading
import time
from bleak import BleakClient, BleakScanner
import os

from common import *


class SerialClient(object):

    def __init__(self):
        self.port = ''
        self.ser = None
        self.connected = False
        self.baud = 115200

    def __unique_ports(self, ports):
        port_list = []
        for port in ports:
            if port not in port_list:
                port_list.append(port)
        return port_list

    def list_ports(self):
        ports = serial.tools.list_ports.comports()
        matching_ports = [port.device for port in ports if platform.system() == 'Windows' or "serial" in port.device.lower()]
        non_matching_ports = [port.device for port in ports if port.device not in matching_ports]
        return self.__unique_ports(matching_ports + non_matching_ports)

    def select_port(self):
        ports = self.list_ports()
        if len(ports) == 1:
            return ports[0]
        questions = [
            inquirer.List('port',
                          message="Select a port",
                          choices=ports,
                          carousel=True)
        ]
        answers = inquirer.prompt(questions)
        self.port = answers['port']
        return self.port

    def connect(self, port):
        try:
            # 如果之前连接过，先断开
            if self.ser and self.ser.is_open:
                self.disconnect()
            
            # 等待一小段时间确保端口完全释放
            time.sleep(0.5)
            
            # 尝试打开串口
            self.ser = serial.Serial(port, self.baud, timeout=1)
            self.port = port
            self.connected = True
            
            # 创建独立线程读取数据
            self.thread = threading.Thread(target=self.read, args=(self.ser,), daemon=True)
            self.thread.start()
            
            logger.info(f"Connected to {port}.")
            return True
        except Exception as e:
            # 尝试使用更高权限打开端口
            try:
                # 如果是Windows系统，尝试以独占模式打开
                if os.name == 'nt':
                    import win32file
                    import win32con
                    import pywintypes
                    
                    # 关闭先前打开的句柄
                    if hasattr(self, 'handle') and self.handle:
                        win32file.CloseHandle(self.handle)
                    
                    # 尝试以独占方式打开串口
                    self.handle = win32file.CreateFile(
                        f"\\\\.\\{port}",
                        win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                        0,  # 不共享
                        None,  # 默认安全属性
                        win32con.OPEN_EXISTING,
                        0,  # 没有重叠I/O
                        None  # 模板文件为None
                    )
                    
                    # 如果成功打开，创建Serial对象
                    self.ser = serial.Serial()
                    self.ser.port = port
                    self.ser.baudrate = self.baud
                    self.ser.timeout = 1
                    self.ser.open()
                    self.port = port
                    self.connected = True
                    
                    # 创建独立线程读取数据
                    self.thread = threading.Thread(target=self.read, args=(self.ser,), daemon=True)
                    self.thread.start()
                    
                    logger.info(f"Connected to {port} using exclusive mode.")
                    return True
                else:
                    raise e  # 非Windows系统，重新抛出异常
            except Exception as e2:
                error(e, f"Connect to {port} Failed")
                return False

    def disconnect(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                logger.info(f"Disconnected from {self.port}.")
            except Exception as e:
                error(e, "Failed to disconnect the serial port.")
        else:
            logger.info("Serial port is already closed or was not connected.")
        self.connected = False
        self.ser = None

    def read(self, port):
        while True:
            if port.in_waiting:
                data = port.read(port.in_waiting)
                result = data.decode('utf-8', errors='ignore')
                logger.debug("\nReceived:", result.strip('\n').strip())

    def send(self, msg):
        try:
            encode_msg = msg.encode('utf-8')
            self.ser.write(encode_msg)
            logger.debug(f"Sent: {msg}")
            # 发送后添加换行符，确保命令能被设备正确接收
            if not msg.endswith('\n'):
                self.ser.write(b'\n')
            
            # 简化回应检测逻辑，不要期望完全相同的回应
            start_time = time.time()
            while time.time() - start_time < 2:  # 等待2秒
                if self.ser.in_waiting > 0:
                    response = self.ser.read(self.ser.in_waiting).decode('utf-8', errors='ignore')
                    logger.debug(f"Received: {response}")
                    return response
                time.sleep(0.1)
            
            return None  # 超时返回
        except Exception as e:
            error(e, "Serial port send message Failed!")
            self.connected = False
            return None


class BaseBluetoothClient(object):
    def __init__(self, device_name="", service_uuid="", characteristic_uuid=""):
        self.device_name = device_name
        self.service_uuid = service_uuid
        self.characteristic_uuid = characteristic_uuid
        self.client = None
        self.connected = False

    async def list_devices(self):
        logger.info("Scanning devices...")
        device_list = []
        devices = await BleakScanner.discover()
        for device in devices:
            if device.name == self.device_name:
                device_list.append(device.address)
        return device_list

    async def connect(self, device_address):
        self.client = BleakClient(device_address)
        try:
            await self.client.connect()
            logger.info(f"Connected to {self.device_name} at {device_address}")
            self.connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {self.device_name}: {e}")
            self.connected = False
            return False

    async def disconnect(self):
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            self.connected = False
            logger.info(f"Disconnected from {self.device_name}")

    async def send(self, data):
        if self.client and self.client.is_connected:
            try:
                await self.client.write_gatt_char(self.characteristic_uuid, data.encode('utf-8'))
                logger.info(f"Sent to {self.device_name}: {data}")
            except Exception as e:
                logger.error(f"Failed to send data: {e}")
        else:
            logger.info("Not connected to any device.")


class BluetoothClient(BaseBluetoothClient):
    def __init__(self, device_name="Desk-Emoji",
                 service_uuid="4db9a22d-6db4-d9fe-4d93-38e350abdc3c",
                 characteristic_uuid="ff1cdaef-0105-e4fb-7be2-018500c2e927"):
        super().__init__(device_name, service_uuid, characteristic_uuid)
        self.loop_thread = threading.Thread(target=self._run_event_loop)
        self.loop_thread.daemon = True
        self.loop = asyncio.new_event_loop()
        self.loop_thread.start()

    def _run_event_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def list_devices(self):
        return asyncio.run_coroutine_threadsafe(super().list_devices(), self.loop).result()

    def connect(self, device_address):
        return asyncio.run_coroutine_threadsafe(super().connect(device_address), self.loop).result()

    def disconnect(self):
        asyncio.run_coroutine_threadsafe(super().disconnect(), self.loop).result()

    def send(self, data):
        asyncio.run_coroutine_threadsafe(super().send(data), self.loop).result()

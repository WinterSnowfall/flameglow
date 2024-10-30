#!/usr/bin/env python3
'''
@author: Winter Snowfall
@version: 2.32
@date: 30/10/2024

Warning: Built for use with python 3.6+
'''

import logging
import os
import subprocess
import json
from logging.handlers import RotatingFileHandler
# uncomment for debugging purposes only
#import traceback

# logging configuration block
LOG_FILE_PATH = os.path.join('..', 'logs', 'os_stats.log')
logger_file_handler = RotatingFileHandler(LOG_FILE_PATH, maxBytes=25165824, backupCount=1, encoding='utf-8')
LOGGER_FORMAT = '%(asctime)s %(levelname)s : %(name)s >>> %(message)s'
logger_file_handler.setFormatter(logging.Formatter(LOGGER_FORMAT))
# logging level for other modules
logging.basicConfig(format=LOGGER_FORMAT, level=logging.ERROR)
logger = logging.getLogger(__name__)
logger.addHandler(logger_file_handler)

PROC_LOADAVG_PATH = '/proc/loadavg'
PROC_MEMINFO_PATH = '/proc/meminfo'
PROC_UPTIME_PATH = '/proc/uptime'
PROC_NET_DEV_PATH = '/proc/net/dev'
PROC_IO_DEV_PATH = '/proc/diskstats'

SYS_RASPBERRY_PI_HOST_TYPE = 'raspberrypi'
SYS_CPU_THERMAL_ZONE_TYPE_PI = 'cpu-thermal'
SYS_CPU_THERMAL_ZONE_TYPE_GENERIC = 'x86_pkg_temp'
# could possibly add intel dGPU support in the future
SYS_GPU_CARD_TYPES = ('amdgpu')

IO_SECTOR_SIZE = 512

# could possibly add intel dGPU support in the future
GPU_TYPES = ('nvidia', 'amd', 'raspberrypi')
IO_SERIAL_NAME_COMMAND = ['lsblk', '--nodeps', '-J', '-o', 'name,serial']
NVIDIA_GPU_STATS_COMMAND = ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,temperature.gpu', 
                            '--format=csv,noheader']
RPI_GPU_TEMP_COMMAND = ['vcgencmd', 'measure_temp']

class os_stats:
    '''gather host stats using the /proc and /sys OS stat modules'''

    _logging_level = logging.WARNING

    def __init__(self, host_type, gpu_type, logging_level):
        self._net_intf = None
        self._net_intf_bytes_rec_prev = None
        self._net_intf_bytes_trans_prev = None
        self._net_intf_bytes_rec = 0
        self._net_intf_bytes_trans = 0

        self._io_device = None
        self._io_device_sectors_read_prev = None
        self._io_device_sectors_written_prev = None
        self._io_device_sectors_read = 0
        self._io_device_sectors_written = 0

        self._cpu_thermal_zone_id = None
        self._nvme_drive_id = None
        self._nvme_hwmon_id = None
        self._gpu_card_id = None
        self._gpu_hwmon_id = None

        self.avg_cpu_usage = 0
        self.memory_load = 0
        self.uptime = 0
        self.net_rec_rate = 0
        self.net_trans_rate = 0
        self.io_bytes_read = 0
        self.io_bytes_written = 0
        
        # currently only relevant for Nvidia GPUs
        self.gpu_usage = 0
        self.gpu_memory_usage = 0

        self.cpu_package_temp = 0
        self.nvme_composite_temp = 0
        self.gpu_temp = 0

        # defaults to 'WARNING' otherwise
        if logging_level == 'DEBUG':
            self._logging_level = logging.DEBUG
        elif logging_level == 'INFO':
            self._logging_level = logging.INFO

        self._host_type = host_type
        self._gpu_type = gpu_type

        # logging level for current logger
        logger.setLevel(self._logging_level)

        self.detect_cpu_thermal_zone_path()
        self.detect_nvme_path()
        if self._gpu_type == GPU_TYPES[1]:
            self.detect_gpu_path()

    def set_network_interface(self, net_intf):
        self._net_intf = net_intf
        
    def get_io_device(self):
        return self._io_device

    def set_io_device(self, io_device):
        # i/o device serial numbers can be used as a more strict identifier
        try:
            lsblk_output_raw = subprocess.run(IO_SERIAL_NAME_COMMAND, capture_output=True,
                                              text=True, check=True)
            lsblk_output = json.loads(lsblk_output_raw.stdout)
            
            for block_device in lsblk_output['blockdevices']:
                block_device_name = block_device['name']
                block_device_serial = block_device['serial']
                
                logger.debug(f'Found I/O device {block_device_name} with serial number {block_device_serial}.')
                
                if block_device_serial == io_device:
                    logger.info(f'I/O device name set to {block_device_name}.')
                    self._io_device = block_device_name
                    return
        except:
            pass
            
        self._io_device = io_device

    def detect_cpu_thermal_zone_path(self):
        logger.info(f'Detecting CPU package thermal zone for {self._host_type} host type...')

        thermal_zone_no = 0

        while os.path.exists(f'/sys/class/thermal/thermal_zone{thermal_zone_no}'):
            logger.debug(f'Atempting CPU package thermal zone detection for: {thermal_zone_no}...')

            with open(f'/sys/class/thermal/thermal_zone{thermal_zone_no}/type', 'r') as zone_type:
                detected_zone_type = zone_type.read().strip()
                logger.debug(f'detected_zone_type: {detected_zone_type}')

                if self._host_type != SYS_RASPBERRY_PI_HOST_TYPE:
                    if detected_zone_type == SYS_CPU_THERMAL_ZONE_TYPE_GENERIC:
                        self._cpu_thermal_zone_id = thermal_zone_no
                        logger.info('Succesfully detected CPU package thermal zone.')
                        return
                else:
                    if detected_zone_type == SYS_CPU_THERMAL_ZONE_TYPE_PI:
                        self._cpu_thermal_zone_id = thermal_zone_no
                        logger.info('Succesfully detected CPU package thermal zone.')
                        return

                thermal_zone_no += 1

        logger.warning('CPU thermal zones have been exhausted without detection.')

    def detect_nvme_path(self):
        logger.info(f'Detecting NVMe composite thermal readings...')

        nvme_no = 0

        while os.path.exists(f'/sys/class/nvme/nvme{nvme_no}'):
            logger.debug(f'Atempting NVMe hwmon detection for nvme: {nvme_no}...')

            with os.scandir(f'/sys/class/nvme/nvme{nvme_no}') as hwmon_path:
                for hwmon_path_entry in hwmon_path:
                    if hwmon_path_entry.name.startswith('hwmon') and hwmon_path_entry.is_dir():
                        logger.debug(f'Atempting NVMe temp input detection for: {hwmon_path_entry.name}...')

                        if os.path.exists(f'/sys/class/nvme/nvme{nvme_no}/{hwmon_path_entry.name}/temp1_input'):
                            self._nvme_drive_id = nvme_no
                            logger.debug(f'nvme_no: {nvme_no}')

                            detected_hwmon_no = hwmon_path_entry.name[5:]
                            self._nvme_hwmon_id = detected_hwmon_no
                            logger.debug(f'detected_hwmon_no: {detected_hwmon_no}')

                            logger.info('Succesfully detected NVMe hwmon path.')
                            return

            nvme_no += 1

        logger.info('No NVMe devices with thermal readings have been detected.')

    def detect_gpu_path(self):
        logger.info(f'Detecting GPU thermal readings for {self._gpu_type} GPU type...')

        card_no = 0

        while os.path.exists(f'/sys/class/drm/card{card_no}'):
            logger.debug(f'Atempting GPU card detection for card: {card_no}...')

            with os.scandir(f'sys/class/drm/card{card_no}/device/hwmon') as hwmon_path:
                for hwmon_path_entry in hwmon_path:
                    if hwmon_path_entry.name.startswith('hwmon') and hwmon_path_entry.is_dir():
                        logger.debug(f'Atempting GPU card detection for: {hwmon_path_entry.name}...')

                        detected_hwmon_no = hwmon_path_entry.name[5:]
                        logger.debug(f'detected_hwmon_no: {detected_hwmon_no}')

                        with open(f'/sys/class/drm/card{card_no}'
                                  f'/device/hwmon/hwmon{detected_hwmon_no}/name', 'r') as card_name:
                            detected_card_name = card_name.read().strip()
                            logger.debug(f'detected_card_name: {detected_card_name}')

                            if detected_card_name in SYS_GPU_CARD_TYPES:
                                self._gpu_card_id = card_no
                                self._gpu_hwmon_id = detected_hwmon_no
                                logger.info('Succesfully detected GPU card.')
                                return

        logger.warning('No DRM cards with thermal readings have been detected.')

    def clear_stats(self):
        self._net_intf_bytes_rec = 0
        self._net_intf_bytes_trans = 0

        self._io_device_sectors_read = 0
        self._io_device_sectors_written = 0

        self.avg_cpu_usage = 0
        self.memory_load = 0
        self.uptime = 0
        self.net_rec_rate = 0
        self.net_trans_rate = 0
        self.io_bytes_read = 0
        self.io_bytes_written = 0
        
        self.gpu_usage = 0
        self.gpu_memory_usage = 0

        self.cpu_package_temp = 0
        self.nvme_composite_temp = 0
        self.gpu_temp = 0

    def collect_stats(self):
        logger.info('***** Starting data collection run *****')

        try:
            # /proc/loadavg file parsing
            with open(PROC_LOADAVG_PATH, 'r') as loadavg:
                self.avg_cpu_usage = loadavg.read().split()[0]

                logger.debug(f'avg_cpu_usage: {self.avg_cpu_usage}')

            # /proc/meminfo file parsing
            with open(PROC_MEMINFO_PATH, 'r') as meminfo:
                memory_total = 0
                memory_available = 0

                for line in meminfo.read().splitlines():
                    if line.startswith('MemTotal'):
                        memory_total = line.split(':')[1].strip().split()[0]
                    elif line.startswith('MemAvailable'):
                        memory_available = line.split(':')[1].strip().split()[0]
                    if memory_total != 0 and memory_available != 0:
                        break

                self.memory_load = int(memory_total) - int(memory_available)

                logger.debug(f'memory_load: {self.memory_load}')

            # /proc/uptime file parsing
            with open(PROC_UPTIME_PATH, 'r') as uptime:
                self.uptime = int(float(uptime.read().split()[0]))

                logger.debug(f'uptime: {self.uptime}')

            # /proc/net/dev file parsing
            with open(PROC_NET_DEV_PATH, 'r') as net_dev:
                for line in net_dev.read().splitlines():
                    if line.lstrip().startswith(self._net_intf):
                        intf_line = line.split(':')[1].split()
                        self._net_intf_bytes_rec = int(intf_line[0])
                        self._net_intf_bytes_trans = int(intf_line[8])
                        break

                logger.debug(f'_net_intf_bytes_rec: {self._net_intf_bytes_rec}')
                logger.debug(f'_net_intf_bytes_trans: {self._net_intf_bytes_trans}')

                logger.debug(f'_net_intf_bytes_rec_prev: {self._net_intf_bytes_rec_prev}')
                logger.debug(f'_net_intf_bytes_trans_prev: {self._net_intf_bytes_trans_prev}')

                # won't do a delta on the first pass, so return 0
                if self._net_intf_bytes_rec_prev is None and self._net_intf_bytes_trans_prev is None:
                    self.net_rec_rate = 0
                    self.net_trans_rate = 0
                else:
                    self.net_rec_rate = self._net_intf_bytes_rec - self._net_intf_bytes_rec_prev
                    self.net_trans_rate = self._net_intf_bytes_trans - self._net_intf_bytes_trans_prev

                # setup delta for next iteration
                self._net_intf_bytes_rec_prev = self._net_intf_bytes_rec
                self._net_intf_bytes_trans_prev = self._net_intf_bytes_trans

                logger.debug(f'net_rec_rate: {self.net_rec_rate}')
                logger.debug(f'net_trans_rate: {self.net_trans_rate}')

            # /proc/diskstats file parsing
            with open(PROC_IO_DEV_PATH, 'r') as io_dev:
                for line in io_dev.read().splitlines():
                    if self._io_device in line:
                        intf_line = line.split()
                        # offset fields by 2 compared to documentation descriptions
                        self._io_device_sectors_read = int(intf_line[5])
                        self._io_device_sectors_written = int(intf_line[9])
                        break

                logger.debug(f'_io_device_sectors_read: {self._io_device_sectors_read}')
                logger.debug(f'_io_device_sectors_written: {self._io_device_sectors_written}')

                logger.debug(f'_io_device_sectors_read_prev: {self._io_device_sectors_read_prev}')
                logger.debug(f'_io_device_sectors_written_prev: {self._io_device_sectors_written_prev}')

                # won't do a delta on the first pass, so return 0
                if self._io_device_sectors_read_prev is None and self._io_device_sectors_written_prev is None:
                    self.io_bytes_read = 0
                    self.io_bytes_written = 0
                else:
                    self.io_bytes_read = (self._io_device_sectors_read -
                                          self._io_device_sectors_read_prev) * IO_SECTOR_SIZE
                    self.io_bytes_written = (self._io_device_sectors_written -
                                             self._io_device_sectors_written_prev) * IO_SECTOR_SIZE

                # setup delta for next iteration
                self._io_device_sectors_read_prev = self._io_device_sectors_read
                self._io_device_sectors_written_prev = self._io_device_sectors_written

                logger.debug(f'io_bytes_read: {self.io_bytes_read}')
                logger.debug(f'io_bytes_written: {self.io_bytes_written}')

            # /sys/class/thermal/thermal_zone*/temp parsing
            if self._cpu_thermal_zone_id is not None:
                with open(f'/sys/class/thermal/thermal_zone{self._cpu_thermal_zone_id}/temp', 'r') as temp:
                    self.cpu_package_temp = int(temp.read())

                    logger.debug(f'cpu_package_temp: {self.cpu_package_temp}')
            else:
                logger.debug('Skipping CPU package temperature collection.')

            # /sys/class/nvme/nvme*/hwmon0/temp1_input parsing
            if self._nvme_drive_id is not None and self._nvme_hwmon_id is not None:
                # temp1_input is traditionally the "composite" temperature
                # of the NVMe drive, which is used for throttling
                with open(f'/sys/class/nvme/nvme{self._nvme_drive_id}'
                          f'/hwmon{self._nvme_hwmon_id}/temp1_input', 'r') as nvme_temp:
                    self.nvme_composite_temp = int(nvme_temp.read())

                logger.debug(f'nvme_composite_temp: {self.nvme_composite_temp}')
            else:
                logger.debug('Skipping NVMe composite temperature collection.')

            # nvidia-smi command output parsing
            if self._gpu_type == GPU_TYPES[0]:
                try:
                    # use the nvidia-smi utility to parse GPU stats for Nvidia
                    nvidia_smi_output_raw = subprocess.run(NVIDIA_GPU_STATS_COMMAND, capture_output=True,
                                                           text=True, check=True)
                    nvidia_smi_output = nvidia_smi_output_raw.stdout.split(', ')
                    # returned GPU usage will be a integer percentage
                    self.gpu_usage = int(nvidia_smi_output[0].split()[0])
                    # returned GPU memory usage will in MiBs
                    self.gpu_memory_usage = int(nvidia_smi_output[1].split()[0])
                    # multiply by 1000 to align with sys sensor readings default format
                    self.gpu_temp = int(nvidia_smi_output[2]) * 1000
                except:
                    self.gpu_usage = 0
                    self.gpu_memory_usage = 0
                    self.gpu_temp = 0
                    logger.warning('Nvidia SMI could not communicate with the Nvidia driver.')

                logger.debug(f'gpu_usage: {self.gpu_usage}')
                logger.debug(f'gpu_memory_usage: {self.gpu_memory_usage}')
                logger.debug(f'gpu_temp: {self.gpu_temp}')

            # /sys/class/drm/card*/device/hwmon/hwmon*/temp1_input file parsing
            elif self._gpu_type == GPU_TYPES[1]:
                if self._gpu_card_id is not None and self._gpu_hwmon_id is not None:
                    with open(f'/sys/class/drm/card{self._gpu_card_id}/device'
                              f'/hwmon/hwmon{self._gpu_hwmon_id}/temp1_input',
                              'r') as temp:
                        self.gpu_temp = int(temp.read())

                        logger.debug(f'gpu_temp: {self.gpu_temp}')
                else:
                    logger.debug('Skipping GPU temperature collection.')

            # vcgencmd measure_temp command output parsing
            elif self._gpu_type == GPU_TYPES[2]:
                try:
                    # use the vcgencmd utility to parse temperature for Raspberry Pis
                    vcgencmd_output = subprocess.run(RPI_GPU_TEMP_COMMAND, capture_output=True,
                                                     text=True, check=True)

                    # multiply by 1000 to align with sys sensor readings default format
                    self.gpu_temp = int(float(vcgencmd_output.stdout.strip().split('=')[1][:-2]) * 1000)

                except:
                    self.gpu_temp = 0
                    logger.warning('Unable to retrieve Raspberry Pi GPU temperature from vcgencmd.')

                logger.debug(f'gpu_temp: {self.gpu_temp}')

            else:
                logger.debug('No supported GPU type detected. Skipping GPU stats collection.')

            logger.info('***** Data collection complete *****')

        except Exception as exception:
            logger.error(f'Encountered following exception: {type(exception)} {exception}')
            # uncomment for debugging purposes only
            #logger.error(traceback.format_exc())
            raise

#!/usr/bin/env python3
'''
@author: Winter Snowfall
@version: 1.40
@date: 21/08/2021

Warning: Built for use with python 3.6+
'''

import logging
import os
import subprocess
from logging.handlers import RotatingFileHandler
#uncomment for debugging purposes only
import traceback

##logging configuration block
log_file_full_path = os.path.join('..', 'logs', 'os_stats.log')
logger_file_handler = RotatingFileHandler(log_file_full_path, maxBytes=104857600, backupCount=2, encoding='utf-8')
logger_format = '%(asctime)s %(levelname)s : %(name)s >>> %(message)s'
logger_file_handler.setFormatter(logging.Formatter(logger_format))
#logging level for other modules
logging.basicConfig(format=logger_format, level=logging.ERROR)
logger = logging.getLogger(__name__)
logger.addHandler(logger_file_handler)

PROC_LOADAVG_PATH = '/proc/loadavg'
PROC_MEMINFO_PATH = '/proc/meminfo'
PROC_UPTIME_PATH = '/proc/uptime'
PROC_NET_DEV_PATH = '/proc/net/dev'

SYS_RASPBERRY_PI_HOST_TYPE = 'raspberrypi'
SYS_CPU_THERMAL_ZONE_TYPE_PI = 'cpu-thermal'
SYS_CPU_THERMAL_ZONE_TYPE_GENERIC = 'x86_pkg_temp'
SYS_GPU_AMD_CARD_TYPE = 'amdgpu'

NVIDIA_GPU_TEMP_COMMAND = 'nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader'

class os_stats:
    '''gather host stats using the /proc and /sys OS stat modules'''
    
    _logging_level = logging.WARNING
    
    def __init__(self, host_type, gpu_type, logging_level):
        self._net_intf_name = None
        self._net_intf_bytes_rec_prev = None
        self._net_intf_bytes_trans_prev = None
        self._net_intf_bytes_rec = 0
        self._net_intf_bytes_trans = 0
        
        self._thermal_zone_identifier = 0
        self._gpu_card_identifier = 0
        
        self.avg_cpu_usage = 0
        self.memory_load = 0
        self.uptime = 0
        self.net_rec_rate = 0
        self.net_trans_rate = 0
        
        self.cpu_package_temp = 0
        self.gpu_temp = 0
        
        #defaults to WARNING otherwise
        if logging_level == 'DEBUG':
            self._logging_level = logging.DEBUG
        elif logging_level == 'INFO':
            self._logging_level = logging.INFO
        
        self._host_type = host_type
        self._gpu_type = gpu_type
            
        #logging level for current logger
        logger.setLevel(self._logging_level)
        
        self.detect_thermal_zone_path()
    
        if self._gpu_type == 'amd':
            self.detect_amd_gpu_path()
    
    def set_net_intf_name(self, net_intf_name):
        self._net_intf_name = net_intf_name
    
    def detect_thermal_zone_path(self):
        logger.info(f'Detecting CPU package thermal zone for {self._host_type} host type...')
        
        try:
            #how many thermal zones can a system have?
            for i in range(0, 100):
                logger.debug(f'Atempting CPU package thermal zone detection for: {i}...')
                
                with open(f'/sys/class/thermal/thermal_zone{i}/type', 'r') as zone_type:
                    detected_zone_type = zone_type.read().strip()
                    logger.debug(f'detected_zone_type: {detected_zone_type}')
                    
                    if self._host_type == SYS_RASPBERRY_PI_HOST_TYPE:
                        if detected_zone_type == SYS_CPU_THERMAL_ZONE_TYPE_PI:
                            self._thermal_zone_identifier = i
                            logger.info('Succesfully detected CPU package thermal zone.')
                            break
                    else:
                        if detected_zone_type == SYS_CPU_THERMAL_ZONE_TYPE_GENERIC:
                            self._thermal_zone_identifier = i
                            logger.info('Succesfully detected CPU package thermal zone.')
                            break
        except:
            logger.critical('Thermal zones have been exhausted without detection.')
            raise
        
    def detect_amd_gpu_path(self):
        logger.info(f'Detecting GPU package thermal zone for {self._gpu_type} GPU type...')
                 
        try:
            #if you have a system with more than 2 GPUs, this tool is not for you anyway
            for i in range(0, 2):
                logger.debug(f'Atempting AMD GPU card detection for: {i}...')
                
                with open(f'/sys/class/drm/card{i}/device/hwmon/hwmon1/name', 'r') as card_name:
                    detected_card_name = card_name.read().strip()
                    logger.debug(f'detected_card_name: {detected_card_name}')
                    
                    if detected_card_name == SYS_GPU_AMD_CARD_TYPE:
                        self._gpu_card_identifier = i
                        logger.info('Succesfully detected AMD GPU card.')
                        break
        except:
            logger.critical('DRM cards have been exhausted without detection.')
            raise
                 
    def clear_stats(self):
        self._net_intf_bytes_rec = 0
        self._net_intf_bytes_trans = 0
        
        self.avg_cpu_usage = 0
        self.memory_load = 0
        self.uptime = 0
        self.net_rec_rate = 0
        self.net_trans_rate = 0
        
        self.cpu_package_temp = 0
        
    def collect_stats(self):
        logger.info('+++ Starting data collection run +++')
        
        try:
            #/proc/loadavg file parsing
            with open(PROC_LOADAVG_PATH, 'r') as loadavg:
                self.avg_cpu_usage = loadavg.read().split()[0]
                
                logger.debug(f'avg_cpu_usage: {self.avg_cpu_usage}')
                
            #/proc/meminfo file parsing
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
                
            #/proc/uptime file parsing
            with open(PROC_UPTIME_PATH, 'r') as uptime:
                self.uptime = int(float(uptime.read().split()[0]))
                
                logger.debug(f'uptime: {self.uptime}')
                
            #/proc/net/dev file parsing
            with open(PROC_NET_DEV_PATH, 'r') as net_dev:
                for line in net_dev.read().splitlines():
                    if line.lstrip().startswith(self._net_intf_name):
                        intf_line = line.split(':')[1].split()
                        self._net_intf_bytes_rec = int(intf_line[0])
                        self._net_intf_bytes_trans =  int(intf_line[8])
                        break
                    
                logger.debug(f'_net_intf_bytes_rec: {self._net_intf_bytes_rec}')
                logger.debug(f'_net_intf_bytes_trans: {self._net_intf_bytes_trans}')
                    
                logger.debug(f'_net_intf_bytes_rec_prev: {self._net_intf_bytes_rec_prev}')
                logger.debug(f'_net_intf_bytes_trans_prev: {self._net_intf_bytes_trans_prev}')
                
                #won't do a delta on the first pass, so return 0
                if self._net_intf_bytes_rec_prev is None and self._net_intf_bytes_trans_prev is None:
                    self.net_rec_rate = 0
                    self.net_trans_rate = 0
                else:
                    self.net_rec_rate = self._net_intf_bytes_rec - self._net_intf_bytes_rec_prev
                    self.net_trans_rate = self._net_intf_bytes_trans - self._net_intf_bytes_trans_prev

                #setup delta for next iteration
                self._net_intf_bytes_rec_prev = self._net_intf_bytes_rec
                self._net_intf_bytes_trans_prev = self._net_intf_bytes_trans
                
                logger.debug(f'net_rec_rate: {self.net_rec_rate}')
                logger.debug(f'net_trans_rate: {self.net_trans_rate}')
                
            #/sys/class/thermal/thermal_zone*/temp parsing
            with open(f'/sys/class/thermal/thermal_zone{self._thermal_zone_identifier}/temp', 'r') as temp:
                self.cpu_package_temp = int(temp.read())
                    
                logger.debug(f'cpu_package_temp: {self.cpu_package_temp}')
                
            #/sys/class/drm/card*/device/hwmon/hwmon1/temp1_input parsing
            if self._gpu_type == 'nvidia':
                #use the nvidia-smi utility to parse temperature for nvidia
                nvidia_smi_output = subprocess.run(NVIDIA_GPU_TEMP_COMMAND, shell=True, 
                                                   capture_output=True, text=True)
                try:
                    #multiply by 1000 to align with sys sensor readings default format
                    self.gpu_temp = int(nvidia_smi_output.stdout.strip()) * 1000
                except ValueError:
                    self.gpu_temp = 0
                    logger.warning('Nvidia SMI could not communicate with the Nvidia driver.')
                
                logger.debug(f'gpu_temp: {self.gpu_temp}')
                
            elif self._gpu_type == 'amd':
                with open(f'/sys/class/drm/card{self._gpu_card_identifier}/device/hwmon/hwmon1/temp1_input', 
                          'r') as temp:
                    self.gpu_temp = int(temp.read())
                    
                    logger.debug(f'gpu_temp: {self.gpu_temp}')
            else:
                logger.debug('No supported GPU type detected. Skipping GPU temp collection.')
                
        except:
            #uncomment for debugging purposes only
            logger.error(traceback.format_exc())
            raise
            
        logger.info('--- Data collection complete ---')

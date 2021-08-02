#!/usr/bin/env python3
'''
@author: Winter Snowfall
@version: 1.00
@date: 02/08/2021

Warning: Built for use with python 3.6+
'''

import logging
import os
from logging.handlers import RotatingFileHandler
#uncomment for debugging purposes only
import traceback

##logging configuration block
log_file_full_path = os.path.join('..', 'logs', 'proc_stat.log')
logger_file_handler = RotatingFileHandler(log_file_full_path, maxBytes=8388608, backupCount=1, encoding='utf-8')
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

class proc_stats:
    '''gather host stats using the /proc OS stats module'''
    
    _logging_level = logging.WARNING
    
    def __init__(self, logging_level):
        self._net_intf_name = None
        self._net_intf_bytes_rec_prev = None
        self._net_intf_bytes_trans_prev = None
        self._net_intf_bytes_rec = 0
        self._net_intf_bytes_trans = 0
        
        self.avg_cpu_usage = 0
        self.memory_load = 0
        self.uptime = 0
        self.net_rec_rate = 0
        self.net_trans_rate = 0
        
        #defaults to WARNING otherwise
        if logging_level == 'DEBUG':
            self._logging_level = logging.DEBUG
        elif logging_level == 'INFO':
            self._logging_level = logging.INFO
            
        #logging level for current logger
        logger.setLevel(self._logging_level)
    
    def set_net_intf_name(self, net_intf_name):
        self._net_intf_name = net_intf_name
    
    def clear_stats(self):
        self._net_intf_bytes_rec = 0
        self._net_intf_bytes_trans = 0
        
        self.avg_cpu_usage = 0
        self.memory_load = 0
        self.uptime = 0
        self.net_rec_rate = 0
        self.net_trans_rate = 0
        
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
                
        except:
            #uncomment for debugging purposes only
            logger.error(traceback.format_exc())
            raise
            
        logger.info('--- Data collection complete ---')

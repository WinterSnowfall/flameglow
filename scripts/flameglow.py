#!/usr/bin/env python3
'''
@author: Winter Snowfall
@version: 2.20
@date: 24/02/2024

Warning: Built for use with python 3.6+
'''

import signal
import os
from configparser import ConfigParser
from time import sleep
from prometheus_client import start_http_server, Gauge
from os_stats import os_stats

# conf file block
CONF_FILE_PATH = os.path.join('..', 'conf', 'flameglow.conf')

NVME_DEVICE_NAME = 'nvme'
SUPPORTED_GPU_TYPES = ('nvidia', 'amd', 'raspberrypi')

def sigterm_handler(signum, frame):
    print('Stopping stats collection due to SIGTERM...')

    raise SystemExit(0)

def sigint_handler(signum, frame):
    print('Stopping stats collection due to SIGINT...')

    raise SystemExit(0)

if __name__ == '__main__':
    # catch SIGTERM and exit gracefully
    signal.signal(signal.SIGTERM, sigterm_handler)
    # catch SIGINT and exit gracefully
    signal.signal(signal.SIGINT, sigint_handler)

    print(f'Starting flameglow - a simple POSIX proc system stat collection agent...\n\n')

    configParser = ConfigParser()

    try:
        configParser.read(CONF_FILE_PATH)
        general_section = configParser['GENERAL']

        PROMETHEUS_CLIENT_PORT = general_section.getint('prometheus_client_port')
        STATS_COLLECTION_INTERVAL = general_section.getint('collection_interval')
        NET_INTF_NAME = general_section.get('network_interface_name')
        IO_DEV_NAME = general_section.get('io_device_name')
        HOST_TYPE = general_section.get('host_type')
        GPU_TYPE = general_section.get('gpu_type')
        LOGGING_LEVEL = general_section.get('logging_level')

    except:
        print('Could not parse configuration file. Please make sure the appropriate structure is in place!')
        raise SystemExit(1)

    ### Prometheus client metrics ###############################################################################

    #----------------------------------------------- os_stats ---------------------------------------------------
    proc_stats_avg_cpu_usage = Gauge('proc_stats_avg_cpu_usage', 'Average CPU usage over the last minute')
    proc_stats_memory_load = Gauge('proc_stats_memory_load', 'Current RAM memory usage')
    proc_stats_uptime = Gauge('proc_stats_uptime', 'System uptime in seconds')
    proc_stats_rec_rate = Gauge('proc_stats_rec_rate', 'Bytes received on the specified network interface')
    proc_stats_trans_rate = Gauge('proc_stats_trans_rate', 'Byes transmitted on the specified network interface')
    proc_stats_io_read_rate = Gauge('proc_stats_io_read_rate', 'Bytes read on the specified io device')
    proc_stats_io_write_rate = Gauge('proc_stats_io_write_rate', 'Bytes written on the specified io device')
    #------------------------------------------------------------------------------------------------------------

    #------------------------------------------------ sys_stats -------------------------------------------------
    sys_stats_cpu_package_temp = Gauge('sys_stats_cpu_package_temp', 'Current CPU package temperature')
    if GPU_TYPE in SUPPORTED_GPU_TYPES:
        sys_stats_gpu_temp = Gauge('sys_stats_gpu_temp', 'Current GPU temperature')
    if NVME_DEVICE_NAME in IO_DEV_NAME:
        sys_stats_nvme_composite_temp = Gauge('sys_stats_nvme_composite_temp', 'Current NVME composite temperature')
    #------------------------------------------------------------------------------------------------------------

    #############################################################################################################

    # start a Prometheus http server thread to expose the metrics
    start_http_server(PROMETHEUS_CLIENT_PORT)

    os_stats_inst = os_stats(HOST_TYPE, GPU_TYPE, LOGGING_LEVEL)
    os_stats_inst.set_net_intf_name(NET_INTF_NAME)
    os_stats_inst.set_io_device_name(IO_DEV_NAME)

    terminate_signal = False

    while not terminate_signal:
        try:
            os_stats_inst.collect_stats()

            proc_stats_avg_cpu_usage.set(os_stats_inst.avg_cpu_usage)
            proc_stats_memory_load.set(os_stats_inst.memory_load)
            proc_stats_uptime.set(os_stats_inst.uptime)
            # always report average rates per second, regardless of collection interval
            proc_stats_rec_rate.set(os_stats_inst.net_rec_rate / STATS_COLLECTION_INTERVAL)
            proc_stats_trans_rate.set(os_stats_inst.net_trans_rate / STATS_COLLECTION_INTERVAL)
            proc_stats_io_read_rate.set(os_stats_inst.io_bytes_read / STATS_COLLECTION_INTERVAL)
            proc_stats_io_write_rate.set(os_stats_inst.io_bytes_written / STATS_COLLECTION_INTERVAL)

            sys_stats_cpu_package_temp.set(os_stats_inst.cpu_package_temp)
            if GPU_TYPE in SUPPORTED_GPU_TYPES:
                sys_stats_gpu_temp.set(os_stats_inst.gpu_temp)
            if NVME_DEVICE_NAME in IO_DEV_NAME:
                sys_stats_nvme_composite_temp.set(os_stats_inst.nvme_composite_temp)

            sleep(STATS_COLLECTION_INTERVAL)

        except SystemExit:
            print('Stopping flameglow...')
            terminate_signal = True

        except:
            os_stats_inst.clear_stats()

    print(f'\n\nThank you for using flameglow. Bye!')

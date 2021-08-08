#!/usr/bin/env python3
'''
@author: Winter Snowfall
@version: 1.10
@date: 08/08/2021

Warning: Built for use with python 3.6+
'''

from prometheus_client import start_http_server, Gauge
from configparser import ConfigParser
from time import sleep
from proc_stats import proc_stats
import threading
import signal
import os

##global parameters init
configParser = ConfigParser()

##conf file block
conf_file_full_path = os.path.join('..', 'conf', 'flameglow.conf')

# Prometheus client metrics

#---------------------- proc_stats ----------------------------------------------
proc_stats_avg_cpu_usage = Gauge('proc_stats_avg_cpu_usage', 'Average CPU usage over the last minute')
proc_stats_memory_load = Gauge('proc_stats_memory_load', 'Current RAM memory usage')
proc_stats_uptime = Gauge('proc_stats_uptime', 'System uptime in seconds')
proc_stats_rec_rate = Gauge('proc_stats_rec_rate', 'Bytes received on the specified network interface')
proc_stats_trans_rate = Gauge('proc_stats_trans_rate', 'Byes transmitted on the specified network interface')
#--------------------------------------------------------------------------------

def sigterm_handler(signum, frame):
    print(f'\n\nThank you for using chiatter. I can only hope it wasn\'t too painfull. Bye!')
    raise SystemExit(0)

def http_server():
    start_http_server(PROMETHEUS_CLIENT_PORT)
    
if __name__ == '__main__':
    #catch SIGTERM and exit gracefully
    signal.signal(signal.SIGTERM, sigterm_handler)
    
    print('---------------------------------------------------------------------------')
    print('| Welcome to flameglow - a simple POSIX proc system stat collection agent |')
    print(f'---------------------------------------------------------------------------\n')
    
    try:
        #reading from config file
        configParser.read(conf_file_full_path)
        general_section = configParser['GENERAL']
        #parsing generic parameters
        PROMETHEUS_CLIENT_PORT = general_section.getint('prometheus_client_port')
        STATS_COLLECTION_INTERVAL = general_section.getint('collection_interval')
        NET_INTF_NAME = general_section.get('network_interface_name')
        LOGGING_LEVEL = general_section.get('logging_level')

    except:
        print('Could not parse configuration file. Please make sure the appropriate structure is in place!')
        raise SystemExit(1)
    
    #start the Prometheus http server to expose the metrics
    http_server_thread = threading.Thread(target=http_server, args=(), daemon=True)
    http_server_thread.start()
    
    proc_stats_inst = proc_stats(LOGGING_LEVEL)
    proc_stats_inst.set_net_intf_name(NET_INTF_NAME)
    
    while True:
        try:
            proc_stats_inst.clear_stats()
            proc_stats_inst.collect_stats()
            
            proc_stats_avg_cpu_usage.set(proc_stats_inst.avg_cpu_usage)
            proc_stats_memory_load.set(proc_stats_inst.memory_load)
            proc_stats_uptime.set(proc_stats_inst.uptime)
            #always report average rates per second, regardless of collection interval
            proc_stats_rec_rate.set(proc_stats_inst.net_rec_rate / STATS_COLLECTION_INTERVAL)
            proc_stats_trans_rate.set(proc_stats_inst.net_trans_rate / STATS_COLLECTION_INTERVAL)
            
            sleep(STATS_COLLECTION_INTERVAL)
            
        except KeyboardInterrupt:
            break

    print(f'\n\nThank you for using flameglow. Bye!')

#! /bin/sh
### BEGIN INIT INFO
# Provides: samplerbox-pedalbass
# Required-Start: $syslog
# Required-Stop: $syslog
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: noip server
# Description:
### END INIT INFO
 
case "$1" in
    start)
        echo "Starting sampler software"
        /usr/bin/python3 /home/pi/samplerbox-pedalbass/samplerbox.py
        ;;
    stop)
        echo "Stopping sampler software"
        killall python3
        ;;
    *)
        echo "Using: /etc/init.d/sampler {start|stop}"
        exit 1
        ;;
esac
 
exit 0
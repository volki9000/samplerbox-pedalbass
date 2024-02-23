import RPi.GPIO as GPIO
import time
import string
import random

#########################################
# 7-SEGMENT DISPLAY
#
#########################################

# 7-Segment display using SPI
GPIO.setmode(GPIO.BCM)
GPIO.setup(9, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(10, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(11, GPIO.IN, pull_up_down=GPIO.PUD_UP)

import spidev

# Enable SPI
bus = spidev.SpiDev()

# Open a connection to a specific bus and device (chip select pin)
bus.open(0, 0)
# Set SPI speed and mode
bus.max_speed_hz = 500000
bus.mode = 0

def display(s):
    i = 1
    while i < 0x7f:
        # The decimals, colon and apostrophe dots
        msg = [0x77]
        msg.append(i)
        bus.xfer2(msg)
        for char in s:     # position cursor at 0
            msg = [int(ord(char))]
            bus.xfer2(msg)
            i <<= 1

        time.sleep(0.002)
display('----')

def id_generator(size=4, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))

while True:
    display(id_generator())
    time.sleep(0.5)
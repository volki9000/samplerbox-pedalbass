import RPi.GPIO as GPIO
import time

# keys open on press
keys = {
   "c": 26,
  "cs": 17,
   "d": 7,
   "ds": 8,
   "e": 25,
   "f": 1,
   "fs": 7,
#   "g": 10,
#   "gs": 22,
#   "a": 23,
#   "as": 25,
   "b": 24,
#   "c2": 4
}

# switches close on press
switches = {
    "pr+": 14,
    "pr-": 15,
    "vol+": 23,
    "vol-": 22,
    "panic": 4
}

try:
    GPIO.setmode(GPIO.BCM)  
    # Setup your channels
    for key, value in keys.items():
        GPIO.setup(value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    for key, value in switches.items():
        GPIO.setup(value, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    # To test the value of a pin use the .input method
    while(True):
        for key, value in switches.items():
            if GPIO.input(value) == GPIO.LOW:
                print('Switch, ' + key + ' pressed.')
        for key, value in keys.items():
            if GPIO.input(value) == GPIO.LOW:
                print('Key, ' + key + ' pressed.')
        time.sleep(0.1)
except KeyboardInterrupt: # If CTRL+C is pressed, exit cleanly:
    print("Keyboard interrupt")

except RuntimeWarning as e:
    print(str(e)) 

finally:
    print("clean up")
    GPIO.cleanup() # cleanup all GPIO 

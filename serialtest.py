#License
#-------
#This code is published and shared by Numato Systems Pvt Ltd under GNU LGPL 
#license with the hope that it may be useful. Read complete license at 
#http://www.gnu.org/licenses/lgpl.html or write to Free Software Foundation,
#51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA

#Simplicity and understandability is the primary philosophy followed while
#writing this code. Sometimes at the expence of standard coding practices and
#best practices. It is your responsibility to independantly assess and implement
#coding practices that will satisfy safety and security necessary for your final
#application.

#This demo code demonstrates how to read the status of a GPIO
import numato_gpio as gpio
import time

#Open port for communication	
dev = gpio.NumatoUsbGpio("/dev/ttyACM0")

# Configure port 14 as input and setup notification on logic level changes
dev.setup(0, gpio.IN)
""" def callback(port, level):
    print("{edge:7s} edge detected on port {port} "
        "-> new logic level is {level}".format(
        edge="Rising" if level else "Falling",
        port=port,
        level="high" if level else "low")
    )
 
dev.add_event_detect(0, callback, gpio.BOTH)
dev.notify = True
"""
t1 = time.time()
for x in range(1000000000):
    print(str(dev.readall()))
    time.sleep(0.05)
print("1k reads took " + str(time.time() - t1))
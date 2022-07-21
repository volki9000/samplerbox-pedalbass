# Based on https://github.com/timwaizenegger/raspberrypi-examples/blob/master/actor-led-7segment-4numbers/tm1637.py

import math
import RPi.GPIO as IO
import threading
from time import sleep, localtime
# from tqdm import tqdm

# IO.setwarnings(False)
IO.setmode(IO.BCM)

ADDR_AUTO = 0x40
ADDR_FIXED = 0x44
STARTADDR = 0xC0
# DEBUG = False

dict7seg = { '0':0b111111,
             '1':0b110000,
             '2':0b1011011,
             '3':0b1111001,
             '4':0b1110100,
             '5':0b1101101,
             '6':0b1101111,
             '7':0b0111000,
             '8':0b11111111,
             '9':0b1111101,
             'P':0b1011110,
             'n':0b1100010,
             'I':0b110,
             'E':0b1001111,
             'L':0b111,
             'C':0b1111,
             'd':0b1110011,
             'b':0b1100111,
             '+':0b1010000,
             'r':0b1000010,
             '-':0b1000000,
             ' ':0b0000000
             }

class TM1637:
    __doublePoint = False
    __Clkpin = 0
    __Datapin = 0
    __brightness = 1.0  # default to max brightness
    __currentData = [0, 0, 0, 0]

    def __init__(self, CLK, DIO, brightness):
        self.__Clkpin = CLK
        self.__Datapin = DIO
        self.__brightness = brightness
        IO.setup(self.__Clkpin, IO.OUT)
        IO.setup(self.__Datapin, IO.OUT)

    def cleanup(self):
        """Stop updating clock, turn off display, and cleanup GPIO"""
        self.StopClock()
        self.Clear()
        IO.cleanup()

    def Clear(self):
        b = self.__brightness
        point = self.__doublePoint
        self.__brightness = 0
        self.__doublePoint = False
        data = [0x7F, 0x7F, 0x7F, 0x7F]
        self.Show(data)
        # Restore previous settings:
        self.__brightness = b
        self.__doublePoint = point

    def ShowInt(self, i):
        s = str(i)
        self.Clear()
        for i in range(0, len(s)):
            self.Show1(i, int(s[i]))

    def Show(self, data):
        for i in range(0, 4):
            self.__currentData[i] = data[i]

        self.start()
        self.writeByte(ADDR_AUTO)
        self.br()
        self.writeByte(STARTADDR)
        for i in range(0, 4):
            self.writeByte(self.coding(data[i]))
        self.br()
        self.writeByte(0x88 + int(self.__brightness))
        self.stop()

    def Show1(self, DigitNumber, data):
        """show one Digit (number 0...3)"""
        if(DigitNumber < 0 or DigitNumber > 3):
            return  # error

        self.__currentData[DigitNumber] = data

        self.start()
        self.writeByte(ADDR_FIXED)
        self.br()
        self.writeByte(STARTADDR | DigitNumber)
        self.writeByte(self.coding(data))
        self.br()
        self.writeByte(0x88 + int(self.__brightness))
        self.stop()

    def SetBrightness(self, percent):
        """Accepts percent brightness from 0 - 1"""
        max_brightness = 7.0
        brightness = math.ceil(max_brightness * percent)
        if (brightness < 0):
            brightness = 0
        if(self.__brightness != brightness):
            self.__brightness = brightness
            self.Show(self.__currentData)

    def ShowDoublepoint(self, on):
        """Show or hide double point divider"""
        if(self.__doublePoint != on):
            self.__doublePoint = on
            self.Show(self.__currentData)

    def writeByte(self, data):
        for i in range(0, 8):
            IO.output(self.__Clkpin, IO.LOW)
            if(data & 0x01):
                IO.output(self.__Datapin, IO.HIGH)
            else:
                IO.output(self.__Datapin, IO.LOW)
            data = data >> 1
            IO.output(self.__Clkpin, IO.HIGH)

        # wait for ACK
        IO.output(self.__Clkpin, IO.LOW)
        IO.output(self.__Datapin, IO.HIGH)
        IO.output(self.__Clkpin, IO.HIGH)
        IO.setup(self.__Datapin, IO.IN)

        while(IO.input(self.__Datapin)):
            sleep(0.001)
            if(IO.input(self.__Datapin)):
                IO.setup(self.__Datapin, IO.OUT)
                IO.output(self.__Datapin, IO.LOW)
                IO.setup(self.__Datapin, IO.IN)
        IO.setup(self.__Datapin, IO.OUT)

    def start(self):
        """send start signal to TM1637"""
        IO.output(self.__Clkpin, IO.HIGH)
        IO.output(self.__Datapin, IO.HIGH)
        IO.output(self.__Datapin, IO.LOW)
        IO.output(self.__Clkpin, IO.LOW)

    def stop(self):
        IO.output(self.__Clkpin, IO.LOW)
        IO.output(self.__Datapin, IO.LOW)
        IO.output(self.__Clkpin, IO.HIGH)
        IO.output(self.__Datapin, IO.HIGH)

    def br(self):
        """terse break"""
        self.stop()
        self.start()

    def coding(self, data):
        if(self.__doublePoint):
            pointData = 0x80
        else:
            pointData = 0

        if(data == 0x7F):
            data = 0
        else:
            data = data + pointData
        return data

    def clock(self, military_time):
        """Clock script modified from:
            https://github.com/johnlr/raspberrypi-tm1637"""
        self.ShowDoublepoint(True)
        while (not self.__stop_event.is_set()):
            t = localtime()
            hour = t.tm_hour
            if not military_time:
                hour = 12 if (t.tm_hour % 12) == 0 else t.tm_hour % 12
            d0 = hour // 10 if hour // 10 else 0
            d1 = hour % 10
            d2 = t.tm_min // 10
            d3 = t.tm_min % 10
            digits = [d0, d1, d2, d3]
            self.Show(digits)
            # # Optional visual feedback of running alarm:
            # print digits
            # for i in tqdm(range(60 - t.tm_sec)):
            for i in range(60 - t.tm_sec):
                if (not self.__stop_event.is_set()):
                    sleep(1)

    def StartClock(self, military_time=True):
        # Stop event based on: http://stackoverflow.com/a/6524542/3219667
        self.__stop_event = threading.Event()
        self.__clock_thread = threading.Thread(
            target=self.clock, args=(military_time,))
        self.__clock_thread.start()

    def StopClock(self):
        try:
            print('Attempting to stop live clock')
            self.__stop_event.set()
        except:
            print('No clock to close')
    
    def print7seg(self, message):
        if len(message) is not 4:
            print(message + ' is not 4 signs long')
            return
        for c in message:
            if c not in dict7seg:
                dict7seg[c] = 0b1001001
        digits = [dict7seg[message[3]], dict7seg[message[2]], dict7seg[message[1]], dict7seg[message[0]]]
        self.Show(digits)

#if __name__ == "__main__":
#    display = TM1637(CLK=9, DIO=10, brightness=1.0)
#    display.Clear()
#    digits = [0x00, 0x01, 0x02, 0x03]
#    display.SetBrightness(1)
#    display.print7seg("L%03d" % 1)
#     """Confirm the display operation"""
#     display = TM1637(CLK=9, DIO=10, brightness=1.0)

#     display.Clear()

#     digits = [0x00, 0x01, 0x02, 0x03]
#     display.SetBrightness(1)
#     display.Show(digits)
#     print('1234  - Working? (Press Key)')
#     for i in range(0,255):
#         digits = [i % 255, (i << 2) % 255, (i << 2) % 255, ~i % 255]
#         display.Show(digits)
#         sleep(0.1)

#     print('Updating one digit at a time:')
#     display.Clear()
#     display.Show1(1, 0b1000)
#     sleep(0.5)
#     display.Show1(2, 0b100)
#     sleep(0.5)
#     display.Show1(3, 0b10)
#     sleep(0.5)
#     display.Show1(0, 0b1)
#     print('4321  - (Press Key)')
#     sleep(5)

#     print('Add double point\n')
#     display.ShowDoublepoint(True)
#     sleep(0.2)
#     print('Brightness Off')
#     display.SetBrightness(0)
#     sleep(0.5)
#     print('Full Brightness')
#     display.SetBrightness(1)
#     sleep(0.5)
#     print('30% Brightness')
#     display.SetBrightness(0.3)
#     sleep(0.3)


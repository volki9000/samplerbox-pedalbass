#!/usr/bin/python3
#  SamplerBox
#
#  author:    Joseph Ernest (twitter: @JosephErnest, mail: contact@samplerbox.org)
#  url:       http://www.samplerbox.org/
#  license:   Creative Commons ShareAlike 3.0 (http://creativecommons.org/licenses/by-sa/3.0/)
#
#  samplerbox.py: Main file
#


#########################################
# LOCAL
# CONFIG
#########################################

from contextlib import redirect_stdout

def writeToLog(string):
    with open('/home/pi/sbox.log', 'a') as f:
        with redirect_stdout(f):
            print(string)

from datetime import datetime

now = datetime.now()

current_time = now.strftime("%d/%m/%Y %H:%M:%S")
writeToLog("Starting samplerbox.py at " + str(current_time))

AUDIO_DEVICE_ID = 0                    # change this number to use another soundcard
SAMPLES_DIR = "/home/pi/samples/"   # The root directory containing the sample-sets. Example: "/media/" to look for samples on a USB stick / SD card
USE_SERIALPORT_MIDI = False             # Set to True to enable MIDI IN via SerialPort (e.g. RaspberryPi's GPIO UART pins)
USE_I2C_7SEGMENTDISPLAY = True          # Set to True to use a 7-segment display via I2C
USE_BUTTONS = True                     # Set to True to use momentary buttons (connected to RaspberryPi's GPIO pins) to change preset
MAX_POLYPHONY = 13                      # This can be set higher, but 80 is a safe value
DEBOUNCE_SECS = 0.15

#########################################
# 7-SEGMENT DISPLAY
#
#########################################

# 7-Segment display using TM1637

import tm1637

display = tm1637.TM1637(CLK=10, DIO=9, brightness=1.0)
display.Clear()
digits = [0x00, 0x01, 0x02, 0x03]
display.SetBrightness(1)

#########################################
# IMPORT
# MODULES
#########################################

import wave
import time
import numpy
import os
import re
import sounddevice
import threading
from chunk import Chunk
import struct
import samplerbox_audio
import RPi.GPIO as GPIO

#########################################
# SLIGHT MODIFICATION OF PYTHON'S WAVE MODULE
# TO READ CUE MARKERS & LOOP MARKERS
#########################################

class waveread(wave.Wave_read):

    def initfp(self, file):
        self._convert = None
        self._soundpos = 0
        self._cue = []
        self._loops = []
        self._ieee = False
        self._file = Chunk(file, bigendian=0)
        if self._file.getname() != b'RIFF':
            raise Exception('file does not start with RIFF id but ' + str(self._file.getname()))
        if self._file.read(4) != b'WAVE':
            raise Exception('not a WAVE file')
        self._fmt_chunk_read = 0
        self._data_chunk = None
        while 1:
            self._data_seek_needed = 1
            try:
                chunk = Chunk(self._file, bigendian=0)
            except EOFError:
                break
            chunkname = chunk.getname()
            if chunkname == b'fmt ':
                self._read_fmt_chunk(chunk)
                self._fmt_chunk_read = 1
            elif chunkname == b'data':
                if not self._fmt_chunk_read:
                    raise Exception('data chunk before fmt chunk')
                self._data_chunk = chunk
                self._nframes = chunk.chunksize // self._framesize
                self._data_seek_needed = 0
            elif chunkname == b'cue ':
                numcue = struct.unpack(b'<i', chunk.read(4))[0]
                for i in range(numcue):
                    id, position, datachunkid, chunkstart, blockstart, sampleoffset = struct.unpack(b'<iiiiii', chunk.read(24))
                    self._cue.append(sampleoffset)
            elif chunkname == b'smpl':
                manuf, prod, sampleperiod, midiunitynote, midipitchfraction, smptefmt, smpteoffs, numsampleloops, samplerdata = struct.unpack(
                    b'<iiiiiiiii', chunk.read(36))
                for i in range(numsampleloops):
                    cuepointid, type, start, end, fraction, playcount = struct.unpack(b'<iiiiii', chunk.read(24))
                    self._loops.append([start, end])
            chunk.skip()
        if not self._fmt_chunk_read or not self._data_chunk:
            raise Exception('fmt chunk and/or data chunk missing')

    def getmarkers(self):
        return self._cue

    def getloops(self):
        return self._loops


#########################################
# MIXER CLASSES
#
#########################################

class PlayingSound:

    def __init__(self, sound, note):
        self.sound = sound
        self.pos = 0
        self.fadeoutpos = 0
        self.isfadeout = False
        self.note = note

    def fadeout(self):
        if self.sound.playbackMode == 1:
            self.isfadeout = True

    def stop(self):
        try:
            playingsounds.remove(self)
        except:
            pass


class Sound:

    def __init__(self, filename, midinote, velocity, playbackMode):
        wf = waveread(filename)
        self.fname = filename
        self.midinote = midinote
        self.velocity = velocity
        self.playbackMode = playbackMode
        if wf.getloops():
            self.loop = wf.getloops()[0][0]
            self.nframes = wf.getloops()[0][1] + 2
        else:
            self.loop = -1
            self.nframes = wf.getnframes()

        self.data = self.frames2array(wf.readframes(self.nframes), wf.getsampwidth(), wf.getnchannels())

        wf.close()

    def play(self, note):
        snd = PlayingSound(self, note)
        playingsounds.append(snd)
        return snd

    def frames2array(self, data, sampwidth, numchan):
        if sampwidth == 2:
            npdata = numpy.fromstring(data, dtype=numpy.int16)
        elif sampwidth == 3:
            npdata = samplerbox_audio.binary24_to_int16(data, len(data)/3)
        if numchan == 1:
            npdata = numpy.repeat(npdata, 2)
        return npdata

FADEOUTLENGTH = 200000
FADEOUT = numpy.linspace(1., 0., FADEOUTLENGTH)            # by default, float64
FADEOUT = numpy.power(FADEOUT, 6)
FADEOUT = numpy.append(FADEOUT, numpy.zeros(FADEOUTLENGTH, numpy.float32)).astype(numpy.float32)
SPEED = numpy.power(2, numpy.arange(0.0, 84.0)/12).astype(numpy.float32)

samples = {}
playingnotes = {}
sustainplayingnotes = []
sustain = True
playingsounds = []
last_played_per_note = [0] * MAX_POLYPHONY
note_active = [0] * MAX_POLYPHONY
globalvolume = 10 ** (-12.0/20)  # -12dB default global volume
globaltranspose = 0


#########################################
# AUDIO AND MIDI CALLBACKS
#
#########################################

def AudioCallback(outdata, frame_count, time_info, status):
    global playingsounds
    rmlist = []
    playingsounds = playingsounds[-MAX_POLYPHONY:]
    b = samplerbox_audio.mixaudiobuffers(playingsounds, rmlist, frame_count, FADEOUT, FADEOUTLENGTH, SPEED)
    for e in rmlist:
        try:
            playingsounds.remove(e)
        except:
            pass
    b *= globalvolume
    outdata[:] = b.reshape(outdata.shape)

def PlayNoteCallback(midinote, state, event_time):
#    print("playing" + str(midinote))
    global playingnotes, sustain, sustainplayingnotes
    global presetIndex
    velocity = 127
    
    if event_time - last_played_per_note[midinote] > DEBOUNCE_SECS:
        if state == True:
            last_played_per_note[midinote] = event_time
        midinote += globaltranspose
        try:
            if state == True and not note_active[midinote]:
                playingnotes[midinote] = samples[midinote, velocity].play(midinote)
            else:
                playingnotes[midinote].fadeout()
                del playingnotes[midinote]
        except:
            pass
    note_active[midinote] = state

#########################################
# LOAD SAMPLES
#
#########################################

LoadingThread = None
LoadingInterrupt = False


def LoadSamples():
    global LoadingThread
    global LoadingInterrupt

    if LoadingThread:
        LoadingInterrupt = True
        LoadingThread.join()
        LoadingThread = None

    LoadingInterrupt = False
    LoadingThread = threading.Thread(target=ActuallyLoad)
    LoadingThread.daemon = True
    LoadingThread.start()

NOTES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]

def ActuallyLoad():
    try:
        global presetIndex
        global samples
        global playingsounds
        global globalvolume, globaltranspose
        playingsounds = []
        samples = {}
        globalvolume = 10 ** (-12.0/20)  # -12dB default global volume
        globaltranspose = 0

        samplesdir = SAMPLES_DIR if os.listdir(SAMPLES_DIR) else '.'      # use current folder (containing 0 Saw) if no user media containing samples has been found

        basename = next((f for f in os.listdir(samplesdir) if f.startswith("%d " % presetIndex)), None)      # or next(glob.iglob("blah*"), None)
        if basename:
            dirname = os.path.join(samplesdir, basename)
        if not basename:
            writeToLog('Preset empty: %s' % presetIndex)
            display.print7seg("E%03d" % presetIndex)
            return
        writeToLog('Preset loading: %s (%s)' % (presetIndex, basename))
        display.print7seg("L%03d" % presetIndex)

        definitionfname = os.path.join(dirname, "definition.txt")
        print('Loading def=' + definitionfname)
        if os.path.isfile(definitionfname):
            with open(definitionfname, 'r') as definitionfile:
                for i, entry in enumerate(definitionfile):
                    m = re.match('(?:volume=)(?P<volume>-*\d)', entry)
                    if m:
                        presetVolume = int(m.groupdict().get('volume', 0))-12
                        globalvolume = 10 ** (presetVolume/20)
                        continue
                    try:
                        defaultparams = {'midinote': '0', 'velocity': '127', 'notename': '', 'mode': '0'}
                        pattern = '(?P<midinote>\d*)_(?P<mode>\d*)\.wav'
                        for fname in os.listdir(dirname):
                            m = re.match(pattern, fname)
                            if m:
                                info = m.groupdict()
                                midinote = int(info.get('midinote', defaultparams['midinote']))
                                velocity = int(info.get('velocity', defaultparams['velocity']))
                                notename = info.get('notename', defaultparams['notename'])
                                mode = int(info.get('mode', defaultparams['mode']))
                                if notename:
                                    midinote = NOTES.index(notename[:-1].lower()) + (int(notename[-1])+2) * 12
                                samples[midinote, velocity] = Sound(os.path.join(dirname, fname), midinote, velocity, mode)
                    except:
                        print("Error in definition file, skipping line %s." % (i+1))

        else:
            for midinote in range(0, 127):
                if LoadingInterrupt:
                    return
                file = os.path.join(dirname, "%d.wav" % midinote)
                if os.path.isfile(file):
                    samples[midinote, 127] = Sound(file, midinote, 127, 0)

        initial_keys = set(samples.keys())
        for midinote in range(128):
            lastvelocity = None
            for velocity in range(128):
                if (midinote, velocity) not in initial_keys:
                    samples[midinote, velocity] = lastvelocity
                else:
                    if not lastvelocity:
                        for v in range(velocity):
                            samples[midinote, v] = samples[midinote, velocity]
                    lastvelocity = samples[midinote, velocity]
            if not lastvelocity:
                for velocity in range(128):
                    try:
                        samples[midinote, velocity] = samples[midinote-1, velocity]
                    except:
                        pass
        if len(initial_keys) > 0:
            writeToLog('Preset loaded: ' + str(presetIndex))
            display.print7seg("P%03d" % presetIndex)
        else:
            writeToLog('Preset empty: ' + str(presetIndex))
            display.print7seg("E%03d" % presetIndex)
    except BaseException as e:
        writeToLog('Failed in ActuallyLoad(): ' + e)


#########################################
# OPEN AUDIO DEVICE
#
#########################################

try:
    sd = sounddevice.OutputStream(device=AUDIO_DEVICE_ID, blocksize=512, samplerate=44100, channels=2, dtype='int16', callback=AudioCallback)
    sd.start()
    writeToLog('Opened audio device #%i' % AUDIO_DEVICE_ID)
except:
    writeToLog('Invalid audio device #%i' % AUDIO_DEVICE_ID)
    exit(1)

#########################################
# BUTTONS THREAD (RASPBERRY PI GPIO)
#
#########################################
presetIndex = 0
if USE_BUTTONS:
    import numato_gpio as numato
    lastbuttontime = 0

    writeToLog('Attempting to open Numato GPIO')
    numato_serial_fd = '/dev/ttyACM0'
    display.print7seg('1n1+')
    dev = numato.NumatoUsbGpio(numato_serial_fd)
    writeToLog('Successfully opened Numato GPIO')

# TODO seperate threads for buttons and keys? Keys could get higher sample rate
    def Buttons():
        try:
            # Keys C-E
            GPIO.setup(26, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(17, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(7, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(8, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(25, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            # Utility switches
            GPIO.setup(14, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(15, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(23, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(22, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            dev.setup(0, numato.IN)
            dev.setup(1, numato.IN)
            dev.setup(2, numato.IN)
            dev.setup(3, numato.IN)
            dev.setup(4, numato.IN)
            dev.setup(5, numato.IN)
            dev.setup(6, numato.IN)
            dev.setup(7, numato.IN)

            global presetIndex, lastbuttontime, globalvolume
            lastbuttontime = time.time()
            last_played = []
            while True:
                now = time.time()
                upperKeyMask = dev.readall()
                # Previous preset
                if not GPIO.input(15):
                    lastbuttontime = now
                    presetIndex -= 1
                    if presetIndex < 0:
                        presetIndex = 127
                    display.print7seg('LdIn')
                    LoadSamples()
                    time.sleep(0.2)
                # Next preset
                elif not GPIO.input(14):
                    lastbuttontime = now
                    presetIndex += 1
                    if presetIndex > 127:
                        presetIndex = 0
                    display.print7seg('LdIn')
                    LoadSamples()
                    time.sleep(0.2)
                # Volume down
                elif not GPIO.input(22):
                    lastbuttontime = now

                    display.print7seg('db -')
                    globalvolume *= 10 ** (-3.0 / 20)
                    time.sleep(0.5)
                    display.print7seg("P%03d" % presetIndex)
                # Volume up
                elif not GPIO.input(23):
                    lastbuttontime = now
                    display.print7seg('db+r')
                    globalvolume *= 10 ** (3.0 / 20)
                    time.sleep(0.5)
                    display.print7seg("P%03d" % presetIndex)
                # Panic
                elif not GPIO.input(4):
                    lastbuttontime = now
                    display.print7seg('PnIC')
                    playingnotes.clear()
                    playingsounds.clear()
                    time.sleep(0.5)
                    display.print7seg("P%03d" % presetIndex)

                # Note Ons
                # C - B1
                if not GPIO.input(26):
                    #display.print7seg('C  1')
                    lastbuttontime = now
                    PlayNoteCallback(0, True, now)
                # C# - C1
                if not GPIO.input(17):
                    #display.print7seg('C+ 1')
                    lastbuttontime = now
                    PlayNoteCallback(1, True, now)
                # D - B2
                if not GPIO.input(7):
                    #display.print7seg('d  1')
                    lastbuttontime = now
                    PlayNoteCallback(2, True, now)
                # D# - C2
                if not GPIO.input(8):
                    #display.print7seg('d+ 1')
                    lastbuttontime = now
                    PlayNoteCallback(3, True, now)
                # E - A1
                if not GPIO.input(25):
                    #display.print7seg('E  1')
                    lastbuttontime = now
                    PlayNoteCallback(4, True, now)
                # F - A2
                if not upperKeyMask & 1 > 0:
                    #display.print7seg('E+ 1')
                    lastbuttontime = now
                    PlayNoteCallback(5, True, now)
                # F# - C3
                if not upperKeyMask & 2 > 0:
                    #display.print7seg('E++1')
                    lastbuttontime = now
                    PlayNoteCallback(6, True, now)
                # G - B3
                if not upperKeyMask & 4 > 0:
                    #display.print7seg('L  1')
                    lastbuttontime = now
                    PlayNoteCallback(7, True, now)
                # G# - C4
                if not upperKeyMask & 8 > 0:
                    #display.print7seg('L+ 1')
                    lastbuttontime = now
                    PlayNoteCallback(8, True, now)
                # A - B4
                if not upperKeyMask & 16 > 0:
                    #display.print7seg('0  1')
                    lastbuttontime = now
                    PlayNoteCallback(9, True, now)
                # A# - C5
                if not upperKeyMask & 32 > 0:
                    #display.print7seg('0+ 1')
                    lastbuttontime = now
                    PlayNoteCallback(10, True, now)
                # B - B5
                if not upperKeyMask & 64 > 0:
                    #display.print7seg('b  1')
                    lastbuttontime = now
                    PlayNoteCallback(11, True, now)
                # C - C6
                if not upperKeyMask & 128 > 0:
                    #display.print7seg('C  2')
                    lastbuttontime = now
                    PlayNoteCallback(12, True, now)

                # Note Offs
                # C
                if GPIO.input(26):
                    lastbuttontime = now
                    PlayNoteCallback(0, False, now)
                # C#
                if GPIO.input(17):
                    lastbuttontime = now
                    PlayNoteCallback(1, False, now)
                # D
                if GPIO.input(7):
                    lastbuttontime = now
                    PlayNoteCallback(2, False, now)
                # D#
                if GPIO.input(8):
                    lastbuttontime = now
                    PlayNoteCallback(3, False, now)
                # E
                if GPIO.input(25):
                    lastbuttontime = now
                    PlayNoteCallback(4, False, now)
                # F
                if upperKeyMask & 1 > 0:
                    lastbuttontime = now
                    PlayNoteCallback(5, False, now)
                # F#
                if upperKeyMask & 2 > 0:
                    lastbuttontime = now
                    PlayNoteCallback(6, False, now)
                # G
                if upperKeyMask & 4 > 0:
                    lastbuttontime = now
                    PlayNoteCallback(7, False, now)
                # G#
                if upperKeyMask & 8 > 0:
                    lastbuttontime = now
                    PlayNoteCallback(8, False, now)
                # A
                if upperKeyMask & 16 > 0:
                    lastbuttontime = now
                    PlayNoteCallback(9, False, now)
                # A#
                if upperKeyMask & 32 > 0:
                    lastbuttontime = now
                    PlayNoteCallback(10, False, now)
                # B
                if upperKeyMask & 64 > 0:
                    lastbuttontime = now
                    PlayNoteCallback(11, False, now)
                # C
                if upperKeyMask & 128 > 0:
                    lastbuttontime = now
                    PlayNoteCallback(12, False, now)
        except  BaseException as e:
            writeToLog('Failed in Buttons(): ' + str(e))
    ButtonsThread = threading.Thread(target=Buttons)
    ButtonsThread.daemon = True
    ButtonsThread.start()


#########################################
# LOAD FIRST SOUNDBANK
#
#########################################


LoadSamples()

def onShutdown():
    display.print7seg('1n1+')

import atexit

atexit.register(onShutdown)

while True:
    time.sleep(0.5)

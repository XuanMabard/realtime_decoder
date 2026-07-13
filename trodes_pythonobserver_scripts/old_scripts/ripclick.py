import math
import struct
import re
import time
import random
import numpy as np
import pyaudio
import wave

def makewhitenoise():  #play white noise for duration of lockout


    soundlength = int(44100/7)
    p = pyaudio.PyAudio()
    stream = p.open(format = 8, channels = 1, rate = 44100, output = True)
    whitenoise = np.random.randint(700,size = soundlength)
    data = struct.pack("%dh"%(len(whitenoise)), *list(whitenoise))    
    stream.write(data)
    stream.close()
    p.terminate()

def callback(line):
    if line.find("Executing trigger function 22") >= 0:  # ripple has been detected
	    makewhitenoise()

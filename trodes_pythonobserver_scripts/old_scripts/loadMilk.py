import math
import struct
import re
import time

def pokeIn(dio):
    global armWells
    global armPumps
    global sleepWells
    global sleepPumps
    global onTrack
    currWell = int(dio[1])
    for num in range(len(armWells)):
        if currWell == armWells[num]:
            onTrack=1
            print("SCQTMESSAGE: rewardWell = "+str(armPumps[num])+"\n")
            print("SCQTMESSAGE: trigger(1);\n")
    for num in range(len(sleepWells)):
        if currWell == sleepWells[num] and onTrack==0:
            print("SCQTMESSAGE: rewardWell = "+str(sleepPumps[num])+"\n")
            print("SCQTMESSAGE: trigger(1);\n")

# This function MUST BE NAMED 'callback'!!!!
def callback(line):
    # This is the custom callback function. When events occur, addScQtEvent will
    # call this function.
    if line.find("UP") >= 0: #input triggered
        pokeIn(re.findall(r'\d+',line))

#w-track arms wells
armWells = [23, 25, 18, 1, 3, 5]  

#w-track arm pumps:
armPumps = [22, 20, 17, 2, 4, 6]   

#sleep box wells:
sleepWells = [13, 11, 9, 7]   

#sleep box pumps:
sleepPumps = [14, 12, 10, 8]    

#doors:
sleepDoors = [28, 29, 27, 31]    
trackDoor = 26   
boxDoors = [19, 21]   

#global variables
onTrack = 0


#initialize track and start with whichAn
for num in sleepWells:
        print("SCQTMESSAGE: dio = "+str(num)+"\n")
        print("SCQTMESSAGE: trigger(3);\n")

for num in armWells:
        print("SCQTMESSAGE: dio = "+str(num)+"\n")
        print("SCQTMESSAGE: trigger(3);\n")

for num in sleepDoors:
        print("SCQTMESSAGE: dio = "+str(num)+"\n")
        print("SCQTMESSAGE: trigger(3);\n")

print("SCQTMESSAGE: dio = "+str(trackDoor)+"\n")
print("SCQTMESSAGE: trigger(3);\n")

for num in boxDoors:
        print("SCQTMESSAGE: dio = "+str(num)+"\n")
        print("SCQTMESSAGE: trigger(3);\n")

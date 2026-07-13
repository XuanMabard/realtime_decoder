import math
import struct
import re
import time
from tkinter import *
import smtplib

def pokeIn(dio):
    global armWells
    global sleepWells
    currWell = int(dio[1])
    for num in range(len(armWells)):
        if currWell == armWells[num]:
            print("SCQTMESSAGE: holdTime = clock()\n")
            doTrack(num)
    for num in range(len(sleepWells)):
        if currWell == sleepWells[num]:
            print("SCQTMESSAGE: holdTime = clock()\n")
            doSleep(num)

def pokeOut(dio):
    global armWells
    global sleepWells
    global maxTime
    global trackTime
    global reset
    global anIndex
    global whichAn
    global Animals
    currWell = int(dio[1])
    for num in range(len(armWells)):
        if currWell == armWells[num]:
            endTrack(num)
    for num in range(len(sleepWells)):
        if currWell == sleepWells[num]:
            endSleep(num)
    if(reset and round(time.time()-trackTime)>(maxTime*60)):
        endSession()
        print("SCQTMESSAGE: timeOut = 1;\n")
        print("SCQTMESSAGE: disp(timeOut);\n")
        print("SCQTMESSAGE: timeOut = 0;\n")

def doTrack(val):
    global armWells
    global armPumps
    global lastArm
    global totRewards
    global onTrack
    global whichAn
    global timeNow
    global timeElapsed
    global Animals
    global trackTime
    global reset
    if lastArm != val and onTrack == 1:
        if totRewards == 0 and onTrack == 1:
            print("SCQTMESSAGE: dio = "+str(trackDoor)+"\n")
            print("SCQTMESSAGE: trigger(3);\n")
            timeElapsed=round(time.time()-timeNow)
            print("SCQTMESSAGE: timeElapsed = "+str(timeElapsed)+"\n")
            print("SCQTMESSAGE: disp(timeElapsed);\n")
            trackTime=time.time()
            reset=1
        lastArm = val
        totRewards+=1
        deliverReward(val)

def deliverReward(val):
    global armPumps
    global Animals
    global whichAn
    global anIndex
    global session
    global totRewards
    print("SCQTMESSAGE: rewardWell = "+str(armPumps[val])+";\n")
    print("SCQTMESSAGE: trigger(1);\n")

    print("SCQTMESSAGE: totRewards = "+str(totRewards)+"\n")
    print("SCQTMESSAGE: animal = "+str(Animals[whichAn])+"\n")
    print("SCQTMESSAGE: session = "+str(session)+"\n")
    print("SCQTMESSAGE: timeCheck = clock()\n")
    print("SCQTMESSAGE: trigger(7);\n")

def endTrack(val):
    global totRewards
    global maxRewards
    global onTrack
    if totRewards == maxRewards and onTrack == 1:
        endSession()
        print("SCQTMESSAGE: disp(timeOut);\n")

def endSession():
    global armWells
    global totRewards
    global maxRewards
    global onTrack
    global sleepRewards
    global reset
    onTrack = 0
    print("SCQTMESSAGE: dio = "+str(trackDoor)+"\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: dio = "+str(sleepDoors[whichAn])+"\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: dio = "+str(boxDoors[math.floor(whichAn/len(boxDoors))])+"\n")
    print("SCQTMESSAGE: trigger(2);\n")
    for num in armWells:
        print("SCQTMESSAGE: dio = "+str(num)+"\n")
        print("SCQTMESSAGE: trigger(3);\n")
    print("SCQTMESSAGE: dio = "+str(sleepWells[whichAn])+"\n")
    print("SCQTMESSAGE: trigger(2);\n")
    sleepRewards = 0
    reset = 0

def doSleep(val):
    global sleepDoors
    global sleepPumps
    global sleepRewards
    global maxSleep
    global whichAn
    global onTrack
    if sleepRewards == 0 and val == whichAn and onTrack == 0:
#        print("SCQTMESSAGE: dio = "+str(trackDoor)+"\n")
#        print("SCQTMESSAGE: trigger(3);\n")
        print("SCQTMESSAGE: dio = "+str(sleepDoors[whichAn])+"\n")
        print("SCQTMESSAGE: trigger(3);\n")
        print("SCQTMESSAGE: dio = "+str(boxDoors[math.floor(whichAn/len(boxDoors))])+"\n")
        print("SCQTMESSAGE: trigger(3);\n")
    if sleepRewards < maxSleep and val == whichAn and onTrack == 0:
        print("SCQTMESSAGE: rewardWell = "+str(sleepPumps[whichAn])+"\n")
        print("SCQTMESSAGE: timeCheck = clock()\n")
        print("SCQTMESSAGE: trigger(1);\n")
        sleepRewards+=1

def endSleep(val):
    global sleepDoors
    global sleepPumps
    global sleepRewards
    global maxSleep
    global totRewards
    global whichAn
    global onTrack
    global session
    global timeNow
    global lastArm
    global maxSessions
    if sleepRewards == maxSleep and val == whichAn and onTrack == 0:
        print("SCQTMESSAGE: dio = "+str(sleepWells[whichAn])+"\n")
        print("SCQTMESSAGE: trigger(3);\n")
        totRewards = 0
        lastArm = -1
        whichAn += 1
        session += math.floor(whichAn/len(sleepDoors))
        whichAn = (whichAn % len(sleepDoors))
        print("SCQTMESSAGE: transition = 1\n")
        print("SCQTMESSAGE: animal = "+str(Animals[whichAn])+"\n")
        if session > maxSessions:
            print("SCQTMESSAGE: stop = 1\n")
        else:
            onTrack = 1
            print("SCQTMESSAGE: trigger(5);\n")
        for num in armWells:
            print("SCQTMESSAGE: dio = "+str(num)+"\n")
            print("SCQTMESSAGE: trigger(2);\n")
        print("SCQTMESSAGE: dio = "+str(trackDoor)+"\n")
        print("SCQTMESSAGE: trigger(2);\n")
        print("SCQTMESSAGE: dio = "+str(sleepDoors[whichAn])+"\n")
        print("SCQTMESSAGE: trigger(2);\n")
        print("SCQTMESSAGE: dio = "+str(boxDoors[math.floor(whichAn/len(boxDoors))])+"\n")
        print("SCQTMESSAGE: trigger(2);\n")
        print("SCQTMESSAGE: transition = 0\n")
        timeNow=time.time()

# This function MUST BE NAMED 'callback'!!!!
def callback(line):

    # This is the custom callback function. When events occur, addScQtEvent will
    # call this function.
    if line.find("UP") >= 0: #input triggered
        pokeIn(re.findall(r'\d+',line))

    if line.find("DOWN") >= 0: #input released
        pokeOut(re.findall(r'\d+',line))

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
lastArm = -1
totRewards = 0
maxRewards = 80
onTrack = 1
whichAn=0
sleepRewards = 0
maxSleep = 5
session=1
timeElapsed=0
maxSessions=3
timeNow=0
messageSent=0
trackTime=0
maxTime=15
reset=0

print("SCQTMESSAGE: timeOut = 0;\n")

#Animal numbers, to be update for each set of animals
Animals=[1, 2, 3, 4]

def finish():
    global session
    global Animals
    global whichAn
    global sleepWells
    global sleepPumps
    global sleepDoors
    global armWells
    global transition
    global trackDoor
    global boxDoors
    global maxSessions
    global maxRewards
    global timeNow
    global maxTime
    whichAn=var.get()
    Animals[0]=int(E1.get())
    Animals[1]=int(E2.get())
    Animals[2]=int(E3.get())
    Animals[3]=int(E4.get())
    if Animals[3]<0:
        sleepWells = [29, 30, 31]
        sleepPumps = [8, 9, 10]
        sleepDoors = [1, 2, 3]
    if Animals[2]<0:
        sleepWells = [29, 30]
        sleepPumps = [8, 9]
        sleepDoors = [1, 2]
    session=int(E5.get())
    maxRewards=int(E6.get())
    maxSessions=int(E7.get())
    maxTime=int(E8.get())
    display.destroy()

    for num in sleepWells:
        print("SCQTMESSAGE: dio = "+str(num)+"\n")
        print("SCQTMESSAGE: trigger(3);\n")

    for num in armWells:
        print("SCQTMESSAGE: dio = "+str(num)+"\n")
        print("SCQTMESSAGE: trigger(2);\n")

    print("SCQTMESSAGE: stop = 0\n")
    print("SCQTMESSAGE: transition = 1\n")
    print("SCQTMESSAGE: dio = "+str(sleepDoors[whichAn])+"\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: dio = "+str(trackDoor)+"\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: dio = "+str(boxDoors[math.floor(whichAn/len(boxDoors))])+"\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: animal = "+str(Animals[whichAn])+"\n")
    print("SCQTMESSAGE: trigger(5);\n")
    print("SCQTMESSAGE: transition = 0\n")
    timeNow=time.time()

savingDisp = Tk()

advance=0

def yesSaving():
    global advance
    savingDisp.destroy()
    advance=1

def noSaving():
    savingDisp.destroy()

saveFrame1 = Frame(savingDisp)
saveFrame1.pack(side = TOP)

saveFrame2 = Frame(savingDisp)
saveFrame2.pack(side = BOTTOM)

LS0 = Label(saveFrame1, text="have you saved your data?")
LS0.pack()

B1 = Button(saveFrame2, text ="Yes", command = yesSaving)
B1.pack(side = LEFT)

B2 = Button(saveFrame2, text ="No", command = noSaving)
B2.pack(side = LEFT)

savingDisp.mainloop()

if advance:
    display = Tk()

    frame1 = Frame(display)
    frame1.pack(side = TOP)

    frame2 = Frame(display)
    frame2.pack(side = TOP)

    frame3 = Frame(display)
    frame3.pack( side = TOP )

    frame4 = Frame(display)
    frame4.pack( side = TOP )

    frame5 = Frame(display)
    frame5.pack( side = TOP )

    frame6 = Frame(display)
    frame6.pack( side = TOP )

    frame7 = Frame(display)
    frame7.pack( side = TOP )

    frame8 = Frame(display)
    frame8.pack( side = TOP )

    frame9 = Frame(display)
    frame9.pack( side = BOTTOM )

    L0 = Label(frame1, text="animal located in:")
    L0.pack()

    L1 = Label(frame2, text="box 1 is")
    L1.pack( side = LEFT)
    E1 = Entry(frame2, bd = 3, width = 3)
    E1.pack(side = LEFT)
    E1.insert(0,str(Animals[0]))

    L2 = Label(frame2, text="box 2 is")
    L2.pack( side = LEFT)
    E2 = Entry(frame2, bd = 3, width = 3)
    E2.pack(side = LEFT)
    E2.insert(0,str(Animals[1]))

    L3 = Label(frame3, text="box 3 is")
    L3.pack( side = LEFT)
    E3 = Entry(frame3, bd = 3, width = 3)
    E3.pack(side = LEFT)
    E3.insert(0,str(Animals[2]))

    L4 = Label(frame3, text="box 4 is")
    L4.pack( side = LEFT)
    E4 = Entry(frame3, bd = 3, width = 3)
    E4.pack(side = LEFT)
    E4.insert(0,str(Animals[3]))

    var = IntVar()
    R1 = Radiobutton(frame4, text="start box 1", variable=var, value=0)
    R1.pack( anchor = W )

    R2 = Radiobutton(frame4, text="start box 2", variable=var, value=1)
    R2.pack( anchor = W )

    R3 = Radiobutton(frame4, text="start box 3", variable=var, value=2)
    R3.pack( anchor = W)

    R4 = Radiobutton(frame4, text="start box 4", variable=var, value=3)
    R4.pack( anchor = W)

    L5 = Label(frame5, text="session #")
    L5.pack( side = LEFT)
    E5 = Entry(frame5, bd = 3, width = 3)
    E5.pack(side = LEFT)
    E5.insert(0,str(session))

    L6 = Label(frame6, text="max reward #")
    L6.pack( side = LEFT)
    E6 = Entry(frame6, bd = 3, width = 3)
    E6.pack(side = LEFT)
    E6.insert(0,str(maxRewards))

    L7 = Label(frame7, text="max session #")
    L7.pack( side = LEFT)
    E7 = Entry(frame7, bd = 3, width = 3)
    E7.pack(side = LEFT)
    E7.insert(0,str(maxSessions))

    L8 = Label(frame8, text="max time (min)")
    L8.pack(side = LEFT)
    E8 = Entry(frame8, bd = 3, width = 3)
    E8.pack(side = LEFT)
    E8.insert(0,str(maxTime))

    B = Button(frame9, text ="Go", command = finish)

    B.pack(side = BOTTOM)

    display.mainloop()

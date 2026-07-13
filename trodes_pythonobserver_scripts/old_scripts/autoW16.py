import math
import struct
import re
import time
import numpy as np
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
    global wArms
    global armPumps
    global lastArm
    global lastOuter
    global homeRewards
    global outerRewards
    global onTrack
    global whichAn
    global anIndex
    global timeNow
    global timeElapsed
    global Animals
    global trackTime
    global reset
    global trackDoor
    global cenRew
    if lastArm == -1 and onTrack == 1:
        print("SCQTMESSAGE: dio = "+str(trackDoor)+";\n")
        print("SCQTMESSAGE: trigger(3);\n")
        timeElapsed=round(time.time()-timeNow)
        print("SCQTMESSAGE: timeElapsed = "+str(timeElapsed)+";\n")
        print("SCQTMESSAGE: disp(timeElapsed);\n")
        trackTime=time.time()
        reset=1
    if lastArm != val and onTrack == 1:
        if val == (wArms[1]-1):
            homeRewards+=1
            if cenRew:
                deliverReward(val)
        if val == (wArms[0]-1) or val == (wArms[2]-1):
            if val != lastOuter and lastArm == (wArms[1]-1):
                outerRewards+=1
                deliverReward(val)
            lastOuter=val
    lastArm = val
        

def deliverReward(val):
    global armPumps
    global Animals
    global whichAn
    global anIndex
    global session
    global homeRewards
    global outerRewards
    print("SCQTMESSAGE: rewardWell = "+str(armPumps[val])+";\n")
    print("SCQTMESSAGE: trigger(1);\n")

    print("SCQTMESSAGE: homeRewards = "+str(homeRewards)+";\n")
    print("SCQTMESSAGE: outerRewards = "+str(outerRewards)+";\n")
    print("SCQTMESSAGE: animal = "+str(Animals[whichAn[anIndex]])+";\n")
    print("SCQTMESSAGE: session = "+str(session)+";\n")
    print("SCQTMESSAGE: timeCheck = clock()\n")
    print("SCQTMESSAGE: trigger(4);\n")

def endTrack(val):
    global armWells
    global wArms
    global homeRewards
    global whichAn
    global anIndex
    global maxTrials
    global onTrack
    global sleepRewards

    if homeRewards == maxTrials and onTrack == 1 and lastArm != (wArms[1]-1):
        endSession()
        print("SCQTMESSAGE: disp(timeOut);\n")
        

def endSession():
    global trackDoor
    global sleepDoors
    global boxDoors
    global whichAn
    global anIndex
    global armWells
    global sleepWells
    global sleepRewards
    global onTrack
    global reset
    
    onTrack = 0
    print("SCQTMESSAGE: dio = "+str(trackDoor)+";\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: dio = "+str(sleepDoors[whichAn[anIndex]])+";\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: dio = "+str(boxDoors[math.floor(whichAn[anIndex]/len(boxDoors))])+";\n")
    print("SCQTMESSAGE: trigger(2);\n")
    for num in armWells:
        print("SCQTMESSAGE: dio = "+str(num)+";\n")
        print("SCQTMESSAGE: trigger(3);\n")
    print("SCQTMESSAGE: dio = "+str(sleepWells[whichAn[anIndex]])+";\n")
    print("SCQTMESSAGE: trigger(2);\n")
    sleepRewards = 0
    reset = 0

def doSleep(val):
    global sleepDoors
    global sleepPumps
    global sleepRewards
    global maxSleep
    global whichAn
    global anIndex
    global onTrack
    if sleepRewards == 0 and val == whichAn[anIndex] and onTrack == 0:
#        print("SCQTMESSAGE: dio = "+str(trackDoor)+";\n")
#        print("SCQTMESSAGE: trigger(3);\n")
        print("SCQTMESSAGE: dio = "+str(sleepDoors[whichAn[anIndex]])+";\n")
        print("SCQTMESSAGE: trigger(3);\n")
        print("SCQTMESSAGE: dio = "+str(boxDoors[math.floor(whichAn[anIndex]/len(boxDoors))])+";\n")
        print("SCQTMESSAGE: trigger(3);\n")
    if sleepRewards < maxSleep and val == whichAn[anIndex] and onTrack == 0:
        print("SCQTMESSAGE: rewardWell = "+str(sleepPumps[whichAn[anIndex]])+";\n")
        print("SCQTMESSAGE: timeCheck = clock()\n")
        print("SCQTMESSAGE: trigger(1);\n")
        sleepRewards+=1

def endSleep(val):
    global sleepDoors
    global sleepPumps
    global sleepRewards
    global maxSleep
    global homeRewards
    global outerRewards
    global whichAn
    global anIndex
    global onTrack
    global session
    global timeNow
    global lastArm
    global maxSessions
    global lastOuter
    global messageSent
    global wArms
    global WARMS
    global cenRew
    global frustrationSession
    if sleepRewards == maxSleep and val == whichAn[anIndex] and onTrack == 0:
        print("SCQTMESSAGE: dio = "+str(sleepWells[whichAn[anIndex]])+";\n")
        print("SCQTMESSAGE: trigger(3);\n")
        homeRewards = 0
        outerRewards = 0
        lastArm = -1
        lastOuter = -1
        anIndex += 1
        session += math.floor(anIndex/len(sleepDoors))
        anIndex = (anIndex % len(sleepDoors))
        wArms=WARMS[whichAn[anIndex]][:]
        maxTrials=allMax[whichAn[anIndex]]
        print("SCQTMESSAGE: arms = "+str(wArms[0])+str(wArms[1]+(cenRew==0)*5)+str(wArms[2])+";\n")
        print("SCQTMESSAGE: trigger(6);\n")
        print("SCQTMESSAGE: transition = 1;\n")
        print("SCQTMESSAGE: animal = "+str(Animals[whichAn[anIndex]])+";\n")
        if session > maxSessions:
            print("SCQTMESSAGE: stop = 1;\n")
        else:
            onTrack = 1
            print("SCQTMESSAGE: trigger(5);\n")
        for num in armWells:
            print("SCQTMESSAGE: dio = "+str(num)+";\n")
            print("SCQTMESSAGE: trigger(2);\n")
        print("SCQTMESSAGE: dio = "+str(trackDoor)+";\n")
        print("SCQTMESSAGE: trigger(2);\n")
        if(session == frustrationSession):
#            print("SCQTMESSAGE: dio = "+str(trackDoor)+";\n")
#            print("SCQTMESSAGE: trigger(3);\n")
            homeRewards=maxTrials-1
#            print("SCQTMESSAGE: trigger(9);\n")
        print("SCQTMESSAGE: dio = "+str(sleepDoors[whichAn[anIndex]])+";\n")
        print("SCQTMESSAGE: trigger(2);\n")
        print("SCQTMESSAGE: dio = "+str(boxDoors[math.floor(whichAn[anIndex]/len(boxDoors))])+";\n")
        print("SCQTMESSAGE: trigger(2);\n")
        print("SCQTMESSAGE: transition = 0;\n")
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
armWells = [23, 24, 25, 26, 27, 28]

#w-track arms [outer, home, outer] on a set of [1,6]
WARMS= np.array([[2, 3, 4],[2, 3, 4],[2, 3, 4],[2, 3, 4]])
wArms= WARMS[0][:]

#w-track arm pumps:
armPumps = [17, 18, 19, 20, 21, 22]

#sleep box wells:
sleepWells = [29, 30, 31,32]

#sleep box pumps:
sleepPumps = [8, 9, 10 , 11]

#doors:
sleepDoors = [1, 2, 3, 4]
trackDoor = 5
boxDoors = [6, 7]

#global variables
lastArm = -1
homeRewards = 0
outerRewards = 0
maxTrials = 20
allMax= [maxTrials, maxTrials, maxTrials, maxTrials]
onTrack = 1
whichAn=[0,1,2,3]
anIndex=0
sleepRewards = 0
maxSleep = 5
session=1
maxSessions=3
timeElapsed=0
timeNow=0
lastOuter=-1
trackTime=0
maxTime=15
reset=0
cenRew=1
frustrationSession=-1

print("SCQTMESSAGE: timeOut = 0;\n")

#Animal numbers, to be update for each set of animals
Animals=[1, 2, 3, 4]

def finish():
    global session
    global Animals
    global anIndex
    global whichAn
    global sleepWells
    global sleepPumps
    global sleepDoors
    global armWells
    global transition
    global trackDoor
    global boxDoors
    global maxSessions
    global maxTrials
    global timeNow
    global wArms
    global WARMS
    global maxTime
    global allMax
    global cenRew
    global frustrationSession
    anIndex=var.get()
    Animals[0]=int(E1.get())
    Animals[1]=int(E2.get())
    Animals[2]=int(E3.get())
    Animals[3]=int(E4.get())
    whichAn=[0,1,2,3]
    if Animals[3]<0:
        sleepWells = [29, 30, 31]
        sleepPumps = [8, 9, 10]
        sleepDoors = [1, 2, 3]
        whichAn=[0,1,2]
    if Animals[2]<0:
        sleepWells = [29, 30]
        sleepPumps = [8, 9]
        sleepDoors = [1, 2]
        whichAn=[0,1]
    session=int(E5.get())
    maxTrials0=int(E10.get())
    maxTrials1=int(E11.get())
    maxTrials2=int(E12.get())
    maxTrials3=int(E13.get())
    allMax=[maxTrials0, maxTrials1, maxTrials2, maxTrials3]
    maxSessions=int(E7.get())
    allMax
    maxTime=int(E8.get())
    order=varA1.get()
    frustrationSession=int(Cb3.get())
    if order==0:
    	WARMS[0]=[2,3,4]
    elif order==1:
    	WARMS[0]=[1,2,3]
    elif order==2:
    	WARMS[0]=[3,4,5]
    elif order==3:
    	WARMS[0]=[2,4,6]
    elif order==4:
        WARMS[0]=[4,5,6]
    elif order==5:
        WARMS[0]=[1,3,5]
    elif order==6:
        WARMS[0]=[3,2,4]
    else:
        WARMS[0]=[4,3,5]

    order=varA2.get()
    if order==0:
    	WARMS[1]=[2,3,4]
    elif order==1:
    	WARMS[1]=[1,2,3]
    elif order==2:
    	WARMS[1]=[3,4,5]
    elif order==3:
    	WARMS[1]=[2,4,6]
    elif order==4:
        WARMS[1]=[4,5,6]
    elif order==5:
        WARMS[1]=[1,3,5]
    elif order==6:
        WARMS[1]=[3,2,4]
    else:
        WARMS[1]=[4,3,5]

    order=varA3.get()
    if order==0:
    	WARMS[2]=[2,3,4]
    elif order==1:
    	WARMS[2]=[1,2,3]
    elif order==2:
    	WARMS[2]=[3,4,5]
    elif order==3:
    	WARMS[2]=[2,4,6]
    elif order==4:
        WARMS[2]=[4,5,6]
    elif order==5:
        WARMS[2]=[1,3,5]
    elif order==6:
        WARMS[2]=[3,2,4]
    else:
        WARMS[2]=[4,3,5]

    order=varA4.get()
    if order==0:
    	WARMS[3]=[2,3,4]
    elif order==1:
    	WARMS[3]=[1,2,3]
    elif order==2:
    	WARMS[3]=[3,4,5]
    elif order==3:
    	WARMS[3]=[2,4,6]
    elif order==4:
        WARMS[3]=[4,5,6]
    elif order==5:
        WARMS[3]=[1,3,5]
    elif order==6:
        WARMS[3]=[3,2,4]
    else:
        WARMS[3]=[4,3,5]

    order=varB1.get()
    if order==0:
        whichAn=[0,1,2,3]
    elif order==1:
        whichAn=[1,2,3,0]
    elif order==2:
        whichAn=[2,3,0,1]
    elif order==3:
        whichAn=[3,0,1,2]

    
    wArms=WARMS[whichAn[anIndex]][:]
    maxTrials=allMax[whichAn[anIndex]]

    if cbVar.get():
        cenRew=0
    display.destroy()

    for num in sleepWells:
        print("SCQTMESSAGE: dio = "+str(num)+";\n")
        print("SCQTMESSAGE: trigger(3);\n")

    for num in armWells:
        print("SCQTMESSAGE: dio = "+str(num)+";\n")
        print("SCQTMESSAGE: trigger(2);\n")

    print("SCQTMESSAGE: arms = "+str(wArms[0])+str(wArms[1]+(cenRew==0)*5)+str(wArms[2])+";\n")
    print("SCQTMESSAGE: trigger(6);\n")

    print("SCQTMESSAGE: stop = 0;\n")
    print("SCQTMESSAGE: transition = 1;\n")
    print("SCQTMESSAGE: dio = "+str(sleepDoors[whichAn[anIndex]])+";\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: dio = "+str(trackDoor)+";\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: dio = "+str(boxDoors[math.floor(whichAn[anIndex]/len(boxDoors))])+";\n")
    print("SCQTMESSAGE: trigger(2);\n")
    print("SCQTMESSAGE: animal = "+str(Animals[whichAn[anIndex]])+";\n")
    print("SCQTMESSAGE: trigger(5);\n")
    print("SCQTMESSAGE: transition = 0;\n")
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

    frame0 = Frame(display)
    frame0.pack(side = TOP)

    frame1 = Frame(display)
    frame1.pack(side = TOP)

    frame2 = Frame(display)
    frame2.pack(side = TOP)

    frame3 = Frame(display)
    frame3.pack(side = TOP )

    frame4 = Frame(display)
    frame4.pack(side = TOP )

    frame5 = Frame(display)
    frame5.pack(side = TOP )

    frame6 = Frame(display)
    frame6.pack(side = TOP )

    frame7 = Frame(display)
    frame7.pack(side = TOP )

    frame8 = Frame(display)
    frame8.pack(side = TOP )

    frame9 = Frame(display)
    frame9.pack(side = TOP )

    frame10 = Frame(display)
    frame10.pack(side = TOP )

    frame11 = Frame(display)
    frame11.pack(side = TOP )

    frame12 = Frame(display)
    frame12.pack(side = TOP )

    frame13 = Frame(display)
    frame13.pack(side = TOP )

    frame14 = Frame(display)
    frame14.pack(side = BOTTOM )

    L0 = Label(frame0, text="This is the alternation algorithm", font=("Helvetica", 30), bg="green")
    L0.pack(side = LEFT)

    L1 = Label(frame1, text="box 1:")
    L1.pack(side = LEFT)
    E1 = Entry(frame1, bd = 3, width = 3)
    E1.pack(side = LEFT)
    E1.insert(0,str(Animals[0]))
    
    varA1 = IntVar()
    L10 = Label(frame1, text="trials:")
    L10.pack(side = LEFT)
    E10 = Entry(frame1, bd = 3, width = 3)
    E10.pack(side = LEFT)
    E10.insert(0,str(allMax[0]))

    Ra11 = Radiobutton(frame1, text="arms 2,3,4", variable=varA1, value=0)
    Ra11.pack(side = LEFT)

    Ra12 = Radiobutton(frame1, text="arms 1,2,3", variable=varA1, value=1)
    Ra12.pack(side = LEFT)

    Ra13 = Radiobutton(frame1, text="arms 3,4,5", variable=varA1, value=2)
    Ra13.pack(side = LEFT)

    Ra14 = Radiobutton(frame1, text="arms 2,4,6", variable=varA1, value=3)
    Ra14.pack(side = LEFT)

    Ra15 = Radiobutton(frame1, text="arms 4,5,6", variable=varA1, value=4)
    Ra15.pack(side = LEFT)

    Ra16 = Radiobutton(frame1, text="arms 1,3,5", variable=varA1, value=5)
    Ra16.pack(side = LEFT)

    Ra17 = Radiobutton(frame1, text="arms 3,2,4", variable=varA1, value=6)
    Ra17.pack(side = LEFT)

    Ra18 = Radiobutton(frame1, text="arms 4,3,5", variable=varA1, value=7)
    Ra18.pack(side = LEFT)

    L2 = Label(frame2, text="box 2:")
    L2.pack(side = LEFT)
    E2 = Entry(frame2, bd = 3, width = 3)
    E2.pack(side = LEFT)
    E2.insert(0,str(Animals[1]))

    varA2 = IntVar()
    L11 = Label(frame2, text="trials:")
    L11.pack(side = LEFT)
    E11 = Entry(frame2, bd = 3, width = 3)
    E11.pack(side = LEFT)
    E11.insert(0,str(allMax[1]))

    Ra21 = Radiobutton(frame2, text="arms 2,3,4", variable=varA2, value=0)
    Ra21.pack(side = LEFT)

    Ra22 = Radiobutton(frame2, text="arms 1,2,3", variable=varA2, value=1)
    Ra22.pack(side = LEFT)

    Ra23 = Radiobutton(frame2, text="arms 3,4,5", variable=varA2, value=2)
    Ra23.pack(side = LEFT)

    Ra24 = Radiobutton(frame2, text="arms 2,4,6", variable=varA2, value=3)
    Ra24.pack(side = LEFT)

    Ra25 = Radiobutton(frame2, text="arms 4,5,6", variable=varA2, value=4)
    Ra25.pack(side = LEFT)

    Ra26 = Radiobutton(frame2, text="arms 1,3,5", variable=varA2, value=5)
    Ra26.pack(side = LEFT)

    Ra27 = Radiobutton(frame2, text="arms 3,2,4", variable=varA2, value=6)
    Ra27.pack(side = LEFT)

    Ra28 = Radiobutton(frame2, text="arms 4,3,5", variable=varA2, value=7)
    Ra28.pack(side = LEFT)

    L3 = Label(frame3, text="box 3:")
    L3.pack(side = LEFT)
    E3 = Entry(frame3, bd = 3, width = 3)
    E3.pack(side = LEFT)
    E3.insert(0,str(Animals[2]))

    varA3 = IntVar()
    L12 = Label(frame3, text="trials:")
    L12.pack(side = LEFT)
    E12 = Entry(frame3, bd = 3, width = 3)
    E12.pack(side = LEFT)
    E12.insert(0,str(allMax[2]))

    Ra31 = Radiobutton(frame3, text="arms 2,3,4", variable=varA3, value=0)
    Ra31.pack(side = LEFT)

    Ra32 = Radiobutton(frame3, text="arms 1,2,3", variable=varA3, value=1)
    Ra32.pack(side = LEFT)

    Ra33 = Radiobutton(frame3, text="arms 3,4,5", variable=varA3, value=2)
    Ra33.pack(side = LEFT)

    Ra34 = Radiobutton(frame3, text="arms 2,4,6", variable=varA3, value=3)
    Ra34.pack(side = LEFT)

    Ra35 = Radiobutton(frame3, text="arms 4,5,6", variable=varA3, value=4)
    Ra35.pack(side = LEFT)

    Ra36 = Radiobutton(frame3, text="arms 1,3,5", variable=varA3, value=5)
    Ra36.pack(side = LEFT)

    Ra37 = Radiobutton(frame3, text="arms 3,2,4", variable=varA3, value=6)
    Ra37.pack(side = LEFT)

    Ra38 = Radiobutton(frame3, text="arms 4,3,5", variable=varA3, value=7)
    Ra38.pack(side = LEFT)

    L4 = Label(frame4, text="box 4:")
    L4.pack(side = LEFT)
    E4 = Entry(frame4, bd = 3, width = 3)
    E4.pack(side = LEFT)
    E4.insert(0,str(Animals[3]))

    varA4 = IntVar()
    L13 = Label(frame4, text="trials:")
    L13.pack(side = LEFT)
    E13 = Entry(frame4, bd = 3, width = 3)
    E13.pack(side = LEFT)
    E13.insert(0,str(allMax[3]))

    Ra41 = Radiobutton(frame4, text="arms 2,3,4", variable=varA4, value=0)
    Ra41.pack(side = LEFT)

    Ra42 = Radiobutton(frame4, text="arms 1,2,3", variable=varA4, value=1)
    Ra42.pack(side = LEFT)

    Ra43 = Radiobutton(frame4, text="arms 3,4,5", variable=varA4, value=2)
    Ra43.pack(side = LEFT)

    Ra44 = Radiobutton(frame4, text="arms 2,4,6", variable=varA4, value=3)
    Ra44.pack(side = LEFT)

    Ra45 = Radiobutton(frame4, text="arms 4,5,6", variable=varA4, value=4)
    Ra45.pack(side = LEFT)

    Ra46 = Radiobutton(frame4, text="arms 1,3,5", variable=varA4, value=5)
    Ra46.pack(side = LEFT)

    Ra47 = Radiobutton(frame4, text="arms 3,2,4", variable=varA4, value=6)
    Ra47.pack(side = LEFT)

    Ra48 = Radiobutton(frame4, text="arms 4,3,5", variable=varA4, value=7)
    Ra48.pack(side = LEFT)

    cbL1=Label(frame5, text="    ")
    cbL1.pack()

    cbVar = IntVar()
    Cb1=Checkbutton(frame6, text="no Center Reward", variable=cbVar)
    Cb1.grid(row=0, sticky=W)
    Cb1.pack(side = LEFT)

    Cb2 = Label(frame6, text="Frustration Session:", bg="pink", bd=10)
    Cb2.pack(side = LEFT)
    Cb3 = Entry(frame6, bd = 3, width = 3)
    Cb3.pack(side = LEFT)
    Cb3.insert(0,str(frustrationSession))

    cbL2=Label(frame7, text="    ")
    cbL2.pack()

    var = IntVar()
    R1 = Radiobutton(frame8, text="start first position", variable=var, value=0)
    R1.pack(anchor = W )

    R2 = Radiobutton(frame8, text="start second position", variable=var, value=1)
    R2.pack(anchor = W )

    R3 = Radiobutton(frame8, text="start third position", variable=var, value=2)
    R3.pack(anchor = W)

    R4 = Radiobutton(frame8, text="start fourth position", variable=var, value=3)
    R4.pack(anchor = W)

    L5 = Label(frame9, text="start session #")
    L5.pack(side = LEFT)
    E5 = Entry(frame9, bd = 3, width = 3)
    E5.pack(side = LEFT)
    E5.insert(0,str(session))

    L7 = Label(frame10, text="max session #")
    L7.pack(side = LEFT)
    E7 = Entry(frame10, bd = 3, width = 3)
    E7.pack(side = LEFT)
    E7.insert(0,str(maxSessions))

    L8 = Label(frame11, text="max time (min)")
    L8.pack(side = LEFT)
    E8 = Entry(frame11, bd = 3, width = 3)
    E8.pack(side = LEFT)
    E8.insert(0,str(maxTime))

    L0 = Label(frame12, text="Box order:")
    L0.pack()

    varB1 = IntVar()
    Ra21 = Radiobutton(frame13, text="1,2,3,4", variable=varB1, value=0)
    Ra21.pack(side = LEFT)

    Ra22 = Radiobutton(frame13, text="2,3,4,1", variable=varB1, value=1)
    Ra22.pack(side = LEFT)

    Ra23 = Radiobutton(frame13, text="3,4,1,2", variable=varB1, value=2)
    Ra23.pack(side = LEFT)

    Ra24 = Radiobutton(frame13, text="4,1,2,3", variable=varB1, value=3)
    Ra24.pack(side = LEFT)

    B = Button(frame14, text ="Go", command = finish)

    B.pack(side = BOTTOM)

    display.mainloop()

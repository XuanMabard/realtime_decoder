import math
import struct
import re
import time
import random
import numpy as np
import pyaudio
import wave
from itertools import compress

# V8pre_forage
# visits to incorrect wells cause 5s lockout
# exception is repeat visit to prior well (is ok, no lockout)
# can go to any outer well, any number of times
# lockout from getting rip/wait wells wrong is also 5s


# decide what type of up trigger was just recieved; act accordingly
# only for home and outer, center well defined in statescript
def pokeIn(dio):
	global homeWell
	global centerWell
	global outerWells
	global currWell
	global taskState
 
	currWell = int(dio[1])
	# not using doHome
	#if currWell == homeWell: 
	#	doHome()

	# how do we start???
	# for testing we could start with an outer well visit

	if taskState == 1:
		for num in range(len(outerWells)):
			if currWell == outerWells[num]:
				doOuter(num)
	else:
		for num in range(len(outerWells)):
			if currWell == outerWells[num]:
				doOuter(num)

# decide what type of down trigger was just recieved; act accordingly
def pokeOut(dio):
	global homeWell
	global centerWell
	global outerWells
	global currWell
	global lastWell
	global taskState
 
	currWell = int(dio[1])
	# not using endHome
	#if currWell == centerWell: 
	#	endCenter()

	# MEC commented out - moved to callback section
	#if currWell == centerWell: 
	#	endWait()
	if taskState == 1:
		for num in range(len(outerWells)):
			if currWell == outerWells[num]:
				endOuter()
	else:
		for num in range(len(outerWells)):
			if currWell == outerWells[num]:
				endOuter()
		lastWell = currWell

# NOTE: currently NOT calling this function
# instead use endOuter to start new trial
#home poke: decide trial type and upcoming wait length; turn on lights accordingly
# def doHome():
# 	global trialtype  # 0 go to home,1 go to center, 2 go to outer, 3 lockout
# 	global homePump
# 	global lastWell
# 	global currWell
# 	global goalWell
# 	global outerWells

# 	if trialtype == 0:	
# 		trialtype = 1
# 		print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
# 		# this line set the variable delaytime and then writes the variable to statescript  
# 		delaytime = chooseDelay()
# 		print("SCQTMESSAGE: waittime = "+str(delaytime)+";\n")

# 		# set goal well to 1 arm for this trial - get line from old script
# 		# set goal well based on replay content from spykshrk after enough visits to each arm

# 		# yes this is wrong for content rewared wells, but content information will reset
# 		# goalWell in beep function
# 		# this is where cued trials are set and we want to control disrubiton 
# 		#goalWell = np.random.choice(outerWells,1,replace=False)
# 		print("SCQTMESSAGE: homeCount = homeCount + 1;\n") # update homecount in SC
# 		print("SCQTMESSAGE: rewardWell = "+str(homePump)+";\n")
# 		print("SCQTMESSAGE: trigger(1);\n")   # deliver reward
# 	#check for home poke out of sequence, start lockout 1
# 	elif trialtype > 0 and trialtype < 3 and lastWell != currWell:
# 		lockout([0,1])

def chooseDelay():
    global trialtype
    global centercount
    global waitdist
    global content_waitdist
    global startwaitdist
    global centercount_content

    #print(centercount)
    if taskState == 2 and centercount_content < 4:
    	return int(np.random.choice(content_waitdist_early,1))

    elif taskState == 2:
    	return int(np.random.choice(content_waitdist,1))

    elif centercount<3:  #first 3 trials of of each type should be short
        return startwaitdist[centercount]

    else:
        if centercount<=10:  #trials 4-10 of each type will be avg of startwaitdist and normal waitdist
            return int(round(np.mean([int(np.random.choice(startwaitdist,1)), int(np.random.choice(waitdist,1))])))

        else: # all trial 10 and later
            return int(np.random.choice(waitdist,1))

#NOTE: currently NOT calling this function
# was endHome
def endCenter():
	global cuedWells
	global taskState
	global outer_count_content

	# for first content trial, trigger 13
	if taskState == 2 and outer_count_content == 0:
		outer_count_content += 1
		for num in range(len(outerWells)):			# turn off outer lights
			print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
			print("SCQTMESSAGE: trigger(4);\n")
		# turn on center light
		print("SCQTMESSAGE: dio = "+str(2)+";\n")
		print("SCQTMESSAGE: trigger(3);\n")
		print('first content trial',outer_count_content)
		print("SCQTMESSAGE: trigger(5);\n")   # display stats
		print("SCQTMESSAGE: trigger(13);\n")

#function: add time to wait dist. 
def addtime(newtime):
	global count
	global waitdist

	count+=1
	# % means mod (reaminder) function
	waitdist[count%8] = int(newtime[1])  #new time 1 will be timediff, not timestamp
	print(waitdist)

# only called during cued outer arm trials
def beep_center():
	global centerPump
	global centerWell
	global trialtype
	global currWell
	global centercount
	global centercount_content
	global taskState

	centercount+=1

	# for taskstate 2

	if taskState == 2:
		## begin outer arm trial section of task
		#trialtype = 2                   # ready for outer visit
		#print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
		#deliver reward
		trialtype = 2
		print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
		centercount_content += 1
		if currWell == centerWell:
			print("SCQTMESSAGE: rewardWell = "+str(centerPump)+";\n")
		print("SCQTMESSAGE: trigger(1);\n")
		print("SCQTMESSAGE: centerCount = centerCount + 1;\n") # update centercount in SC

	# for taskstate 1 and 3
	else:
		# begin outer arm trial section of task
		trialtype = 2                   # ready for outer visit
		print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
		#deliver reward
		if currWell == centerWell:
			print("SCQTMESSAGE: rewardWell = "+str(centerPump)+";\n")
		print("SCQTMESSAGE: trigger(1);\n")
		print("SCQTMESSAGE: centerCount = centerCount + 1;\n") # update centercount in SC

# # only called during content trials
# def beep_home():
# 	global homePump
# 	global homeWell
# 	global trialtype
# 	global currWell
# 	global homecount

# 	homecount+=1
# 	## begin outer arm trial section of task
# 	#trialtype = 2                   # ready for outer visit
# 	#print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
# 	#deliver reward
# 	if currWell == homeWell:
# 		print("SCQTMESSAGE: rewardWell = "+str(homePump)+";\n")
# 	print("SCQTMESSAGE: trigger(1);\n")
# 	print("SCQTMESSAGE: homeCount = homeCount + 1;\n") # update centercount in SC

# define goalWell - only used during cued arm trials
def chooseGoal():
	global taskState
	global replay_arm
	global outerarm_required_rewards
	global arm1_Goal
	global arm2_Goal
	global arm3_Goal
	global arm4_Goal
	global arm1_counter
	global arm2_counter
	global arm3_counter
	global arm4_counter
	global home_Goal
	global goalWell
	global outerWells
	global cuedWells
	global cued_trial_counter
	global oldGoal
	global outer_arm_reward
	global task3_trial_counter
	global arm1_order12
	global arm2_order12
	global arm3_order12
	global arm4_order12
	global arm1_order_2
	global arm2_order_2
	global arm3_order_2
	global arm4_order_2
	global instructiveTrial
	global outer_count_content

	# taskstate ==1 is cued visits to each outer arm
	if taskState == 1:
		# trial 0: set reward order for each arm
		if cued_trial_counter == 0:
			# 2 of 4 arm visits rewarded - ranint(6)
			order_options = np.array([[1,1,0,0],[1,0,1,0],[1,0,0,1],[0,1,1,0],[0,1,0,1],[0,0,1,1]])
			# 3 of 5 arm visits rewarded - randint(10)
			#order_options = np.array([[1,1,1,0,0],[1,1,0,1,0],[1,1,0,0,1],[1,0,1,1,0],[1,0,0,1,1],
			#	[1,0,1,0,1],[0,1,1,1,0],[0,1,1,0,1],[0,1,0,1,1],[0,0,1,1,1]])
			# 6 of 8 - randint(28)
			#order_options = np.array([[1,1,1,1,1,1,0,0],[1,1,1,1,1,0,0,1],[1,1,1,1,0,0,1,1],[1,1,1,0,0,1,1,1],
			#		[1,1,0,0,1,1,1,1],[1,0,0,1,1,1,1,1],[0,0,1,1,1,1,1,1],[0,1,0,1,1,1,1,1],
			#		[0,1,1,0,1,1,1,1],[0,1,1,1,0,1,1,1],[0,1,1,1,1,0,1,1],[0,1,1,1,1,1,0,1],
			#		[0,1,1,1,1,1,1,0],[1,0,1,0,1,1,1,1],[1,0,1,1,0,1,1,1],[1,0,1,1,1,0,1,1],
			#		[1,0,1,1,1,1,0,1],[1,0,1,1,1,1,1,0],[1,1,0,1,0,1,1,1],[1,1,0,1,1,0,1,1],
			#		[1,1,0,1,1,1,0,1],[1,1,0,1,1,1,1,0],[1,1,1,0,1,0,1,1],[1,1,1,0,1,1,0,1],
			#		[1,1,1,0,1,1,1,0],[1,1,1,1,0,1,0,1],[1,1,1,1,0,1,1,0],[1,1,1,1,1,0,1,0]])

			arm1_order = order_options[np.random.randint(6)]
			arm1_order8 = np.append(arm1_order,order_options[np.random.randint(6)])
			arm1_order12 = np.append(arm1_order8,order_options[np.random.randint(6)])
			arm2_order = order_options[np.random.randint(6)]
			arm2_order8 = np.append(arm2_order,order_options[np.random.randint(6)])
			arm2_order12 = np.append(arm2_order8,order_options[np.random.randint(6)])
			arm3_order = order_options[np.random.randint(6)]
			arm3_order8 = np.append(arm3_order,order_options[np.random.randint(6)])
			arm3_order12 = np.append(arm3_order8,order_options[np.random.randint(6)])
			arm4_order = order_options[np.random.randint(6)]
			arm4_order8 = np.append(arm4_order,order_options[np.random.randint(6)])
			arm4_order12 = np.append(arm4_order8,order_options[np.random.randint(6)])
			print("SCQTMESSAGE: disp('Cued arm 1 reward order "+str(arm1_order12)+"');\n")
			print("SCQTMESSAGE: disp('Cued arm 2 reward order "+str(arm2_order12)+"');\n")
			print("SCQTMESSAGE: disp('Cued arm 3 reward order "+str(arm3_order12)+"');\n")
			print("SCQTMESSAGE: disp('Cued arm 4 reward order "+str(arm4_order12)+"');\n")

		# want to force alternation between arms in the beginning

		# this is boolean way of setting this to 1 or 0
		# valid+_goals is not global just local to this funciton
		valid_goals = [arm1_Goal<outerarm_required_rewards,
					   arm2_Goal<outerarm_required_rewards,
					   arm3_Goal<outerarm_required_rewards,
					   arm4_Goal<outerarm_required_rewards]
		print('valid goals',valid_goals)

		# want to force alternation between arms in the beginning (first 2 visits each)
		# okay this seems to work
		if (cued_trial_counter > 0 and arm1_Goal < outerarm_required_rewards-1 and arm2_Goal < outerarm_required_rewards-1
			and arm3_Goal < outerarm_required_rewards-1 and arm4_Goal < outerarm_required_rewards-1):
			print('goal',goalWell)
			print('old goal',oldGoal)
			print(outerWells.index(oldGoal))
			valid_goals[outerWells.index(oldGoal)] = False
			print('valid goals no repeat',valid_goals)

		# this line doesnt work
		#print(outerWells[valid_goals])
		# try this:
		#print(list(compress(outerWells,valid_goals)))
		print(list(compress(outerWells,valid_goals)))

		# now only choose from list of outerwells where valid_goals == 1
		#goalWell = np.random.choice(list(compress(outerWells,valid_goals)),1,replace=False)
		goalWell = np.random.choice(list(compress(outerWells,valid_goals)),1,replace=False)
		oldGoal = goalWell
		print('cued goalWell is: ',goalWell)
		print("SCQTMESSAGE: disp('CUED ARM VISITS "+str(outerarm_required_rewards)+"');\n")
		
		# NOTE: need to substitute the correct arm numbers (not 1-4) for goalWell
		# NOTE: check that arm assignments are correct
		# NOTE: set outer_arm_reward = 1 to have 100% reward
		if goalWell == 15:
			outer_arm_reward = arm1_order12[arm1_counter]
			#outer_arm_reward = 1
			arm1_counter += 1
		elif goalWell == 14:
			outer_arm_reward = arm2_order12[arm2_counter]
			#outer_arm_reward = 1
			arm2_counter += 1
		elif goalWell == 13:
			outer_arm_reward = arm3_order12[arm3_counter]
			#outer_arm_reward = 1
			arm3_counter += 1	
		elif goalWell == 12:
			outer_arm_reward = arm4_order12[arm4_counter]
			#outer_arm_reward = 1
			arm4_counter += 1	
					
		cued_trial_counter += 1

	# # for return to cued visits used 2*outerarm_required_rewards as cutoff
	# elif taskState == 3:
	# 	# this is boolean way of setting this to 1 or 0
	# 	# valid+_goals is not global just local to this funciton
	# 	valid_goals = [arm1_Goal<outerarm_required_rewards+2,
	# 				   arm2_Goal<outerarm_required_rewards+2,
	# 				   arm3_Goal<outerarm_required_rewards+2,
	# 				   arm4_Goal<outerarm_required_rewards+2]
	# 	print(valid_goals)
	# 	# this line doesnt work
	# 	#print(outerWells[valid_goals])
	# 	# try this:
	# 	print(list(compress(outerWells,valid_goals)))

	# 	# now only choose from list of outerwells where valid_goals == 1
	# 	goalWell = np.random.choice(list(compress(outerWells,valid_goals)),1,replace=False)
	# 	print('cued goalWell is: ',goalWell)
	# 	print("SCQTMESSAGE: disp('CUED ARM VISITS "+str(outerarm_required_rewards)+"');\n")

	# 	#goalWell = np.random.choice(outerWells[valid_goals],1,replace=False)

	# 08-2020: task3: all lights on, give reward after 3 or 4 visits
	elif taskState == 3:
		# # all lights
		# goalWell = [12,13,14,15]
		# # no lights
		# #goalWell = []
		# print('cued goalWell is: ',goalWell)
		# if task3_trial_counter >= 3:
		# 	#outer_arm_reward = 1
		# 	# 75%
		# 	outer_arm_reward = np.random.randint(100)<50
		# else:
		# 	outer_arm_reward = 0



		#outer_arm_reward = 1
		#goalWell = replay_arm
		#print('replay goalWell is: ',goalWell)

		if task3_trial_counter == 0:
			# 2 of 4 arm visits rewarded - ranint(6)
			order_options = np.array([[1,0],[0,1]])

			arm1_order_2 = order_options[np.random.randint(2)]
			arm2_order_2 = order_options[np.random.randint(2)]
			arm2_order_2 = order_options[np.random.randint(2)]
			arm2_order_2 = order_options[np.random.randint(2)]
			print(arm1_order_2,arm2_order_2,arm3_order_2,arm4_order_2)

		# this is boolean way of setting this to 1 or 0
		# valid+_goals is not global just local to this funciton
		valid_goals = [arm1_Goal<outerarm_required_rewards+1,
					   arm2_Goal<outerarm_required_rewards+1,
					   arm3_Goal<outerarm_required_rewards+1,
					   arm4_Goal<outerarm_required_rewards+1]
		print('valid goals',valid_goals)

		# try this:
		#print(list(compress(outerWells,valid_goals)))
		print(list(compress(outerWells,valid_goals)))

		# now only choose from list of outerwells where valid_goals == 1
		#goalWell = np.random.choice(list(compress(outerWells,valid_goals)),1,replace=False)
		goalWell = np.random.choice(list(compress(outerWells,valid_goals)),1,replace=False)
		oldGoal = goalWell
		print('cued goalWell is: ',goalWell)
		print("SCQTMESSAGE: disp('CUED ARM VISITS "+str(outerarm_required_rewards)+"');\n")
		
		# NOTE: need to substitute the correct arm numbers (not 1-4) for goalWell
		# NOTE: check that arm assignments are correct
		# NOTE: set outer_arm_reward = 1 to have 100% reward
		if goalWell == 15:
			print(arm1_counter)
			#outer_arm_reward = arm1_order_2[arm1_counter-outerarm_required_rewards]
			#outer_arm_reward = np.random.randint(100)<50
			outer_arm_reward = 1
			arm1_counter += 1
		elif goalWell == 14:
			print(arm2_counter)
			#outer_arm_reward = arm2_order_2[arm2_counter-outerarm_required_rewards]
			#outer_arm_reward = np.random.randint(100)<50
			outer_arm_reward = 1
			arm2_counter += 1
		elif goalWell == 13:
			print(arm3_counter)
			#outer_arm_reward = arm3_order_2[arm3_counter-outerarm_required_rewards]
			#outer_arm_reward = np.random.randint(100)<50
			outer_arm_reward = 1
			arm3_counter += 1	
		elif goalWell == 12:
			print(arm4_counter)
			#outer_arm_reward = arm4_order_2[arm4_counter-outerarm_required_rewards]
			#outer_arm_reward = np.random.randint(100)<50
			outer_arm_reward = 1
			arm4_counter += 1	
		
		task3_trial_counter += 1


	# if taskState == 2, content trials
	else:
		goalWell = np.random.choice(list(outerWells),1,replace=False)
		if outer_count_content > 1:
			instructiveTrial = np.random.randint(100)<40
		print('instructive probe trial:',instructiveTrial)
		#goalWell = np.array([13])
		outer_arm_reward = 1
		print('instructive content trial. goal',goalWell)
		with open("/home/lorenlab/spykshrk_realtime/config/target_arm.txt","a") as target_arm_file:
			try:
				target_arm_file.write(str(goalWell[0])+'\n')
			finally: 
				target_arm_file.close()			


# only called during cued outer arm trials
def endWait():
	global trialtype
	global goalWell
	global currWell
	global outerWells
	global arm1_Goal
	global arm2_Goal
	global arm3_Goal
	global arm4_Goal
	global instructiveTrial

	if trialtype == 2:   # wait complete

		print("SCQTMESSAGE: dio = "+str(currWell)+";\n")     # turn off rip light
		print("SCQTMESSAGE: trigger(4);\n")	

		print("SCQTMESSAGE: trigger(5);\n")   # display stats
		print("SCQTMESSAGE: disp('CURRENTGOAL IS "+str(goalWell[0])+" TASK_STATE IS "+str(taskState)+"');\n") 
		
		# use taskState to determine whether this is a cued trial or content trial
		# only for which outer lights to turn on
		if taskState == 1:
			# turn on light for goalWell only
			# brackets required to get integer only for statescript
			print("SCQTMESSAGE: dio = "+str(goalWell[0])+";\n")
			print("SCQTMESSAGE: trigger(3);\n")

		elif taskState == 3:
			# turn on light for all outer arms 
			# brackets required to get integer only for statescript
			#for num in range(len(outerWells)):
			#	print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
			#	print("SCQTMESSAGE: trigger(3);\n")
			print("SCQTMESSAGE: dio = "+str(goalWell[0])+";\n")
			print("SCQTMESSAGE: trigger(3);\n")

		elif taskState == 2 and not instructiveTrial:
			print("SCQTMESSAGE: dio = "+str(goalWell[0])+";\n")
			print("SCQTMESSAGE: trigger(3);\n")			

		elif taskState == 2 and instructiveTrial:
			for num in range(len(outerWells)):
				print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
				print("SCQTMESSAGE: trigger(3);\n")

		# taskState = 2
		# this may or may not happen...
		#else:
			# NEW: no outer arms - so re-start wait here
			# we want this wait to have no light, turn on light after wait ends
			# function 16 turns on light and makes beep after wait
			
			#trialtype = 1
			#print('first content trial, in endWait')
			#print("SCQTMESSAGE: trigger(16);\n")

			# the statescript function for each arm now produces the beep after recieving the REPLAY_ARM message
			# so goalWell should be updated based on the message from spykshrk not the random number
			## turn on all outer lights
			#for num in range(len(outerWells)):
			#	print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
			#	print("SCQTMESSAGE: trigger(3);\n")
			#	print('current goal is ',str(goalWell[0]))

			#print("SCQTMESSAGE: dio = "+str(centerWell)+";\n")   # turn center light on
			#print("SCQTMESSAGE: trigger(3);\n")
			#print("SCQTMESSAGE: trigger(5);\n")   # display stats


		# save out current goal well to the text file
		#with open("/home/lorenlab/spykshrk_realtime/config/rewarded_arm_trodes.txt","a") as reward_arm_file:
		#		try:
		#			reward_arm_file.write(str(currWell-9)+' '+str(taskState)+' '+str(goalWell[0]-9)+'\n')
		#		finally: 
		#			reward_arm_file.close()


# called by any visit to outer arm
def doOuter(val):
	global outerPumps
	global cuedPumps
	global trialtype
	global allGoal
	global goalWell 
	global currWell
	global lastWell
	global homeWell
	global waslock
	global arm1_Goal
	global arm2_Goal
	global arm3_Goal
	global arm4_Goal
	global home_Goal
	global taskState
	global outerarm_required_rewards
	global outer_arm_reward
	global outer_count_content
	global cued_content_number
	global instructiveTrial

	if trialtype == 2:
		if currWell in goalWell:
			trialtype = 1      # outer satisfied, old: head home next (0). new: head to center (1)

		print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
		print('current well',currWell)
		print('goal well',goalWell)
		print('value',val)
		if currWell in goalWell :  # repeated; reward
			if taskState == 1:
				print("SCQTMESSAGE: rewardWell = "+str(outerPumps[val])+";\n")
			if taskState == 3:
				print("SCQTMESSAGE: rewardWell = "+str(outerPumps[val])+";\n")
			if taskState == 2:
				print("SCQTMESSAGE: rewardWell = "+str(outerPumps[val])+";\n")
			
			# only deliver reward if this is one of the rewarded visits
			if outer_arm_reward:
				print("SCQTMESSAGE: trigger(2);\n")   # deliver reward
				print("SCQTMESSAGE: outer reward delivered;\n")
			else:
				print("SCQTMESSAGE: no outer reward;\n")

			print("SCQTMESSAGE: correctCued = "+str(1)+";\n")
			allGoal+=1
			# create and add to counter for each of the 4 outer arms
			if currWell == outerWells[0]:
				arm1_Goal+=1
				#print('arm1',arm1_Goal)
			elif currWell == outerWells[1]:
				arm2_Goal+=1
				#print('arm2',arm2_Goal)
			elif currWell == outerWells[2]:
				arm3_Goal+=1
				#print('arm3',arm3_Goal)
			elif currWell == outerWells[3]:
				arm4_Goal+=1
				#print('arm4',arm4_Goal)
			#elif currWell == outerWells[0]:
			#	home_Goal+=1
				#print('arm4',arm4_Goal)	
			print('arm1',arm1_Goal,'arm2',arm2_Goal,'arm3',arm3_Goal,'arm4',arm4_Goal)

			# write to a file that will record last rewarded arm so that spykshrk can read it
			# bug: at first content trial it writes all 4 wells, not sure why, after that it works
			# write (currWell - 9) to get back to arms 1-4

			print('current well',currWell)
			with open("/home/lorenlab/spykshrk_realtime/config/rewarded_arm_trodes.txt","a") as reward_arm_file:
				try:
					reward_arm_file.write(str(currWell-9)+' '+str(taskState)+' '+str(goalWell[0])+'\n')
				finally: 
					reward_arm_file.close()

			# if required rewards met for all arms, switch to content trials (taskState=2)
			# could replace this with a vector with the visits for each arm
			if (taskState == 1 and arm1_Goal>=outerarm_required_rewards and arm2_Goal>=outerarm_required_rewards
				 and arm3_Goal>=outerarm_required_rewards and arm4_Goal>=outerarm_required_rewards):
				taskState = 2
				print("SCQTMESSAGE: taskstate = "+str(taskState)+";\n") # update taskstate in SC
				print('switched to content trials')
				# move decoder start to new function below
				#with open("/home/lorenlab/spykshrk_realtime/config/taskstate.txt","a") as reward_arm_file:
				#	try:
				#		reward_arm_file.write(str(2)+'\n')
				#	finally: 
				#		reward_arm_file.close()				

			# TO DO: turn off all lights at end of taskState 3 and set taskState back to 1 in text file
			elif taskState == 3 and arm1_Goal>=2*outerarm_required_rewards and arm2_Goal>=2*outerarm_required_rewards:
				with open("/home/lorenlab/spykshrk_realtime/config/taskstate.txt","a") as reward_arm_file:
					try:
						reward_arm_file.write(str(1)+'\n')
					finally: 
						reward_arm_file.close()	
				print('task finished!')
				print("SCQTMESSAGE: dio = "+str(homeWell)+";\n") # turn off home well
				print("SCQTMESSAGE: trigger(4);\n")
				print("SCQTMESSAGE: dio = "+str(centerWell)+";\n")  #turn off all center and outer well lights
				print("SCQTMESSAGE: trigger(4);\n")
				for num in range(len(outerWells)):
					print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
					print("SCQTMESSAGE: trigger(4);\n")
				
			print("SCQTMESSAGE: goalTotal = "+str(allGoal)+";\n") # update goaltotal in SC

		# for instructive probe trials - reset if wrong well
		elif taskState == 2 and instructiveTrial:
			trialtype = 1
			print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
			print('content probe trial incorrect')

		else:   # wrong well; add to forage record if newly visited
			print("SCQTMESSAGE: otherCount = otherCount + 1;\n") # update othercount in SC

	elif trialtype < 2 and waslock<1:
		pass
		#lockout([0,1])

# called by any visit to outer arm
def endOuter():
	global trialtype
	global outerWells
	global homeWell
	global lastWell
	global currWell
	global goalWell
	global centerWell
	global taskState
	global outer_count_content
	global cued_content_number
	global instructiveTrial

	# note: this should run at the end of the last cued trial, right after switch to taskstate 2
	#print('lastwell',lastWell)
	#print('curr well',currWell)
	# we only want this to happen if he visits correct well
	#if trialtype == 1 and lastWell != currWell and taskState == 1:  # outer satisfied. old: 0, new: 1
	if trialtype == 1 and lastWell != currWell and taskState == 1 and currWell in goalWell:
		#for num in range(len(outerWells)):			# turn off outer lights
		#	print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
		#	print("SCQTMESSAGE: trigger(4);\n")
		for num in range(len(outerWells)):			# turn off outer lights
			print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
			print("SCQTMESSAGE: trigger(4);\n")			
		# now we need to run endHome - to start wait at center
		# original
		#print("SCQTMESSAGE: dio = "+str(homeWell)+";\n")   # turn homewell on
		#print("SCQTMESSAGE: trigger(3);\n")
		#print("SCQTMESSAGE: trigger(5);\n")   # display stats
		# no home
		print("SCQTMESSAGE: dio = "+str(centerWell)+";\n")   # turn center light on
		print("SCQTMESSAGE: trigger(3);\n")
		print("SCQTMESSAGE: trigger(5);\n")   # display stats

		# this line set the variable delaytime and then writes the variable to statescript  
		delaytime = chooseDelay()
		print("SCQTMESSAGE: waittime = "+str(delaytime)+";\n")

		# we may want to define a lockout type here

	# # for first content trial, trigger 13
	# elif taskState == 2 and outer_count_content == 0:
	# 	outer_count_content += 1
	# 	for num in range(len(outerWells)):			# turn off outer lights
	# 		print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
	# 		print("SCQTMESSAGE: trigger(4);\n")
	# 	print('first content trial',outer_count_content)
	# 	print("SCQTMESSAGE: trigger(5);\n")   # display stats
	# 	print("SCQTMESSAGE: trigger(13);\n")

	# leave outer at beginning of taskstate2
	elif trialtype == 1 and lastWell != currWell and taskState == 2 and outer_count_content == 0:
		outer_count_content += 1
		print('first content trial',outer_count_content)
		for num in range(len(outerWells)):			# turn off outer lights
			print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
			print("SCQTMESSAGE: trigger(4);\n")
		print("SCQTMESSAGE: trigger(5);\n")   # display stats
		print("SCQTMESSAGE: dio = "+str(centerWell)+";\n")   # turn center light on
		print("SCQTMESSAGE: trigger(3);\n")
		chooseGoal()		

	# instructive probe trials
	elif trialtype == 1 and lastWell != currWell and taskState == 2 and instructiveTrial:
		outer_count_content += 1
		for num in range(len(outerWells)):			# turn off outer lights
			print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
			print("SCQTMESSAGE: trigger(4);\n")
		print("SCQTMESSAGE: trigger(5);\n")   # display stats
		print("SCQTMESSAGE: dio = "+str(centerWell)+";\n")   # turn center light on
		print("SCQTMESSAGE: trigger(3);\n")
		chooseGoal()

	# instructive content trials
	elif trialtype == 1 and lastWell != currWell and taskState == 2 and currWell in goalWell and not instructiveTrial:
		outer_count_content += 1
		for num in range(len(outerWells)):			# turn off outer lights
			print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
			print("SCQTMESSAGE: trigger(4);\n")
		print("SCQTMESSAGE: trigger(5);\n")   # display stats
		print("SCQTMESSAGE: dio = "+str(centerWell)+";\n")   # turn center light on
		print("SCQTMESSAGE: trigger(3);\n")
		chooseGoal()

	# return to cued trials
	elif trialtype == 1 and lastWell != currWell and taskState == 3:  # outer satisfied. old: 0, new: 1
		for num in range(len(outerWells)):			# turn off outer lights
			print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
			print("SCQTMESSAGE: trigger(4);\n")
		# now we need to run endHome - to start wait at center
		print("SCQTMESSAGE: dio = "+str(centerWell)+";\n")   # turn center light on
		print("SCQTMESSAGE: trigger(3);\n")
		print("SCQTMESSAGE: trigger(5);\n")   # display stats

		# this line set the variable delaytime and then writes the variable to statescript  
		delaytime = chooseDelay()
		print("SCQTMESSAGE: waittime = "+str(delaytime)+";\n")	

# called when "LOCKOUT" printed by statescript or doOuter
def lockout(val):   # turn off all lights for certain amount of time
	global centerWell
	global outerWells
	global lastWell
	global trialtype
	global waslock

	print("lockout val "+str(val)+"\n")
	locktype = int(val[1])
	trialtype = 3
	print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
	print("SCQTMESSAGE: trigger(6);\n")  # start lockout timer in SCQTMESSAGE
	#turn off all lights
	print("SCQTMESSAGE: dio = "+str(homeWell)+";\n") # turn off home well
	print("SCQTMESSAGE: trigger(4);\n")
	print("SCQTMESSAGE: dio = "+str(centerWell)+";\n")  #turn off all center and outer well lights
	print("SCQTMESSAGE: trigger(4);\n")
	for num in range(len(outerWells)):
		print("SCQTMESSAGE: dio = "+str(outerWells[num])+";\n")
		print("SCQTMESSAGE: trigger(4);\n")
	waslock=1
	print("SCQTMESSAGE: waslock = "+str(waslock)+";\n") # turn off home well
	if locktype == 1:
		print("SCQTMESSAGE: locktype1 = locktype1 + 1;\n") # type 1 = wrong well order
	if locktype == 2:
		print("SCQTMESSAGE: locktype2 = locktype2 + 1;\n") # type 2 = impatience at center well

# read from statescript, used to re-start cued arm trials
# NOTE: changed global homeWell to centerWell
def lockend():
	global trialtype
	global centerWell

	# no home: now reset trial type to 1 not 0, and tell statescript
	trialtype = 1
	print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
	# home well
	#print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
	#print("SCQTMESSAGE: dio = "+str(homeWell)+";\n") # turn on home well
	#rint("SCQTMESSAGE: trigger(3);\n")

	# no home
	print("SCQTMESSAGE: dio = "+str(centerWell)+";\n")   # turn center light on
	print("SCQTMESSAGE: trigger(3);\n")
	print("SCQTMESSAGE: trigger(5);\n")   # display stats

	# choose wait time, tell statescript
	delaytime = chooseDelay()
	print("SCQTMESSAGE: waittime = "+str(delaytime)+";\n")

	# set last well to 10 so that loop with center well timer will run
	print("SCQTMESSAGE: lastWell = "+str(10)+";\n")


# called from statescript, when "NEXT_TRIAL" displayed
def startContentTrial():
	global trialtype
	#global content_trial_dist

	# no home: now reset trial type to 1 not 0, and tell statescript
	# with home, keep as trialtype 1
	trialtype = 1
	print("SCQTMESSAGE: trialtype = "+str(trialtype)+";\n")
	print("SCQTMESSAGE: trigger(5);\n")   # display stats

	# choose time between trials
	#content_trial_time = int(np.random.choice(content_trial_dist,1))
	# sample from exponential distribution, mean 30 sec
	# note: 3 sec is added in statescript

	# original line for trial length
	# 30 here is for 30 seconds
	#content_trial_time = int(1000*(1 + np.random.exponential(scale=20, size=None)))
	# for nosepoke version start new trial after 1 sec
	#content_trial_time = 1000

	#print("SCQTMESSAGE: content_trial_time = "+str(content_trial_time)+";\n")

	# start new content wait time
	print('start next content trial')
	print("SCQTMESSAGE: trigger(16);\n")

	# for nosepoke version: also send waittime 
	delaytime = chooseDelay()
	print("SCQTMESSAGE: waittime = "+str(delaytime)+";\n")		

# called from statescript, when "TASKSTATE3" displayed
def returnToCued():
	global taskState

	print('return to cued trials')
	taskState = 3
	# tell decoder it is taskState 3 now
	with open("/home/lorenlab/spykshrk_realtime/config/taskstate.txt","a") as reward_arm_file:
		try:
			reward_arm_file.write(str(3)+'\n')
		finally: 
			reward_arm_file.close()	
	# use lockend to start new cued trial
	lockend()

# called from statescript, when "waslock" displayed
def updateWaslock(val):
	global waslock

	waslock = int(val[1])
	print("SCQTMESSAGE: waslock = "+str(waslock)+";\n")

# Function: generate cowbell sound
def generate_beep():

	File='Beep.wav'
	#File='noise.wav'
	spf = wave.open(File, 'rb')
	signal = spf.readframes(-1)
	signal = np.fromstring(signal, 'Int16')
	p = pyaudio.PyAudio()
	stream = p.open(format =
				p.get_format_from_width(spf.getsampwidth()),
				channels = 1,
				rate = spf.getframerate(),
				output = True)
	#play 
	data = struct.pack("%dh"%(len(signal)), *list(signal))    
	stream.write(data)
	stream.close()
	p.terminate()

def makewhitenoise():  #play white noise for duration of lockout
	global locksoundlength

	soundlength = int(44100*locksoundlength/1000)
	p = pyaudio.PyAudio()
	stream = p.open(format = 8, channels = 1, rate = 44100, output = True)
	whitenoise = np.random.randint(700,size = soundlength)
	data = struct.pack("%dh"%(len(whitenoise)), *list(whitenoise))    
	stream.write(data)
	stream.close()
	p.terminate()

def decoder_task2():
	print('write taskstate2 for decoder')
	with open("/home/lorenlab/spykshrk_realtime/config/taskstate.txt","a") as reward_arm_file:
		try:
			reward_arm_file.write(str(2)+'\n')
		finally: 
			reward_arm_file.close()	


# This is the custom callback function. When events occur, addScQtEvent will
# call this function. This function MUST BE NAMED 'callback'!!!!
def callback(line):

	global waslock
	global goalWell
	global replay_arm 

	if line.find("UP") >= 0: #input triggered
		pokeIn(re.findall(r'\d+',line))
	if line.find("DOWN") >= 0: #input triggered
		pokeOut(re.findall(r'\d+',line))
	# add ripwait to holding vector
	if line.find("riptime") >=0:
		addtime(re.findall(r'\d+',line))
	if line.find("BEEP1") >= 0:
		chooseGoal()
		#beep()
	# this is only called by cued trials, remove sound cue
	if line.find("BEEP2") >= 0:
		beep_center()
		#generate_beep()
		#mec added to turn on outer lights at same time as beep
		endWait()
	# for content trials. beep sound
	if line.find("BEEP3") >= 0:
		generate_beep()
	# for content trials. reward delivery
	if line.find("BEEP4") >= 0:
		beep_center()
		endWait()
	if line.find("CONTENT_END") >= 0:
		chooseGoal()
	
	if line.find("LOCKOUT") >= 0: # lockout procedure
		lockout(re.findall(r'\d+',line))
	if line.find("LOCKEND") >= 0: # reset trialtype to 0
		lockend()
	if line.find("WHITENOISE") >= 0: # make noise during lockout
		makewhitenoise()
	if line.find("waslock") >= 0:  #update waslock value
		updateWaslock(re.findall(r'\d+',line))
	# function for reading specific arm output from spykshrk
	# note: had to reprint statescript variable replay_arm after it comes in, in order for python to see it
	#if line.find("replay_arm") >= 0:
	#	replay_arm = re.findall(r'\d+',line)
	#	replay_arm = int(replay_arm[1])
	#	print('replay arm from callback', replay_arm)
	# to start next content trial based on function 18 in statescript
	if line.find("NEXT_TRIAL") >= 0:
		startContentTrial()
	# to switch back to cued trials (at begin of function 16 in statescript)
	if line.find("TASKSTATE3") >= 0:
		returnToCued()	
	# to write taskstate2 to text file for decoder
	if line.find("DECODER_TASK2") >= 0:
		decoder_task2()	


# all global variables are initialized
# all variables can be used anywhere in this script
# define wells, old outer: 10,11,12,13
# 1st version: wells 8 (8) and 4 (12)
# 2nd version: arms 6 (10) and 2 (14)
# 3rd version: arms 7 (9) and 3 (13)
# 4th version: arms 5(11) and 1 (15)
# tree track: arm 2 (14) and 1 (15) 
# 4 arm: arm5 (12), arm6 (13), arm7 (14), arm8 (15) 

homeWell = 1
centerWell = 2
#outerWells = [14,15]
outerWells = [12,13,14,15]
#cuedWells=[1,8,12]
#cuedWells = [1,10,14]
#cuedWells = [1,9,13]
#cuedWells = [1,11,15]

# define pumps +9 for arm
# old outer: 19,20,21,22
# pumps: 8 (17) and 12 (21)
# 2nd version: 10 (19) and 14 (23)
# 3rd version: 9 (18) and 13 (22)
# 4th version: 11 (20) and 15 (24)
# tree track: 14 (23) and 15 (24)
# 4 arm: 21,22,23,24

homePump = 25
centerPump = 26
#outerPumps = [25,17,21]

outerPumps = [21,22,23,24]
#cuedPumps = [25,20,24]

#global variables
# new startup: lastwell = 10, before lastwell = -1
lastWell = -1
currWell = -1

# no home: initiaze with trialtype 2 (was 0 before) and turn on one outer well light
# new startup: trialtype = 1, before trialtype = 2
trialtype = 1

allGoal = 0

# counters for visit to each arm
arm1_Goal = 0
arm2_Goal = 0
arm3_Goal = 0
arm4_Goal = 0
home_Goal = 0
# counter for assignment of each arm
arm1_counter = 0
arm2_counter = 0
arm3_counter = 0
arm4_counter = 0
arm1_order12 = []
arm2_order12 = []
arm3_order12 = []
arm4_order12 = []
arm1_order_2 = []
arm2_order_2 = []
arm3_order_2 = []
arm4_order_2 = []
outer_arm_reward = 0
task3_trial_counter = 0
outerarm_required_rewards = 8
cued_content_number = 50
outer_count_content = 0
homecount = 0
instructiveTrial = 0

# task state variable
# 1 = cued reward well
# 2 = content contigent rewrad well
taskState = 1
# should start at -1 so that it doesnt return a real arm
# this may require a check that replay-arm does not equal -1
replay_arm = [13]

# choose one well at random of the 4
# no home - try to initalize with well 10 and a list (was 0 before)
goalWell = [10]
cued_trial_counter = 0
oldGoal = 0

startwaitdist = [100, 100, 100]
waitdist = [100]
# for 8-11
content_waitdist = [5000,7000,8000,9000,11000,13000,15000]
#content_waitdist = [5000,7000,9000,11000,13000,15000]
content_waitdist_early = [2000,3000,4000]
#content_trial_dist = [5000]
count = 0

locksoundlength = 1000
print(goalWell)
waslock=0
centercount = 0
centercount_content = 0

# ---------------------------------------------------------------------
#	Multi Linear Track 
#   verison with 8 pumps: one for each well, no switches
	
#	This works with StateScript to control four lanes of linear track going 
#   simultaneously. Each lane has two reward pumps, one for each well. There are
#   no switches in this version of the code.

# 	A GUI allows you to enter information about a session, and it will send
# 	an email when a session is complete.

# 	Written by David Kastner and Eric Angevine Miller
# 	Contact (Eric): angevineMiller@gmail.com
# ---------------------------------------------------------------------

import math
import struct
import re
import time
from tkinter import *
import smtplib


# ----------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------
# 	Experiment Specific Variables.
#   This is all you need to edit when setting up a new multi linear track.
# ------------------------------------------------------------------------

# Define the SpikeGadgets ports corresponding to reward wells and pumps
# REQUIREMENTS:
#     'lanes' and 'pumps' must be lists of lists. Each inner list coresponds to a lane, 
#     and must contain exactly 2 elements, corresponding to the well/pump number 
#     at opposite ends of that lane. Furthermore, the well/pump numbers at corresponding
#     indices of 'lanes' and 'pumps' must be associated. Finally, the numbers must be unique
#     across both 'lanes' and 'pumps'.
lanes = [[19,25], [13,24], [1,4], [23,28]]  # sublists are opposing ports in a lane 9- C, 10 -L, 26 -R
pumps = [[26, 20], [9,12], [5,6], [7,8]]    # sublists are pumps corresponding to opposing ports in a lane 


# Who to email when a session ends
david = '6507048329@txt.att.net'
cristofer = 'cristofer.holobetz@berkeley.edu'

#who_to_email = [david]

# ----------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------


# ----------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------
# 	Internal Variable Initializations
# 	Do not edit these variables unless you know what you're doing.
# ----------------------------------------------------------------------------------

last_well_visit = [0 for l in range(len(lanes))]  # last well visited for each lane (init to 0)
animals = [i+1 for i in range(len(lanes))]    # Update with animals currently running in each track
max_time = 60		# User can define how long session will last (minutes)
start_time = 0		# Update with system time of beginning of session
session_is_over = False
stop_after_time_limit = False    # Whether or not to stop behavior after time limit.

# Make a flattened list of the pumps
# Use this to map from the pumps variable to the StateScript rewardPump variables
# pump_idx is used in the initialize_track() and deliver_reward() methods below.
pump_idx = []
for pump_pair in pumps:
	pump_idx.append(pump_pair[0])
	pump_idx.append(pump_pair[1])


# Convenience mappings from well port to its associated pump, lane, and opposing well
well_to_pump = {}  # well port --> pump port
well_to_lane = {}  # well port --> lane number
opposing_well = {} # well port --> opposing well port
for i in range(len(lanes)):
	lane = lanes[i]
	pump = pumps[i]
	well_to_lane[lane[0]] = i
	well_to_lane[lane[1]] = i
	opposing_well[lane[0]] = lane[1]
	opposing_well[lane[1]] = lane[0]
	well_to_pump[lane[0]] = pump[0]
	well_to_pump[lane[1]] = pump[1]

rewards_per_lane = [0 for l in lanes]		# Keep track of received rewards for each lane/animal.
user_has_saved = False			# Change to True when user confirms they have saved.
# -------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------


# ----------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# 	Functions for Interfacing with StateScript
# ------------------------------------------------------------------------------

# This is a required function, which MUST BE NAMED 'callback'!!!!
def callback(line):
	'''
		Called on each line of StateScript output. Callbacks are handled by parsing the line.
	'''
	global session_is_over
	global stop_after_time_limit
	# If the session is already over and the user decided to stop behavior after the time
	# limit, do not process this callback.
	if session_is_over and stop_after_time_limit:
		return
	# Process an "UP (port)" line, which is a nose poke, if this was NOT the last
	# port visited in this lane. (i.e. don't register repeat pokes in the same well)
	if line.find("UP") >= 0:
		portList = re.findall(r'\d+',line)
		port = int(portList[1])
		lane = well_to_lane[port]  # port is the well the animal poked at
		if last_well_visit[lane] != port:
			last_well_visit[lane] = port
			pokeIn(port)

def pokeOut(port):
	pass
	

def pokeIn(port):
	'''
		This function is called when StateScript sends an "UP (port)" signal.	
	'''
	global max_time
	global start_time
	global session_is_over
	global stop_after_time_limit
	current_well = port  # the port argument corresponds to the well the animal poked at
	current_opposing_well = opposing_well[current_well]
	current_pump = well_to_pump[current_well]
	current_lane = well_to_lane[current_well]

	# print("In pokeIn: " + str(port))

	# Deliver the reward at this well by activating the appropriate pump
	deliver_reward(current_pump)

	# Switch light to the opposing well in this lane.
	turn_off(current_well)
	turn_on(current_opposing_well)

	# Update and print the reward tallys for all animals.
	rewards_per_lane[current_lane] += 1
	print_tally()

	# If the session is not already over, update the elapsed time and see if it is now over
	# If it is now over, handle the session-over logic.
	if not session_is_over:
		elapsed_time_minutes, elapsed_time_seconds = divmod(time.time() - start_time, 60)
		if elapsed_time_minutes >= max_time:
			session_is_over = True
			print("SCQTMESSAGE: disp('The session is complete.');\n")
			if stop_after_time_limit:
				stop_track()
			send_message(elapsed_time_minutes, elapsed_time_seconds, who_to_email)
	
def turn_on(port):
	'''
		Set this port to 1. Used to turn a well light on.
	'''
	print("SCQTMESSAGE: portout[" + str(port) + "] = 1;\n")

def turn_off(port):
	'''
		Set this port to 0. Used to turn a well light off.
	'''
	print("SCQTMESSAGE: portout[" + str(port) + "] = 0;\n")

# def flip(port):
# 	'''
# 		Flip port between 0/1. Used to flip the switch between opposing wells.
# 	'''
# 	print("SCQTMESSAGE: portout[" + str(port) + "] = flip;\n")

def deliver_reward(reward_pump):
	'''
		Trigger the StateScript reward delivery function corresponding to this pump.
		(Recall there is a separate reward delivery function for each pump.)
	'''
	# print("In deliver_reward: " + str(reward_pump))
	idx = pump_idx.index(reward_pump) + 1
	print("SCQTMESSAGE: trigger(" + str(idx) + ");\n")

def print_tally():
	'''
		Print the current reward tally for each animal.
		Called after each animal earns a new reward.
	'''
	print("SCQTMESSAGE: disp('--------------------------------------');\n")
	for i in range(len(animals)):
		line = "Animal " + str(animals[i]) + ": " + str(rewards_per_lane[i])
		print("SCQTMESSAGE: disp('" + line + "');\n")
	print("SCQTMESSAGE: disp('--------------------------------------');\n")

def initialize_track():
	'''
		Turn on all well lights.
		Assign the statescript rewardPump variables to the correct ports.
	'''
	# Turn on all well lights
	for lane in lanes:
		turn_on(lane[0])
		turn_on(lane[1])
	# Set the ports for each reward pump variable
	# The index of each pump is defined via the flattened pump list
	for i in range(len(pump_idx)):
		idx = pump_idx[i]
		print("SCQTMESSAGE: rewardPump" + str(i+1) + " = " + str(idx) + ";\n")

def stop_track():
	'''
		Turn off all lights and switches.
		Called only if user says to stop behavior after time limit.
	'''
	print("SCQTMESSAGE: disp('Stopping track behavior.');\n")
	# Turn off all well lights
	for lane in lanes:
		turn_off(lane[0])
		turn_off(lane[1])

# ----------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------




# ------------------------------------------------------------------------------
# 	Functions for GUIs
# ------------------------------------------------------------------------------
def yes_saving():
	'''
		Called if user says "Yes" to having saved their data.
	'''
	global user_has_saved
	saving_display.destroy()
	user_has_saved = True

def no_saving():
	'''
		Called if user says "No" to having saved their data.
	'''
	saving_display.destroy()
	print("SCQTMESSAGE: disp('Please save before beginning a new session.');\n")

def run_session(display, stop_behavior):
	'''
		Called after user clicks "Begin" in the session initialization GUI.

		Arguments:
			display - tkinter window for the session init GUI
			stop_behavior - radio button variable for whether to stop after time limit
	'''
	global animals
	global max_time
	global start_time
	global stop_after_time_limit
	if stop_behavior.get() == 1:
		stop_after_time_limit = True
	animals[0] = int(E1.get())
	animals[1] = int(E2.get())
	animals[2] = int(E3.get())
	animals[3] = int(E4.get())
	max_time = int(E5.get())
	display.destroy()
	initialize_track()
	print("Beginning new " + str(max_time) + " minute session.")
	start_time = time.time()

def send_message(elapsed_min, elapsed_sec, who_to_email):
	'''
		Send email to people when animals have completed 
		the specified time limit.
	'''

	gmail_user = 'autoBehavior20@gmail.com'  
	gmail_password = 'ByNLMqvM(*Uy3P'

	sent_from = gmail_user
	to = who_to_email  
	subject = 'Multi Linear Track Session Complete'  
	body = "The animals have finished.\n\n" + \
			"Elapsed Time: " + str(int(elapsed_min)) + " min, " + \
				str(int(elapsed_sec)) + " sec.\n\n" + \
			"Results:\n" + \
			"Rat " + str(animals[0]) + ": " + str(rewards_per_lane[0]) + "\n" + \
			"Rat " + str(animals[1]) + ": " + str(rewards_per_lane[1]) + "\n" + \
			"Rat " + str(animals[2]) + ": " + str(rewards_per_lane[2]) + "\n" + \
			"Rat " + str(animals[3]) + ": " + str(rewards_per_lane[3]) + "\n\n" + \
			"Sincerely,\nMulti Linear Track"

	email_text = """ 
    From: %s  
    To: %s  
    Subject: %s

    %s
	""" % (sent_from, ", ".join(to), subject, body)

	try:  
		server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
		server.ehlo()
		server.login(gmail_user, gmail_password)
		server.sendmail(sent_from, to, email_text)
		server.close()
		print("Email sent!")
	except:  
		print("Something went wrong...")
# ----------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
#  	GUI Styling variables
# ------------------------------------------------------------------------------ 
window_bg_color = "#f7f9f9"
yes_button_off = "#82e0aa"
yes_button_on = "#2ecc71"
no_button_off = "#f1948a"
no_button_on = "#e74c3c"
# ------------------------------------------------------------------------------ 


# ----------------------------------------------------------------------------------
# ------------------------------------------------------------------------------
# 	Run the GUI to check whether the user has saved. 
# 	We will only let the experiment begin if they have saved.
# ------------------------------------------------------------------------------
saving_display = Tk()
saving_display.title("Save Your Work")
saving_display.configure(background = window_bg_color)

screen_width = saving_display.winfo_screenwidth()
screen_height = saving_display.winfo_screenheight()
x_offset = str(int(screen_width/3))
y_offset = str(int(screen_height/3))
window_pos = str(int(screen_width/8)) + "x" + str(int(screen_height/6)) + "+" + x_offset + "+" + y_offset
saving_display.geometry(window_pos)

save_frame_top = Frame(saving_display, bg=window_bg_color)
save_frame_top.pack(side = TOP, expand=True)
save_frame_bottom = Frame(saving_display, bg=window_bg_color)
save_frame_bottom.pack(side = BOTTOM, expand=True)
yes_frame = Frame(save_frame_bottom, bg=window_bg_color)
yes_frame.pack(side=LEFT, expand=True, padx = 20)
no_frame = Frame(save_frame_bottom, bg=window_bg_color)
no_frame.pack(side=LEFT, expand=True, padx = 20)

save_label_top = Label(save_frame_top, text="Have you saved your data?",  
						font=("Times", 12, "bold"), bg = window_bg_color)
save_label_top.pack()

save_yes_button = Button(yes_frame, text ="Yes", bg=yes_button_off, relief=RAISED,
						activebackground = yes_button_on, padx = 20, command = yes_saving)
save_yes_button.pack(fill=BOTH)
save_no_button = Button(no_frame, text ="No", bg=no_button_off, relief=RAISED,
					activebackground = no_button_on, padx = 20, command = no_saving)
save_no_button.pack(fill=BOTH)

saving_display.mainloop()
# ------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------


# ------------------------------------------------------------------------------
# 	Run the session initialization GUI after the User confirms they have saved. 
# ------------------------------------------------------------------------------
if user_has_saved:
	display = Tk()
	display.title("Initialize the Session")
	display.configure(bg = window_bg_color)

	screen_width = display.winfo_screenwidth()
	screen_height = display.winfo_screenheight()
	x_offset = str(int(screen_width/4))
	y_offset = str(int(screen_height/3))
	window_pos = str(int(screen_width/7)) + "x" + str(int(screen_height/4)) + "+" + x_offset + "+" + y_offset
	display.geometry(window_pos)

	frame1 = Frame(display, bg = window_bg_color)
	frame1.pack(side = TOP)
	frame2 = Frame(display, bg = window_bg_color)
	frame2.pack(side = TOP)
	frame3 = Frame(display, bg = window_bg_color)
	frame3.pack(side = TOP)
	frame4 = Frame(display, bg = window_bg_color)
	frame4.pack(side = TOP)
	frame5 = Frame(display, bg = window_bg_color, pady = 20)
	frame5.pack(side = BOTTOM)

	L1 = Label(frame1, text="Lane 1 is", bg = window_bg_color, padx = 10, pady = 10)
	L1.pack(side = LEFT)
	E1 = Entry(frame1, bd = 3, width = 3, bg = window_bg_color, relief=FLAT)
	E1.pack(side = LEFT)
	E1.insert(0, str(animals[0]))

	L2 = Label(frame1, text="Lane 2 is", bg = window_bg_color, padx = 10, pady = 10)
	L2.pack(side = LEFT)
	E2 = Entry(frame1, bd = 3, width = 3, bg = window_bg_color, relief=FLAT)
	E2.pack(side = LEFT)
	E2.insert(0, str(animals[1]))

	L3 = Label(frame2, text="Lane 3 is", bg = window_bg_color, padx = 10, pady = 10)
	L3.pack(side = LEFT)
	E3 = Entry(frame2, bd = 3, width = 3, bg = window_bg_color, relief=FLAT)
	E3.pack(side = LEFT)
	E3.insert(0, str(animals[2]))

	L4 = Label(frame2, text="Lane 4 is", bg = window_bg_color, padx = 10, pady = 10)
	L4.pack(side = LEFT)
	E4 = Entry(frame2, bd = 3, width = 3, bg = window_bg_color, relief=FLAT)
	E4.pack(side = LEFT)
	E4.insert(0, str(animals[3]))

	L5 = Label(frame3, text="Session time limit (minutes)", bg = window_bg_color, padx = 10, pady = 20)
	L5.pack(side = LEFT)
	E5 = Entry(frame3, bd = 3, width = 3, bg = window_bg_color, relief=FLAT)
	E5.pack(side = LEFT)
	E5.insert(0, '60')

	L6 = Label(frame4, text="Stop behavior after time limit?", bg = window_bg_color, pady = 20)
	L6.pack(side = LEFT)
	stop_behavior = IntVar()
	R1 = Radiobutton(frame4, text="No, keep behavior running.", variable=stop_behavior, 
						value=0, bg = window_bg_color, padx = 10, borderwidth=0)
	R1.pack(anchor = W)
	R2 = Radiobutton(frame4, text="Yes, stop behavior.", variable=stop_behavior, 
						value=1, bg = window_bg_color, padx = 10, borderwidth=0)
	R2.pack(anchor = W)

	B = Button(frame5, text ="Begin Session", bg=yes_button_off, activebackground=yes_button_on, relief=RAISED,
				command = lambda: run_session(display, stop_behavior), padx=25, pady=25)
	B.pack(side = BOTTOM)

	display.mainloop()

# ----------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------


	

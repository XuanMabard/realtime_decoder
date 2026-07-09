% PROGRAM NAME: 	V8pre_goal_nowait
% AUTHOR: AKG
% DESCRIPTION: pretraining regime 	

int deliverPeriodBox= 300			% how long to deliver the reward at home/center, 100 uL
int deliverPeriodBox_content = 300	% milk delivery time for content trials, 100 uL
int deliverPeriodOuter= 450   		% how long to deliver the reward at outer wells, 150 uL
int lockoutPeriod= 10000 			% length of lockout
int proxTime = 200 					% amount of time allowed to be away from nose poke

int rewardWell = 0
int currWell = 0
int lastWell = 0
int dio = 0
int homeCount = 0		% number of times rewarded at home
int centerCount = 0		% number of times rewarded at wait well
int locktype1 = 0 		% number of times lockout: order error
int locktype2 = 0 		% number of times lockout: not holding in center
int trialtype = 1
int taskstate = 1
int goalTotal = 0		% cumulative num outer visits
int otherCount = 0
int waittime = 0
int proximity = 0
int waslock = 0

int session_type = 1						% 1: timer, 0: decoder
int target_replay_wait = 3000
int reward_avail_wait = 1500				% reward window
int content_trial_time = 30000				% first time between trials
int content_trials_time_limit = 1800000		% box time
int reward_avail = 0
int reward_delivered = 0
int contentReward = 0
int contentTrialCount = 0
% int content_trials_limit = 40
int content_trials_finish = 0
int pokein_home = 0

% initialize lights at outer well (was home)
portout[1] = 0
portout[2] = 1

portout[10] = 0
portout[11] = 0
portout[12] = 0
portout[13] = 0
;

% function to deliver reward to box wells
% size of reward determined by taskstate
function 1
	if taskstate == 1 do
		portout[rewardWell]=1 % reward
		do in deliverPeriodBox 
			portout[rewardWell]=0 % reset reward
		end
	else if taskstate == 3 do
		portout[rewardWell]=1 % reward
		do in deliverPeriodBox 
			portout[rewardWell]=0 % reset reward
		end
	% taskstate 2	
	else do
		disp('content reward at home')
		portout[rewardWell]=1 % reward
		do in deliverPeriodBox_content 
			portout[rewardWell]=0 % reset reward
		end
	end	
end;

% function to deliver reward to outer wells
function 2
	disp('outer reward')	
	portout[rewardWell]=1 % reward
	do in deliverPeriodOuter 
		portout[rewardWell]=0 % reset reward
	end	
end;

% Function to turn on output
function 3
	portout[dio]=1
end;

% function to turn off output
function 4	
	portout[dio]=0	
end;

%display status to scatesscript terminal and saved in sc log
function 5
	disp(centerCount)
	disp(goalTotal)
	disp(locktype1)
	disp(locktype2)
	disp(otherCount)
	disp(contentTrialCount)
	disp(contentReward)
end;

function 6 % end lockout and reactivate home
	disp('WHITENOISE')	
	do in lockoutPeriod
		disp('LOCKEND')
	end
end;

% function to flip light in port 6
function 15
	disp('trigger from spykshrk')	
	portout[6]=1 % reward
	do in 100 
		portout[6]=0 % reset reward
	end	
end;

% timer for all content trials
function 19
	disp('start content trial timer')
	do in content_trials_time_limit
		content_trials_finish = 1
	end
end;

% timer for visting home well after beep
function 17
	disp('home well reward time after beep')
	do in reward_avail_wait
		portout[1]=0
		reward_avail = 0
	end
end;

% timer for time between trials - to start next trial text NEXT_TRIAL
% first content trial: 60 sec
% start timer for content session here too - moved to function 13
function 18
	disp('end content trial')
	disp('delay between trials')
	disp(content_trial_time)
	do in content_trial_time
		disp('NEXT_TRIAL')
	end
	%if contentTrialCount == 1 do
	%	trigger(19)
	%end
end;

% could make a function to run the timer for content wait
% at end of wait turn on home light and make beep
% cutoff was in trials before, now it is time
function 16
	%if contentTrialCount == content_trials_limit do
	if content_trials_finish == 1 do
		taskstate = 3
		disp('TASKSTATE3')
	else do
		contentTrialCount = contentTrialCount + 1
		disp('start content trial')
		disp(content_trial_time)
		%disp(taskstate)
		do in target_replay_wait
			portout[1]=1
			disp('BEEP3')
			reward_avail = 1
			reward_delivered = 0
			trigger(17)
			trigger(18)
			% to deliver reward while poked at home
			if pokein_home == 1 do
				disp('reward while poked')
				disp('BEEP4')
				reward_delivered = 1
				contentReward = contentReward + 1
			end			
		end
	end
end;

% first content trial: turn on home light, no time limit
function 13
	contentTrialCount = contentTrialCount + 1
	disp('start content trial')
	disp(content_trial_time)
	%disp(taskstate)
	trigger(19)
	portout[1]=1
	reward_delivered = 0
	do in target_replay_wait
		if session_type == 1 do
			trigger(18)
		end		
	end
end;

%function for testing statescript message
function 14
	disp('shortcut message any ripple')
end;

% CALLBACKS -- EVENT-DRIVEN TRIGGERS
callback portin[1] up % home well
	currWell = 1
	disp('UP 1')
	pokein_home = 1

	% timer without nosepoke: functions 16, 17, 18

	% first content trial, deliver 1 reward
	if (taskstate == 2 && trialtype == 1 && contentTrialCount == 1 && reward_delivered == 0) do
		contentReward = contentReward + 1
		disp('1st content trial - reward delivered')
		disp('BEEP4')
		reward_delivered = 1

	% for content trials, deliver 1 reward
	else if (taskstate == 2 && trialtype == 1 && reward_avail == 1 && reward_delivered == 0) do
		contentReward = contentReward + 1
		disp('content trial - reward delivered')
		disp('BEEP4')
		reward_delivered = 1

	% if not reward avail, do nothing
	else if (taskstate == 2 && reward_avail == 0) do
		%disp('content trial - no reward yet')

	% are we using waslock? dont think so
	%waslock = 0
	%disp(waslock)

	end
end;

callback portin[1] down
	lastWell = 1
	disp('DOWN 1')
	pokein_home = 0
end;

callback portin[2] up % center well
	currWell = 2 % well currently active
	disp('UP 2')

	% MEC: old lastWell == 0. new: > 2

	% after lockout, set lastWell to 10
	if (taskstate == 1 && trialtype == 1) do
		if lastWell != currWell do
			disp('start 1st cued trial')
			proximity = 1
			do in waittime
				if proximity > 0 do
					proximity = 0
					trialtype = 2
					disp('BEEP1')
					disp('BEEP2')
				end
			end
		else do 
			proximity=proximity+1
		end

	% return to cued trials in taskstate 3
	else if (taskstate == 3 && trialtype == 1) do
		if lastWell != currWell do
			disp('start 2nd cued trial')
			proximity = 1
			do in waittime
				if proximity > 0 do
					proximity = 0
					trialtype = 2
					disp('BEEP1')
					disp('BEEP2')
				end
			end
		else do 
			proximity=proximity+1
		end

	else do
		% create lockout 1 for order error		
		if (trialtype != 3 &&  currWell != lastWell && waslock != 1) do 
			disp('LOCKOUT 1')
		end
	end

end;

callback portin[2] down
	lastWell=2 % well left, now last well
	disp('DOWN 2')

	% creates lockout 2: not waiting
	if proximity>0 do
		do in proxTime	
			proximity=proximity-1	
			if (proximity <1 && trialtype <2) do
				disp('LOCKOUT 2')
			end	
		end
	end
end;

% outer arm CALLBACKS

callback portin[8] up
	currWell = 8
	if currWell != lastWell do
		disp('UP 8')
	end
end;

callback portin[8] down
	lastWell = 8
	disp('DOWN 8')
end;

callback portin[12] up
	currWell = 12
	if currWell != lastWell do
		disp('UP 12')
	end
end;

callback portin[12] down
	lastWell = 12
	disp('DOWN 12')
end;


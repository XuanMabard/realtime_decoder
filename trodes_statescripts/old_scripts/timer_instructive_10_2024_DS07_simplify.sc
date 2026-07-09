% PROGRAM NAME: 	Content Discrimination Task 
% AUTHOR: Donghoon Shin -- shinapses@gmail.com
% DESCRIPTION: Pretraining 	
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


% PARAMETERS to change
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
int reward_window_outer_arm = 10000 % (DS) window of outer arm reward 

int deliverPeriodBox= 275			% how long to deliver the reward at back/center, 100 uL
int deliverPeriodBox_content = 275	% milk delivery time for content trials, 100 uL
int deliverPeriodOuter= 275   		% how long to deliver the reward at outer wells, 150 uL -- if 400; reduced
int lockoutPeriod_timeout= 10000 			% length of lockout after not going to the outer arm after a beep
int lockoutPeriod_centerReward = 0  %(DS) if the BEEP sound happens right after the rat started to consume reward, it won't react
int choice_window = 1 % to have decision_timeout or not
int content_trial_time = 5000				% first time between trials


int content_trials_time_limit = 2400000		% box time 2400000 = 40 min; 1800000 = 30min, 1200000 = 20min

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%5

int rewardWell = 0
int currWell = 0
int lastWell = 0
int dio = 0
int backCount = 0		% number of times rewarded at back
int centerCount = 0		% number of times rewarded at wait well
int trialtype = 1              % (DS)Python- 0 go to back,1 go to center, 2 go to outer, 3 lockout
int taskstate = 1
int goalTotal = 0		% cumulative num outer visits
int otherCount = 0
int contentOuterCount = 0
int waittime = 0
int proximity = 0
int waslock = 0

int session_type = 1						% 1: timer, 0: decoder
int target_replay_wait = 10
int reward_avail_wait = 3000				% reward window -- for instructive task, make it infinite
int reward_avail = 0
int reward_available_at_center = 0
int reward_delivered = 0
int contentReward = 0
int contentTrialCount = 0
int content_trials_limit = 80 % if center port does not give reward all the time.
int content_trials_finish = 0
int pokein_center = 0
int correctCued = 1
int target_location = 0
int contentCorrectDecision = 0
int wrong_outer_poke = 0 % when the rat pokes the outer arm during task state 2 before beep
int decision_timeout_number = 0 %(DS) how many times that rat did not respond
int decision_timeout = 0 % (DS) a bit indicating that decision timeout
int reward_available_out_if_poke = 0

% initialize lights at outer well (was back)
portout[9] = 0  % arm 1
portout[15] = 0 % arm 2
portout[7] = 1  % center
portout[5] = 0  % back




% FUNCTIONS 
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% function to deliver reward to box wells
% size of reward determined by taskstate
function 1
	if taskstate == 1 do
		portout[rewardWell]=1 % reward
		do in deliverPeriodBox 
			portout[rewardWell]=0 % reset reward
		end
	else if taskstate == 2 do
		%disp('content reward at back')
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
	disp(contentTrialCount)
	disp(contentCorrectDecision)
	disp(decision_timeout_number)
	disp(contentOuterCount)
end;

% timer for all content trials
function 19
	disp('start content trial timer')
	do in content_trials_time_limit
		content_trials_finish = 1
	end
end;

% timer for visting center well after beep
function 17
	disp('center well reward time after beep')
	do in reward_avail_wait
		%portout[7]=0
		reward_avail = 0
	end
end;

%% timer for time between trials - to start next trial text NEXT_TRIAL
%% first content trial: 60 sec
%% start timer for content session here too - moved to function 13
function 18
	disp('FUTURE BEEP')
	disp(content_trial_time)
	do in content_trial_time
		disp('CURRENT BEEP')
		if (wrong_outer_poke == 0 && reward_available_at_center == 0 && decision_timeout ==0 && reward_available_out_if_poke == 0) do
			disp('BEEP READY')
			reward_available_out_if_poke = 1
		end
	end
end;

% this is function for timer trials
% could make a function to run the timer for content wait
% at end of wait turn on back light and make beep
% cutoff was in trials before, now it is time
function 16
	if (content_trials_finish == 1 || contentReward >= content_trials_limit) do
		taskstate = 3
		disp('TERMINATE EPOCH')
	else do
		contentTrialCount = contentTrialCount + 1
		disp('start content trial')
		%disp(content_trial_time)
		%disp(taskstate)
		disp('BEEP3')
		portout[7]=0
		reward_avail = 1
		reward_delivered = 0
		contentReward = contentReward + 1

		if (target_location == 1) do    
			portout[9]=1
		else if (target_location == 2) do
			portout[15]=1
		end	

		if (choice_window == 1) do
			do in reward_window_outer_arm
				disp(reward_window_outer_arm) 
				if (reward_avail == 1 && reward_available_at_center != 1 )  do
					disp('WHITENOISE')
					reward_avail = 0
					reward_delivered = 0
					reward_available_at_center = 0
					portout[9] =0
					portout[15]=0
					portout[7] =1
					%trigger(18)
					disp('DECISION TIMEOUT')
					decision_timeout = 1
					decision_timeout_number = decision_timeout_number + 1
				end	
			end
		end
	end
end;


% first content trial
function 13
	disp(content_trial_time)
	trigger(19)
	portout[7]=1
	reward_delivered = 0
	% this is for timer trials
	do in lockoutPeriod_centerReward
		if session_type == 1 do
			trigger(18)
		end		
	end
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%




% CALLBACKS -- EVENT-DRIVEN TRIGGERS
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
callback portin[7] up % center well
	currWell = 7 % well currently active
	disp('UP 7')
	pokein_center = 1

	% taskstate == 1
	if (taskstate == 1 && trialtype == 1 && correctCued == 1) do
		if lastWell != currWell do
			disp('start 1st cued trial')
			correctCued = 0
			proximity = 1
			do in waittime % currently waittime =0
				if proximity > 0 do
					proximity = 0
					trialtype = 2
					disp('BEEP1') % after BEEP1, pythonObserver chooseGoal
					disp('BEEP2') % give reward at the center (beep_center)
				end
			end
		else do 
			proximity=proximity+1
		end

	% taskstate == 2
	else if (taskstate == 2 && trialtype == 1) do
		
		% first content trial, deliver 1 reward
		% try to make this first nose poke at center during task2 contentTrialCount replaced with contentReward
		if (contentReward == 0 && reward_delivered == 0) do
			disp('1st content trial - reward delivered')
			disp('BEEP4')
			disp('DECODER_TASK2')
			% should this be 2?, was 1
			%dio = 2
			%trigger(4)
			reward_delivered = 1
			portout[7]=1

		% only make a sound when the rat pokes the center port
		else if (reward_available_out_if_poke == 1 && reward_available_at_center == 0) do
			disp('NEXT_TRIAL')
			reward_available_out_if_poke = 0

		% for content trials, deliver 1 reward
		else if (reward_available_at_center == 1) do
			%disp('content trial - reward delivered')
			disp('BEEP4')
			reward_available_at_center = 0
			reward_avail = 0
			do in lockoutPeriod_centerReward % because if the timer interval is too small, the rat will not be able to go 
				trigger(18)
			end
			
		% coming back to the center port after wrong outer poke
		else if (reward_available_at_center == 0 && wrong_outer_poke == 1 ) do
			trigger(18)
			wrong_outer_poke = 0
			decision_timeout = 0 % if the rat barely missed the reward window, then there's no lockout

		% timeout -- if the rat does not do decision the
		else if (reward_available_at_center == 0 && decision_timeout == 1 ) do 
			do in lockoutPeriod_timeout
				trigger(18)
			end
			decision_timeout = 0
			wrong_outer_poke = 0
		end	
	
	else if (taskstate == 3) do
		disp('TERMINATE EPOCH')
	
	end		
end;

callback portin[7] down
	lastWell=7 % well left, now last well
	disp('DOWN 7')
	pokein_center = 0

end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%



% outer arm CALLBACKS
% center well: 7
% outer wells: 15,9
% back well: 5
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% back -- this was initially 10 but changed to 5 (20240609-DS)
callback portin[5] up
	currWell = 5
	if currWell != lastWell do
		disp('UP 5')
	end
end;

% back -- this was initially 10 but changed to 5 (20240609-DS)
callback portin[5] down
	lastWell = 5
	disp('DOWN 5')
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% arm 2 -- this was initially 13 but changed to 15 (20240609-DS)
callback portin[15] up
	currWell = 15
	if currWell != lastWell do
		disp('UP 15')
		if (taskstate == 2 && target_location == 2 && reward_avail == 1 && reward_delivered == 0) do
			disp('REWARD ARM2')
		else if (taskstate == 2 && target_location == 1 && reward_avail == 1 && reward_delivered == 0) do
			disp('WRONG ARM2')		
		else if (taskstate == 2 && reward_avail == 0 ) do
			disp('WRONG OUTER VISIT')
		end
	end
end;

callback portin[15] down
	lastWell = 15
	disp('DOWN 15')
	if (taskstate == 2) do
		disp('OUTER ARMS DONE')
	end
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% arm 1
callback portin[9] up
	currWell = 9
	if currWell != lastWell do
		disp('UP 9')
		if (taskstate == 2 && target_location == 1 && reward_avail == 1 && reward_delivered == 0) do
			disp('REWARD ARM1')
		else if (taskstate == 2 && target_location == 2 && reward_avail == 1 && reward_delivered == 0) do
			disp('WRONG ARM1')
		else if (taskstate == 2 && reward_avail == 0 ) do
			disp('WRONG OUTER VISIT')
		end
	end
end;

callback portin[9] down
	lastWell = 9
	disp('DOWN 9')
	if (taskstate == 2) do
		disp('OUTER ARMS DONE')
	end
	
end;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

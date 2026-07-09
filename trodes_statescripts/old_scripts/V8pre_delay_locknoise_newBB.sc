% PROGRAM NAME: 	V8pre_goal_nowait
% AUTHOR: AKG
% DESCRIPTION: pretraining regime 	

% constants
int deliverPeriodBox= 150   	% how long to deliver the reward at home/rip/wait
int deliverPeriodOuter= 450   	% how long to deliver the reward at outer wells
int lockoutPeriod= 25000 	% length of lockout, 10sec
int proxTime = 200 		% amount of time allowed to be away from nose poke
% variables
int rewardWell = 0
int currWell = 0
int lastWell = 0
int dio = 0
int homeCount = 0		% number of times rewarded at home
int waitCount = 0		% number of times rewarded at wait well
int ripCount = 0		%number of times rewarded at rip well
int locktype1 = 0		% number of times locked out by choosing wrong rip/wait well
int locktype2 = 0 		% number of times lockout out by making other order error
int locktype3 = 0 		% number of times lockout from not holding in rip or wait
int trialtype = 0
int goalCount = 0		% cumulative num outer visits
int goalTotal = 0
int otherCount = 0
int waittime = 0
int proximity = 0
int waslock = 0

int outerreps = 0

% initialize
portout[1] = 0
portout[2] = 0
portout[3] = 0
portout[4] = 0
portout[5] = 0
portout[6] = 0
portout[7] = 0
portout[8] = 0
portout[10] = 1
portout[11] = 0
portout[12] = 0
;

% function to deliver reward to box wells
function 1
	portout[rewardWell]=1 % reward
	do in deliverPeriodBox 
		portout[rewardWell]=0 % reset reward
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

%display status
function 5
	disp(homeCount)
	disp(waitCount)
	disp(ripCount)
	disp(locktype1)
	disp(locktype2)
	disp(locktype3)
	disp(goalCount)
	disp(goalTotal)
	disp(otherCount)
end;

function 6 % end lockout and reactivate home
	disp('WHITENOISE')	
	do in lockoutPeriod
		disp('LOCKEND')
	end
end;


% CALLBACKS -- EVENT-DRIVEN TRIGGERS
callback portin[10] up
	if trialtype != 4 do 
		currWell = 10
		disp('UP 10')
		waslock = 0
		disp(waslock)
	end
end;

callback portin[10] down
	if trialtype != 4 do
		lastWell = 10
		disp('DOWN 10')
	end
end;

callback portin[11] up % Rip well
	currWell = 11 % well currently active
	disp('UP 11')

	if trialtype == 1 do
		if lastWell != currWell do
			proximity = 1
			do in waittime
				if proximity > 0 do
					proximity = 0
					trialtype = 3
					disp('BEEP1')
					disp('BEEP2')
				end
			end
		else do 
			proximity=proximity+1
		end
	else do		
		if (trialtype != 4 &&  currWell != lastWell && waslock != 1) do 
			if trialtype == 2 do
				disp('LOCKOUT 1')
			else do
				disp('LOCKOUT 2')
			end
		end
	end

end;

callback portin[11] down
	lastWell=11 % well left, now last well
	disp('DOWN 11')
	if proximity>0 do
		do in proxTime	
			proximity=proximity-1	
			if (proximity <1 && trialtype <3) do
				disp('LOCKOUT 3')
			end	
		end
	end
end;

callback portin[12] up % wait well
	currWell = 12 % well currently active
	disp('UP 12')
	if trialtype == 2 do
		if lastWell != currWell do
			proximity = 1
			do in waittime
				if proximity > 0 do
					proximity = 0
					trialtype = 3
					disp('CLICK1')
					disp('CLICK2')
				end
			end
		else do 
			proximity=proximity+1			
		end
	else do
		if (trialtype != 4 && currWell != lastWell && waslock != 1) do
			if trialtype == 1 do
				disp('LOCKOUT 1')
			else do
				disp('LOCKOUT 2')
			end			
		end
	end
end;

callback portin[12] down
	lastWell=12 % well left, now last well
	disp('DOWN 12')
	if proximity>0 do
		do in proxTime	
			proximity=proximity-1	
			if (proximity <1 && trialtype <3) do
				disp('LOCKOUT 3')
			end	
		end
	end
end;

callback portin[1] up
	currWell = 1
	if currWell != lastWell do
		disp('UP 1')
	end
end;

callback portin[1] down
	lastWell = 1
	disp('DOWN 1')
end;

callback portin[2] up
	currWell = 2
	if currWell != lastWell do
		disp('UP 2')
	end
end;

callback portin[2] down
	lastWell = 2
	disp('DOWN 2')
end;

callback portin[3] up
	currWell = 3
	if currWell != lastWell do
		disp('UP 3')
	end
end;

callback portin[3] down
	lastWell = 3
	disp('DOWN 3')
end;

callback portin[4] up
	currWell = 4
	if currWell != lastWell do
		disp('UP 4')
	end
end;

callback portin[4] down
	lastWell = 4

	disp('DOWN 4')
end;

callback portin[5] up
	currWell = 5
	if currWell != lastWell do
		disp('UP 5')
	end
end;

callback portin[5] down
	lastWell = 5
	disp('DOWN 5')
end;

callback portin[6] up
	currWell = 6
	if currWell != lastWell do
		disp('UP 6')
	end
end;

callback portin[6] down
	lastWell = 6
	disp('DOWN 6')
end;

callback portin[7] up
	currWell = 7
	if currWell != lastWell do
		disp('UP 7')
	end
end;

callback portin[7] down
	lastWell = 7
	disp('DOWN 7')
end;

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

% PROGRAM NAME: 	Fork track center then handle alternation with two second delay. Left side of Haight. Nov 2020.
% AUTHOR: 		JAG

%VARIABLES
int deliverPeriod=300  % reward duration
int delayPeriod=2000 % ms. Delay from poke to reward
int centerWell=17
int rightWell=18
int leftWell=19
int handleWell=20
int handleWellPump=handleWell+8
int rightWellPump=rightWell+8
int leftWellPump=leftWell+8
int centerWellPump=9
int lastSideWell=0
int lastWell=0
int currWell=0
int rewardWell=0
int counter_centerReward=0
int counter_handleReward=0
int counter_outerReward=0
int counter_consecutiveReward=0 % count consecutive reward within a contingency
int ch_zeroOne=0 % 0 for center alt, 1 for handle alt

%FUNCTIONS
function 1 % delivers reward
	do in delayPeriod % institutes delay
		portout[rewardWell] = 1 % give reward
		do in deliverPeriod % do after waiting deliverPeriod ms
			portout[rewardWell] = 0 % stop reward
		end
	end
end

function 2 % deal with first poke ever that happens to occur at center well
	if lastWell==0 do
		rewardWell=currWell+8
		disp('rewarding_center')
		trigger(1)
	end
end

function 3 % deal with first poke at a side well
	if (lastWell==centerWell || lastWell==0) && (lastSideWell==0 && (currWell==rightWell || currWell==leftWell)) do
		rewardWell=currWell+8
		disp('rewarding_side')
		trigger(1)
	end
end

function 4 % restart consecutive reward counter
	counter_consecutiveReward=0
	disp(counter_consecutiveReward)
end

function 5 % update consecutive reward counter, switch contingency if reaches thresh
	counter_consecutiveReward=counter_consecutiveReward+1
	disp(counter_consecutiveReward)
	if counter_consecutiveReward==8 do
		disp(ch_zeroOne)
		disp('switching contingency')
		if ch_zeroOne==0 do
			ch_zeroOne=1
		else do
			ch_zeroOne=0
		end
		disp(ch_zeroOne)
		trigger(4)
	end
end

% CALLBACKS
callback portin[17] up % poke at center
	disp('center_poke')
	currWell=centerWell
	trigger(2) % reward if first poke ever
	if ch_zeroOne == 0 do % if center alt
		if lastWell==rightWell || lastWell==leftWell do % if previously visited left or right
			disp('rewarding_center')
			rewardWell=centerWellPump
			trigger(1)
			counter_centerReward=counter_centerReward+1
			disp(counter_centerReward)
			trigger(5)
		end
	else do 
		trigger(4)
	end
end

callback portin[17] down % set lastWell to center
	lastWell=centerWell
end

callback portin[20] up % poke at handle
	disp('handle_poke')
	currWell=handleWell
	if ch_zeroOne == 1 do % if handle alt
		if lastWell==rightWell || lastWell==leftWell do % if previously visited left or right
			disp('rewarding_handle')
			rewardWell=handleWellPump
			trigger(1)
			counter_handleReward=counter_handleReward+1
			disp(counter_handleReward)
			trigger(5)
		end
	else do
		trigger(4)
	end
end

callback portin[20] down
	lastWell=handleWell % set lastWell to handle
end

callback portin[18] up
	disp('right_poke')
	currWell=rightWell
	trigger(3) % reward if first poke at side arm
	if (ch_zeroOne==1 && lastWell==handleWell) || (ch_zeroOne==0 && lastWell==centerWell) do % if previously visited home
		if lastSideWell==leftWell do % if previous sidewell was left
			disp('rewarding_right')
			rewardWell=rightWellPump
			trigger(1)
			counter_outerReward=counter_outerReward+1
			disp(counter_outerReward)
			trigger(5)
		end
	end
	if (ch_zeroOne==0 && lastWell==centerWell && lastSideWell==rightWell) || (ch_zeroOne==1 && lastWell==handleWell && lastSideWell==rightWell) || (lastWell==leftWell) do % if incorrect outer or inner
		trigger(4)
	end
end

callback portin[18] down
	lastWell=rightWell
	lastSideWell=rightWell						
end

callback portin[19] up
	disp('left_poke')
	currWell=leftWell
	trigger(3) % reward if first poke at side arm	
	if (ch_zeroOne==1 && lastWell==handleWell) || (ch_zeroOne==0 && lastWell==centerWell) do % if previously visited home
		if lastSideWell==rightWell do % if previous sidewell was right
			disp('rewarding_left')
			rewardWell=leftWellPump
			trigger(1) % trigger reward
			counter_outerReward=counter_outerReward+1
			disp(counter_outerReward)
			trigger(5)
		end
	end
	if (ch_zeroOne==0 && lastWell==centerWell && lastSideWell==leftWell) || (ch_zeroOne==1 && lastWell==handleWell && lastSideWell==leftWell) || (lastWell==rightWell) do % if incorrect outer or inner
		trigger(4)
	end
end

callback portin[19] down
	lastWell=leftWell
	lastSideWell=leftWell
end;

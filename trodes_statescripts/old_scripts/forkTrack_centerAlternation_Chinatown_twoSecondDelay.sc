% PROGRAM NAME: 	Fork track center alternation with two second delay. Left side of Haight. Oct 2020.
% AUTHOR: 		JAG

%VARIABLES
int deliverPeriod=300  % reward duration
int delayPeriod=2000 % ms. Delay from poke to reward
int centerWell=17
int rightWell=18
int leftWell=2
int handleWell=3
int centerWellPump=9
int rightWellPump=rightWell+8
int leftWellPump=leftWell+10
int lastSideWell=0
int lastWell=0
int currWell=0
int rewardWell=0
int counter_centerReward=0
int counter_outerReward=0
int counter_handlePoke=0

%FUNCTIONS
function 1 % delivers reward
	do in delayPeriod % institutes delay
		portout[rewardWell] = 1 % give reward
		do in deliverPeriod % do after waiting deliverPeriod ms
			portout[rewardWell] = 0 % stop reward
		end
	end
end;

function 2 % deal with first poke ever that happens to occur at center well
	if lastWell==0 do
		rewardWell=centerWellPump
		disp('rewarding_center')
		trigger(1)
	end
end;

function 3 % deal with first poke at a side well
	if (lastWell==centerWell || lastWell==0) && (lastSideWell==0 && (currWell==rightWell || currWell==leftWell)) do
		rewardWell=currWell+8
		disp('rewarding_side')
		trigger(1)
	end
end;

% CALLBACKS
callback portin[3] up % poke at handle
	disp('handle_poke')
	currWell=handleWell
	counter_handlePoke=counter_handlePoke+1
	disp(counter_handlePoke)
end

callback portin[3] down % set lastWell to handle
	lastWell=handleWell
end

callback portin[17] up % poke at center
	disp('center_poke')
	currWell=centerWell
	trigger(2) % reward if first poke ever	
	if lastWell==rightWell || lastWell==leftWell do % if previously visited left or right
		disp('rewarding_center')
		rewardWell=centerWellPump
		trigger(1)
		counter_centerReward=counter_centerReward+1
		disp(counter_centerReward)
	end
end

callback portin[17] down
	lastWell=centerWell % set lastWell to center
end

callback portin[18] up
	disp('right_poke')
	currWell=rightWell
	trigger(3) % reward if first poke at side arm
	if lastWell==centerWell do % if previously visited center
		if lastSideWell==leftWell do % if previous sidewell was left
			disp('rewarding_right')
			rewardWell=rightWellPump
			trigger(1)
			counter_outerReward=counter_outerReward+1
			disp(counter_outerReward)
		end
	end
end

callback portin[18] down
	lastWell=rightWell
	lastSideWell=rightWell						
end

callback portin[2] up
	disp('left_poke')
	currWell=leftWell
	trigger(3) % reward if first poke at side arm	
	if lastWell==centerWell do % if previously visited center				
		if lastSideWell==rightWell do % if previous sidewell was right
			disp('rewarding_left')
			rewardWell=leftWellPump
			trigger(1) % trigger reward
			counter_outerReward=counter_outerReward+1
			disp(counter_outerReward)
		end
	end
end

callback portin[2] down
	lastWell=leftWell
	lastSideWell=leftWell
end;

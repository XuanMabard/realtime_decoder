% PROGRAM NAME: 	reward all wells in Haight
% AUTHOR: 		JAG

%VARIABLES
int deliverPeriod=300  % reward duration
int delayPeriod=0 % ms. Delay from poke to reward
int rewardWell=0

%FUNCTIONS
function 1 % delivers reward
	do in delayPeriod % institutes delay
		portout[rewardWell] = 1 % give reward
		do in deliverPeriod % do after waiting deliverPeriod ms
			portout[rewardWell] = 0 % stop reward
		end
	end
end;

% CALLBACKS


 % Center
callback portin[17] up		
	rewardWell = 9
	trigger(1)
end;

% Left

callback portin[2] up
	rewardWell = 12
	trigger(1)
end;

% Right

callback portin[18] up
	rewardWell = 26
	trigger(1)
end;

% Handle

callback portin[3] up
	rewardWell = 11
	trigger(1)
end;

% Linear_1
callback portin[29] up
	rewardWell = 19
	trigger(1)
end;

% Linear_2
callback portin[21] up
	rewardWell = 28
	trigger(1)
end;


% PROGRAM NAME: multi linear track
% DESCRIPTION:	lights and rewards alternate between 2 wells for 4 different tracks

int deliverPeriod= 400   	% how long to deliver the reward
int rewardPump1 = 0
int rewardPump2 = 0
int rewardPump3 = 0
int rewardPump4 = 0
int rewardPump5 = 0
int rewardPump6 = 0
int rewardPump7 = 0
int rewardPump8 = 0
;

% functions to deliver rewards to each pump
function 1
	portout[rewardPump1]=1 		% turn pump on
	do in deliverPeriod 
		portout[rewardPump1]=0 	% turn pump off
	end	
end;
function 2
	portout[rewardPump2]=1 		% turn pump on
	do in deliverPeriod 
		portout[rewardPump2]=0 	% turn pump off
	end	
end;
function 3
	portout[rewardPump3]=1 		% turn pump on
	do in deliverPeriod 
		portout[rewardPump3]=0 	% turn pump off
	end	
end;
function 4
	portout[rewardPump4]=1 		% turn pump on
	do in deliverPeriod 
		portout[rewardPump4]=0 	% turn pump off
	end	
end;
function 5
	portout[rewardPump5]=1 		% turn pump on
	do in deliverPeriod 
		portout[rewardPump5]=0 	% turn pump off
	end	
end;
function 6
	portout[rewardPump6]=1 		% turn pump on
	do in deliverPeriod 
		portout[rewardPump6]=0 	% turn pump off
	end	
end;
function 7
	portout[rewardPump7]=1 		% turn pump on
	do in deliverPeriod 
		portout[rewardPump7]=0 	% turn pump off
	end	
end;
function 8
	portout[rewardPump8]=1 		% turn pump on
	do in deliverPeriod 
		portout[rewardPump8]=0 	% turn pump off
	end	
end;


% CALLBACKS -- EVENT-DRIVEN TRIGGERS
% Poke in callbacks
% --------------------
callback portin[1] up
	disp('UP 1')
end;

callback portin[2] up
	disp('UP 2')
end;

callback portin[3] up
	disp('UP 3')
end;

callback portin[4] up
	disp('UP 4')
end;

callback portin[5] up
	disp('UP 5')
end;


callback portin[6] up
	disp('UP 6')
end;

callback portin[7] up
	disp('UP 7')
end;

callback portin[8] up
	disp('UP 8')
end;

callback portin[9] up
	disp('UP 9')
end;

callback portin[10] up
	disp('UP 10')
end;

callback portin[11] up
	disp('UP 11')
end;

callback portin[12] up
	disp('UP 12')
end;

callback portin[13] up
	disp('UP 13')
end;

callback portin[14] up
	disp('UP 14')
end;

callback portin[15] up
	disp('UP 15')
end;

%callback portin[16] up
%	disp('UP 16')
%end;

callback portin[17] up
	disp('UP 17')
end;

callback portin[18] up
	disp('UP 18')
end;

callback portin[19] up
	disp('UP 19')
end;

callback portin[20] up
	disp('UP 20')
end;

callback portin[21] up
	disp('UP 21')
end;

callback portin[22] up
	disp('UP 22')
end;

callback portin[23] up
	disp('UP 23')
end;

callback portin[24] up
	disp('UP 24')
end;

callback portin[25] up
	disp('UP 25')
end;

callback portin[26] up
	disp('UP 26')
end;

callback portin[27] up
	disp('UP 27')
end;

callback portin[28] up
	disp('UP 28')
end;

callback portin[29] up
	disp('UP 29')
end;

callback portin[30] up
	disp('UP 30')
end;

callback portin[31] up
	disp('UP 31')
end;

callback portin[32] up
	disp('UP 32')
end;

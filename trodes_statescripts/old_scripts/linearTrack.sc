% PROGRAM NAME: Linear track without lights
% AUTHOR: JAG
% DESCRIPTION: alternate between ends, active trial lights up
	
int deliverPeriod=300 % ms. How long to deliver the reward
int rewardWell=0
int currWell=0
int lastWell=0
int rewCount=0
int well1_IR_ID=23  %cable marked 7
int well2_IR_ID=24  %cable marked 4 
int well1_reward_ID=26  %right pump
int well2_reward_ID=12  %left pump

% Turn off lights
portout[well1_IR_ID]=0 
portout[well2_IR_ID]=0

function 1
	portout[rewardWell]=1 % reward
	do in deliverPeriod 
		portout[rewardWell]=0 % reset reward
	end
	rewCount = rewCount+1
	disp(rewCount)	
end;
					
callback portin[23] up % one side
	currWell = well1_IR_ID
	if lastWell != currWell do
		rewardWell = well1_reward_ID
		trigger(1)
		lastWell = currWell
	end
end;

callback portin[24] up % other side	
	currWell = well2_IR_ID
	if lastWell != currWell do
		rewardWell = well2_reward_ID
		trigger(1)
		lastWell = currWell
	end
end;


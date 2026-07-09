% PROGRAM NAME: Linear track without lights
% AUTHOR: JAG
% DESCRIPTION: alternate between ends, active trial lights up
	
int deliverPeriod=300 % ms. How long to deliver the reward
int delayPeriod = 1000 % ms. Delay period after nose poke and before reward given
int rewardWell=0
int currWell=0
int lastWell=0
int rewCount=0
int well1_IR_ID=23  %cable marked 7
int well2_IR_ID=24  %cable marked 4 
int well1_reward_ID=26  %right pump
int well2_reward_ID=12  %left pump

function 1
	do in delayPeriod % institutes delay
		portout[rewardWell]=1 % reward
		do in deliverPeriod 
			portout[rewardWell]=0 % reset reward
		end
		rewCount = rewCount+1
		disp(rewCount)
	end
end;
					
callback portin[23] up % one side
	currWell = well1_IR_ID
	if lastWell != currWell do
		rewardWell = well1_reward_ID
		trigger(1)
		lastWell = currWell
	end
end;

callback portin[24] up   % right	
	currWell = well2_IR_ID
	if lastWell != currWell do
		rewardWell = well2_reward_ID
		trigger(1)
		lastWell = currWell
	end
end;


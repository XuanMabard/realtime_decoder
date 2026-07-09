% PROGRAM NAME: 	Load milk
% AUTHOR: 		AKG 
% DESCRIPTION:	

int deliverPeriod= 200   	% how long to deliver the reward
int rewardWell=0;

portout[10]=0
portout[11]=0
portout[12]=0

portout[1]=0
portout[2]=0
portout[3]=0
portout[4]=0
portout[5]=0
portout[6]=0
portout[7]=0
portout[8]=0
portout[17]=0
portout[18]=0
portout[19]=0
portout[20]=0
portout[21]=0
portout[22]=0
portout[23]=0
portout[24]=0
portout[25]=0;




function 1
	portout[rewardWell]=1 % reward
	do in deliverPeriod 
		portout[rewardWell]=0 % reset reward
	end	
end;

callback portin[1] up   % home	
	rewardWell = 17
	trigger(1)
end;
					
callback portin[2] up   % home	
	rewardWell = 18
	trigger(1)
end;
callback portin[3] up   % wall	
	rewardWell = 19
	trigger(1)
end;

callback portin[4] up   % arm4	
	rewardWell = 20
	trigger(1)
end;

callback portin[5] up   % arm5	
	rewardWell = 21
	trigger(1)
end;

callback portin[6] up   % arm6	
	rewardWell =22
	trigger(1)
end;

callback portin[7] up   % home	
	rewardWell = 23
	trigger(1)
end;

callback portin[8] up   % inner
	rewardWell = 24
	trigger(1)
end;

callback portin[10] up   % arm1	
	rewardWell = 25
	trigger(1)
end;

callback portin[11] up   % arm2
	rewardWell = 26
	trigger(1)
end;

callback portin[12] up   % arm3
	rewardWell = 27
	trigger(1)
end;

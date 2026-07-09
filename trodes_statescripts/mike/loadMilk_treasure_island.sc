% PROGRAM NAME: 	Load milk
% AUTHOR: 		AKG 
% DESCRIPTION:	

int deliverPeriod= 400   	% how long to deliver the reward
int lightupPeriod = 500 % reward port lights up

int rewardWell=0;
int rewardPort=0;

portout[1]=0
portout[2]=0

portout[5]=0
portout[6]=0

portout[7]=0
portout[8]=0
portout[9]=0
portout[10]=0
portout[11]=0
portout[12]=0
portout[13]=0
portout[14]=0
portout[15]=0;




function 1
	portout[rewardWell]=1 % reward
	do in deliverPeriod 
		portout[rewardWell]=0 % reset reward
	end	
end;

function 2
	portout[rewardPort]=1 % reward
	do in lightupPeriod 
		portout[rewardPort]=0 % reset reward
	end	
end;


callback portin[9] up   % arm1	
	rewardWell = 12
	rewardPort = 9
	trigger(2)
	trigger(1)
end;

callback portin[15] up   % arm2	
	rewardWell = 11
	rewardPort = 15
	trigger(2)
	trigger(1)
end;

callback portin[7] up   % center	
	rewardWell = 14
	rewardPort = 7
	trigger(2)
	trigger(1)
end;

callback portin[5] up   % home	
	rewardWell = 8
	rewardPort = 5
	trigger(2)
	trigger(1)
end;

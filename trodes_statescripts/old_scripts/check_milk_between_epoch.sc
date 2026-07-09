% PROGRAM NAME: 	Load milk
% AUTHOR: 		AKG 
% DESCRIPTION:	

int deliverPeriod= 800   	% how long to deliver the reward
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

function 3

	rewardWell = 12 % arm1
	rewardPort = 9
	trigger(2)
	trigger(1)

	rewardWell = 11  % arm2	
	rewardPort = 15
	trigger(2)
	trigger(1)

	rewardWell = 14 % center	
	rewardPort = 7
	trigger(2)
	trigger(1)

	rewardWell = 8 % home	
	rewardPort = 5
	trigger(2)
	trigger(1)
end;

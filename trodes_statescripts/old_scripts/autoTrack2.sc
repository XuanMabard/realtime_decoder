% PROGRAM NAME: 	autoTrack1
% DESCRIPTION:	state script file for automatic track

int deliverPeriod= 300   	% how long to deliver the reward 300
int rewardWell=0
int dio=0
int transition=0
int stop=0
int animal=0
int session=0
int homeRewards=0
int outerRewards=0
int totRewards=0
int expRewards=0
int timeElapsed=0
int arms=0
int timeOut=0
int timeCheck=clock()
int holdTime=0
int count=0
int doorCloseTime=300000
int frusSes=1
;

% function to deliver reward
function 1
	if timeCheck==holdTime do
		portout[8]=0
		portout[9]=0
		portout[10]=0
		portout[11]=0
		portout[17]=0
		portout[18]=0
		portout[19]=0
		portout[20]=0
		portout[21]=0
		portout[22]=0
		portout[23]=0
		portout[24]=0
		portout[25]=0
		portout[26]=0
		portout[27]=0
		portout[28]=0
		portout[29]=0
		portout[30]=0
		portout[31]=0
		portout[32]=0
		disp('streaming disconnected')
	else do
		portout[rewardWell]=1 % reward
		do in deliverPeriod 
			portout[rewardWell]=0 % reset reward
		end
	end
end;

% function to turn on output
function 2
	if transition==0 do	
		portout[dio]=1
	end
	if (transition==1 && stop==0) do
		portout[dio]=1
	end
end;

% function to turn off output
function 3	
	portout[dio]=0	
end;

%display status
function 4
	disp(session)
	disp(animal)
	disp(homeRewards)
	disp(outerRewards)
end;

function 5
	disp(transition)
	disp(animal)
end;

% info function
function 6
	disp(arms)
end;

function 7
	disp(session)
	disp(animal)
	disp(totRewards)
end;

function 8
	disp(session)
	disp(animal)
	disp(expRewards)
end;

function 9
        do in doorCloseTime 
                portout[5]=1 % reset reward
                disp(frusSes)
        end
end;

% CALLBACKS -- EVENT-DRIVEN TRIGGERS

callback portin[1] up
	disp('UP 1')
end;

callback portin[3] up
	disp('UP 3')
end;

callback portin[5] up
	disp('UP 5')
end;

callback portin[7] up
	disp('UP 7')
end;

callback portin[9] up
	disp('UP 9')
end;

callback portin[11] up
	disp('UP 11')
end;

callback portin[13] up
	disp('UP 13')
end;
callback portin[14] up
	disp('UP 14')
end;

callback portin[17] up
	disp('UP 17')
end;
callback portin[18] up
	disp('UP 18')
end;

callback portin[20] up
	disp('UP 20')
end;

callback portin[22] up
	disp('UP 22')
end;
callback portin[1] down
	disp('DOWN 1')
end;

callback portin[3] down
	disp('DOWN 3')
end;

callback portin[5] down
	disp('DOWN 5')
end;

callback portin[7] down
	disp('DOWN 7')
end;

callback portin[9] down
	disp('DOWN 9')
end;

callback portin[11] down
	disp('DOWN 11')
end;

callback portin[13] down
	disp('DOWN 13')
end;
callback portin[14] down
	disp('DOWN 14')
end;

callback portin[17] down
	disp('DOWN 17')
end;
callback portin[18] down
	disp('DOWN 18')
end;

callback portin[20] down
	disp('DOWN 20')
end;

callback portin[22] down
	disp('DOWN 22')
end;
callback portin[23] up 
	disp('UP 23')
end;

callback portin[23] down
	disp('DOWN 23')
end;

callback portin[24] up
	disp('UP 24')
end;

callback portin[24] down
	disp('DOWN 24')
end;

callback portin[25] up
	disp('UP 25')
end;

callback portin[25] down
	disp('DOWN 25')
end;

callback portin[26] up
	disp('UP 26')
end;

callback portin[26] down
	disp('DOWN 26')
end;

callback portin[27] up
	disp('UP 27')
end;

callback portin[27] down
	disp('DOWN 27')
end;

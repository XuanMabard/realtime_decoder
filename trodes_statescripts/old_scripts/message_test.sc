% PROGRAM NAME: 	My simple script
% AUTHOR: 		MEC, AKG 
% DESCRIPTION:	

% set a variable light_time at 300 msec
int light_time = 300;

portout[6]=0;

% turn on light in port 1, then turn off after 100 msec

function 1
	portout[6]=1 % turns on light
	do in light_time
		portout[6]=0
	end
end;


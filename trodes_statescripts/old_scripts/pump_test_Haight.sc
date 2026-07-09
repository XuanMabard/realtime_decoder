% PROGRAM NAME:     Test Pump
% AUTHOR:       Shijie
% DESCRIPTION:  

int deliverPeriod= 15000    % how long to deliver the reward, 15 seconds

int rewardWell=29;

% load milk

function 1

    portout[rewardWell]=1 % reward

    do in deliverPeriod 

        portout[rewardWell]=0 % reset reward

    end 

end;

% in command line type trigger(1);

% there shall be 5ml milk out/syringe shall move 5ml.

%% Pairwise TLE differencing ---------------------------------------------%
%
% Compute the covariance matrix of a TLE at its release epoch using the TLE
% itself as observed observable and propagated TLEs from previous epochs as
% as computed observables.
%
% Input:  pathtle - [string] path to the TLE .txt file. This file stores the TLEs
%                            subject of investigation in 3le format
%
%         patheop - [string] path to the most recent EOP release
%
%         nut80   - [double] nut80.dat sgp4 file
%
% Output  infosat - 6 x N cell where N is the number of available TLEs
%                   row 1 - TLEs satrec @ release epoch
%                   row 2 - Rotation matrix from ECI to RIC of each TLE
%                           @ release epoch
%                   row 3 - TLEs reci veci @ release epoch
%                   row 4 - Matrix with columns made of reci veci of
%                           propagated TLEs @ release epoch
%                   row 5 - Residuals
%                   row 6 - Covariance
%
% ------------------------------------------------------------------------%

%%

function infosat = tle_pairwise(pathtle, patheop, nut80)

% Get TLE data
tle     = sorttle(pathtle);
% Init infosat
infosat = cell(6,length(tle));

% For each TLE
for i=1:length(tle)
    % Get TLEs satrec @primary TLE epoch
    [~, ~, ~, infosat{1,i}] = twoline2rv(char(tle{i}(1)), char(tle{i}(2)), 'c', [], [], 84);
    % Compute state @primary TLEs epoch
    [~, rteme, vteme] = sgp4(infosat{1,i}, 0);
    epochtle = infosat{1,i}.jdsatepoch + infosat{1,i}.jdsatepochf;
    dateeop  = datetime(epochtle,'convertfrom','juliandate','Format','yyyy-MM-dd');
    t        = datevec(datetime(epochtle,'convertfrom','juliandate'));
    eop      = EOP_struct(patheop,string(dateeop));
    [~, ~, ttt]     = convtime(t(1), t(2), t(3), t(4), t(5), t(6), 0, eop.dut1, eop.dat);
    [reci, veci, ~] = teme2eci(rteme', vteme', 0, ttt, eop.ddpsi, eop.ddeps, nut80);
    % Rotation matrix from ECI to RIC
    M = rot_eci2rtc(reci,veci);
    infosat{2,i} = M;
    % Observed TLE
    infosat{3,i} = [reci; veci];
    % Propagate secondary TLEs to the primary
    if i>1
        for j=1:(i-1)
            epochtlestart = infosat{1,j}.jdsatepoch + infosat{1,j}.jdsatepochf;
            epochtle      = infosat{1,i}.jdsatepoch + infosat{1,i}.jdsatepochf;
            deltaT        = epochtle - epochtlestart;
            tsince        = deltaT*1440;
            [~, rteme, vteme] = sgp4(infosat{1,j}, tsince);
            dateeop           = datetime(epochtle,'convertfrom','juliandate','Format','yyyy-MM-dd');
            eop               = EOP_struct(patheop,string(dateeop));
            t                 = datevec(datetime(epochtle,'convertfrom','juliandate'));
            [~, ~, ttt]     = convtime(t(1), t(2), t(3), t(4), t(5), t(6), 0, eop.dut1, eop.dat);
            [reci, veci, ~] = teme2eci(rteme', vteme', 0, ttt, eop.ddpsi, eop.ddeps, nut80);
            mat(:,j)        = [reci; veci];
            % Residuals
            dX = mat(:,j) - infosat{3,i};
            % Transform in RIC
            dX(1:3) = infosat{2,i}*dX(1:3);
            dX(4:6) = infosat{2,i}*dX(4:6);
            dX(7)   = deltaT;
            % Save residuals
            infosat{5,i}(:,j) = dX;
        end
        % Computed observables
        infosat{4,i} = mat;
        if i>2
            % Mean of residuals
            tosum = infosat{5,i}(1:6,:);
            m = sum(tosum,2)/size(tosum,2);
            % Covariance
            P = zeros(6,6);
            for ii=1:size(tosum,2)
                b = (infosat{5,i}(1:6,ii) - m)*(infosat{5,i}(1:6,ii) - m)';
                P = P+b;
            end
            if size(tosum,2) > 1
                P = P ./ (size(tosum,2) - 1);   % unbiased
            else
                P = P ./ size(tosum,2);
            end
            infosat{6,i} = P;
        end
    end
end
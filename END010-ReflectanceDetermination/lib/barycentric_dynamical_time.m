%% Help ------------------------------------------------------------------%
% 
% Compute barycentric dynamical time                    
% 
% Input:  UTC      - [datetime 1x1] - input datetime in UTC
%
% Output: TDB      - [datetime 1x1] - Barycentric dynamical time
%         JD_TDB   - [double 1x1]   - Julian date of TDB
%         MJD_TDB  - [double 1x1]   - Modified julian date of TDB
% ------------------------------------------------------------------------%

function [TDB,JD_TDB,MJD_TDB] = barycentric_dynamical_time(UTC)

% Terrestrial Dynamical Time (TT or TDT)
TAI = UTC + seconds(37);
TDT = TAI + seconds(32.184);
% Julian centuries of TT since J2000
JD_TDT   = juliandate(TDT); 
JD_J2000 = 2451545;  % juliandate(2000,1,1,12,0,0)
T_TT = (JD_TDT - JD_J2000)/36525;

% Barycentric Dynamical Time (TT or TDT) (Vallado, eq. 3-53)
TDB = TDT + seconds(0.001657*sin(628.3076*T_TT + 6.2401) + ...
    0.000022*sin(575.3385*T_TT + 4.2970) + ...
    0.000014*sin(1256.6152*T_TT + 6.1969) + ...
    0.000005*sin(606.9777*T_TT + 4.0212) + ...
    0.000005*sin(52.9691*T_TT + 0.4444) + ...
    0.000002*sin(21.3299*T_TT + 5.5431) + ...
    0.000010*T_TT*sin(628.3076*T_TT + 4.2490));

% Julian date of TDB
JD_TDB = juliandate(TDB);

% Modified julian date of TDB
MJD_TDB = JD_TDB - 2400000.5;
end
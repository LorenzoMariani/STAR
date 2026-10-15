%  -----------------------------------------------------------------------------
%
%                            procedure twoline2rv
%
%  this function converts the two line element set character string data to
%    variables and initializes the sgp4 variables. several intermediate varaibles
%    and quantities are determined. note that the result is a structure so multiple
%    satellites can be processed simultaneously without having to reinitialize. the
%    verification mode is an important option that permits quick checks of any
%    changes to the underlying technical theory. this option works using a
%    modified tle file in which the start, stop, and delta time values are
%    included at the end of the second line of data. this only works with the
%    verification mode. the catalog mode simply propagates from -1440 to 1440 min
%    from epoch and is useful when performing entire catalog runs.
%
% Author:
%   Jeff Beck
%   beckja@alumni.lehigh.edu
%   1.0  aug  6, 2006 - update for paper dav
%   2.0  mar  8, 2007 - misc fixes and manual operation updates
%   2.01 may  9, 2007 - fix for correction to year of 57
%   2.02 oct  8, 2007 - fix for manual jdstart jdstop matlab formats
% original comments from Vallado C++ version:
%   author        : david vallado                  719-573-2600    1 mar 2001
%
%   inputs        :
%   longstr1      - TLE character string
%   longstr2      - TLE character string
%   typeinput     - type of manual input           mfe 'm', epoch 'e', dayofyr 'd'
%
%   outputs       :
%     satrec      - structure containing all the sgp4 satellite information
%
%   coupling      :
%     getgravconst
%     days2mdhms  - conversion of days to month, day, hour, minute, second
%     jday        - convert day month year hour minute second into julian date
%     sgp4init    - initialize the sgp4 variables
%
%   references    :
%     norad spacetrack report #3
%     vallado, crawford, hujsak, kelso  2006
%
% [startmfe, stopmfe, deltamin, satrec] = twoline2rv(longstr1, longstr2, ...
%          typerun, typeinput, opsmode, whichconst)
%  ----------------------------------------------------------------------------*/

function [startmfe, stopmfe, deltamin, satrec] = twoline2rv(longstr1, longstr2, ...
    typerun, ~, opsmode, whichconst)


deg2rad  =   pi / 180.0;         %  0.01745329251994330;  % [deg/rad]
xpdotp   =  1440.0 / (2.0*pi);   % 229.1831180523293;  % [rev/day]/[rad/min]

satrec.error = 0;

for j = 11:16
    if longstr1(j) == ' '
        longstr1(j) = '_';
    end
end

if longstr1(45) ~= ' '
    longstr1(44) = longstr1(45);
end
longstr1(45) = '.';

if longstr1(8) == ' '
    longstr1(8) = 'U';
end

if longstr1(10) == ' '
    longstr1(10) = '.';
end

for j = 46:50
    if longstr1(j) == ' '
        longstr1(j) = '0';
    end
end
if longstr1(52) == ' '
    longstr1(52) = '0';
end
if longstr1(54) ~= ' '
    longstr1(53) = longstr1(54);
end
longstr1(54) = '.';

longstr2(26) = '.';

for j = 27:33
    if longstr2(j) == ' '
        longstr2(j) = '0';
    end
end

if longstr1(63) == ' '
    longstr1(63) = '0';
end

if ((length(longstr1) < 68) || (longstr1(68) == ' '))
    longstr1(68) = '0';
end

% Parse first line
satrec.satnum = str2double(longstr1(3:7));
satrec.classification = longstr1(8);
satrec.intldesg = longstr1(10:17);
satrec.epochyr = str2double(longstr1(19:20));
satrec.epochdays = str2double(longstr1(21:32));
satrec.ndot = str2double(longstr1(34:43));
satrec.nddot = str2double(longstr1(44:50));
nexp = str2double(longstr1(51:52));
satrec.bstar = str2double(longstr1(53:59));
ibexp = str2double(longstr1(60:61));
satrec.elnum = str2double(longstr1(65:68));

% Parse second line
satrec.satnum = str2double(longstr2(3:7));
satrec.inclo = str2double(longstr2(8:16));
satrec.nodeo = str2double(longstr2(17:25));
satrec.ecco = str2double(longstr2(26:33));
satrec.argpo = str2double(longstr2(34:42));
satrec.mo = str2double(longstr2(43:51));
satrec.no_kozai = str2double(longstr2(52:63));
satrec.revnum = str2double(longstr2(64:68));

% Find no, ndot, nddot
satrec.no_kozai   = satrec.no_kozai / xpdotp;
satrec.nddot= satrec.nddot * 10.0^nexp;
satrec.bstar= satrec.bstar * 10.0^ibexp;

% Convert to sgp4 units ----
satrec.ndot = satrec.ndot  / (xpdotp*1440.0);          % [rad/min^2]
satrec.nddot= satrec.nddot / (xpdotp*1440.0*1440);     % [rad/min^3]

% Find standard orbital elements ----
satrec.inclo = satrec.inclo  * deg2rad;
satrec.nodeo = satrec.nodeo * deg2rad;
satrec.argpo = satrec.argpo  * deg2rad;
satrec.mo    = satrec.mo     *deg2rad;

if (satrec.epochyr < 57)
    year= satrec.epochyr + 2000;
else
    year= satrec.epochyr + 1900;
end

[mon,day,hr,minute,sec]                 = days2mdh ( year,satrec.epochdays );
[satrec.jdsatepoch, satrec.jdsatepochf] = jday( year,mon,day,hr,minute,sec );



% Perform complete catalog evaluation
if (typerun == 'c')
    startmfe =  -1440.0;
    stopmfe  =  1440.0;
    deltamin = 20.0;
end


% Initialize the orbit at sgp4epoch
[satrec] = sgp4init( whichconst, opsmode, satrec, satrec.jdsatepoch+satrec.jdsatepochf-2433281.5, satrec.bstar, ...
    satrec.ndot, satrec.nddot, satrec.ecco, satrec.argpo, satrec.inclo, satrec.mo, satrec.no_kozai, ...
    satrec.nodeo);


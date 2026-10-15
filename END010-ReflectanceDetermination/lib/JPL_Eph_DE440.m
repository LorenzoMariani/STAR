%% Help ----------------------------------------------------------------- %
% Computes the sun, moon, and nine major planets' equatorial position using 
% JPL Ephemerides
%
% Input:  Mjd_TDB - [double 1x1] - modified julian day in TDB
%         DE440   -              - planetary ephemeris coefficients
%
% Output: r_Sun   - [double 1x3] - Sun position in ECI in km
% ----------------------------------------------------------------------- %
function [r_Sun, r_Moon] = JPL_Eph_DE440(Mjd_TDB,DE440)

JD = Mjd_TDB + 2400000.5;
i = find(DE440(:,1)<=JD & JD<=DE440(:,2),1,'first'); 
PCtemp = DE440(i,:);

t1 = PCtemp(1)-2400000.5; % MJD at start of interval
dt = Mjd_TDB - t1;

temp = (231:13:270);

Cx_EarthMoon = PCtemp(temp(1):temp(2)-1);
Cy_EarthMoon = PCtemp(temp(2):temp(3)-1);
Cz_EarthMoon = PCtemp(temp(3):temp(4)-1);
temp = temp+39;
Cx = PCtemp(temp(1):temp(2)-1);
Cy = PCtemp(temp(2):temp(3) -1);
Cz = PCtemp(temp(3):temp(4)-1);
Cx_EarthMoon = [Cx_EarthMoon,Cx];
Cy_EarthMoon = [Cy_EarthMoon,Cy];
Cz_EarthMoon = [Cz_EarthMoon,Cz];    
if (0<=dt && dt<=16)
    j=0;
    Mjd0 = t1;
elseif(16<dt && dt<=32)
    j=1;
    Mjd0 = t1+16*j;
end
r_EarthMoon = 1e3*Cheb3D(Mjd_TDB, 13, Mjd0, Mjd0+16, Cx_EarthMoon(13*j+1:13*j+13),...
                     Cy_EarthMoon(13*j+1:13*j+13), Cz_EarthMoon(13*j+1:13*j+13))';

temp = (441:13:480);

Cx_Moon = PCtemp(temp(1):temp(2)-1);
Cy_Moon = PCtemp(temp(2):temp(3)-1);
Cz_Moon = PCtemp(temp(3):temp(4)-1);
for i=1:7
    temp = temp+39;
    Cx = PCtemp(temp(1):temp(2)-1);
    Cy = PCtemp(temp(2):temp(3)-1);
    Cz = PCtemp(temp(3):temp(4)-1);   
    Cx_Moon = [Cx_Moon,Cx];
    Cy_Moon = [Cy_Moon,Cy];
    Cz_Moon = [Cz_Moon,Cz];    
end
if (0<=dt && dt<=4)
    j=0;
    Mjd0 = t1;
elseif(4<dt && dt<=8)
    j=1;
    Mjd0 = t1+4*j;
elseif(8<dt && dt<=12)
    j=2;
    Mjd0 = t1+4*j;
elseif(12<dt && dt<=16)
    j=3;
    Mjd0 = t1+4*j;
elseif(16<dt && dt<=20)
    j=4;%   r_Mars,r_Jupiter,r_Saturn,r_Uranus,r_Neptune,r_Pluto,r_Moon,

    Mjd0 = t1+4*j;
elseif(20<dt && dt<=24)
    j=5;
    Mjd0 = t1+4*j;
elseif(24<dt && dt<=28)
    j=6;
    Mjd0 = t1+4*j;
elseif(28<dt && dt<=32)
    j=7;
    Mjd0 = t1+4*j;
end
r_Moon = 1e3*Cheb3D(Mjd_TDB, 13, Mjd0, Mjd0+4, Cx_Moon(13*j+1:13*j+13),...
                    Cy_Moon(13*j+1:13*j+13), Cz_Moon(13*j+1:13*j+13))';

temp = (753:11:786);

Cx_Sun = PCtemp(temp(1):temp(2)-1);
Cy_Sun = PCtemp(temp(2):temp(3)-1);
Cz_Sun = PCtemp(temp(3):temp(4)-1);
temp = temp+33;
Cx = PCtemp(temp(1):temp(2)-1);
Cy = PCtemp(temp(2):temp(3)-1);
Cz = PCtemp(temp(3):temp(4)-1);   
Cx_Sun = [Cx_Sun,Cx];
Cy_Sun = [Cy_Sun,Cy];
Cz_Sun = [Cz_Sun,Cz];
if (0<=dt && dt<=16)
    j=0;
    Mjd0 = t1;
elseif(16<dt && dt<=32)
    j=1;
    Mjd0 = t1+16*j;
end
r_Sun = 1e3*Cheb3D(Mjd_TDB, 11, Mjd0, Mjd0+16, Cx_Sun(11*j+1:11*j+11),...
                   Cy_Sun(11*j+1:11*j+11), Cz_Sun(11*j+1:11*j+11))';

EMRAT = 81.3005682214972154; % DE440
EMRAT1 = 1/(1+EMRAT);
r_Earth = r_EarthMoon-EMRAT1*r_Moon;
r_Sun = -r_Earth+r_Sun;
r_Moon = r_Moon*1e-3;
r_Sun  = r_Sun*1e-3;

end

%% Help ----------------------------------------------------------------- %
%
% Chebyshev approximation of 3-dimensional vectors
%
% 
% Input:    t       - [double 1x1] - Modified Julian Date in TDB
%           N       - [double 1x1] - Number of coefficients
%           Ta      - [double 1x1] - Begin interval in MJD TDB
%           Tb      - [double 1x1] - End interval   in MJD TDB
%           Cx      - [double 1x1] - Coefficients of Chebyshev polyomial (x-coordinate)
%           Cy      - [double 1x1] - Coefficients of Chebyshev polyomial (y-coordinate)
%           Cz      - [double 1x1] - Coefficients of Chebyshev polyomial (z-coordinate)
%
% Output:   ChebApp - [double 1x1] - Chebyshev approximation at query point
%
% ----------------------------------------------------------------------- %
function [ChebApp] = Cheb3D (t, N, Ta, Tb, Cx, Cy, Cz)

% Check validity
if ( (t<Ta) || (Tb<t) )
    error( 'ERROR: Time out of range in Cheb3D::Value\n' );
    exit(1);
end

% Clenshaw algorithm
tau = (2*t-Ta-Tb)/(Tb-Ta);  

f1 = zeros(1,3);
f2 = zeros(1,3);

for i=N:-1:2
    old_f1 = f1;
    f1 = 2*tau*f1-f2+[Cx(i),Cy(i),Cz(i)];
    f2 = old_f1;
end

ChebApp = tau*f1-f2+[Cx(1),Cy(1),Cz(1)];
end
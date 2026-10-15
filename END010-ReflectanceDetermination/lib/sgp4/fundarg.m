%
% ----------------------------------------------------------------------------
%
%                           function fundarg
%
%  this function calulates the delauany variables and planetary values for
%  several theories.
%
%  author        : david vallado                  719-573-2600   16 jul 2004
%
%  revisions
%    vallado     - consolidate with iau 2000                     14 feb 2005
%
%  inputs          description                    range / units
%    ttt         - julian centuries of tt
%    opt         - method option                  '06', '02', '96', '80'
%
%  outputs       :
%    l           - delaunay element               rad
%    ll          - delaunay element               rad
%    f           - delaunay element               rad
%    d           - delaunay element               rad
%    omega       - delaunay element               rad
%    planetary longitudes                         rad
%
%  locals        :
%    ttt2,ttt3,  - powers of ttt
%
%  coupling      :
%    none        -
%
%  references    :
%    vallado       2004, 212-214
%
% [ l, l1, f, d, omega, ...
%   lonmer, lonven, lonear, lonmar, lonjup, lonsat, lonurn, lonnep, precrate ...
% ] = fundarg( ttt, opt );
% ----------------------------------------------------------------------------

function [ l, l1, f, d, omega, ...
    lonmer, lonven, lonear, lonmar, lonjup, lonsat, lonurn, lonnep, precrate ...
    ] = fundarg( ttt )


% ---- determine coefficients for iau 2000 nutation theory ----
ttt2 = ttt*ttt;
ttt3 = ttt2*ttt;
ttt4 = ttt2*ttt2;



% ---- iau 1980 theory
l = ((((0.064) * ttt + 31.310) * ttt + 1717915922.6330) * ttt) / 3600.0 + 134.96298139;
l1 = ((((-0.012) * ttt - 0.577) * ttt + 129596581.2240) * ttt) / 3600.0 + 357.52772333;
f = ((((0.011) * ttt - 13.257) * ttt + 1739527263.1370) * ttt) / 3600.0 + 93.27191028;
d = ((((0.019) * ttt - 6.891) * ttt + 1602961601.3280) * ttt) / 3600.0 + 297.85036306;
omega = ((((0.008) * ttt + 7.455) * ttt - 6962890.5390) * ttt) / 3600.0 + 125.04452222;

% ------ form the planetary arguments in deg
lonmer  = 252.3 + 149472.0 *ttt;
lonven  = 179.9 +  58517.8 *ttt;   % deg
lonear  =  98.4 +  35999.4 *ttt;
lonmar  = 353.3 +  19140.3 *ttt;
lonjup  =  32.3 +   3034.9 *ttt;
lonsat  =  48.0 +   1222.1 *ttt;
lonurn  =   0.0;
lonnep  =   0.0;
precrate=   0.0;


% ---- convert units to rad
l    = rem( l,360.0  )     * pi/180; % rad
l1   = rem( l1,360.0  )    * pi/180;
f    = rem( f,360.0  )     * pi/180;
d    = rem( d,360.0  )     * pi/180;
omega= rem( omega,360.0  ) * pi/180;

lonmer= rem( lonmer,360.0 ) * pi/180;  % rad
lonven= rem( lonven,360.0 ) * pi/180;
lonear= rem( lonear,360.0 ) * pi/180;
lonmar= rem( lonmar,360.0 ) * pi/180;
lonjup= rem( lonjup,360.0 ) * pi/180;
lonsat= rem( lonsat,360.0 ) * pi/180;
lonurn= rem( lonurn,360.0 ) * pi/180;
lonnep= rem( lonnep,360.0 ) * pi/180;
precrate= rem( precrate,360.0 ) * pi/180;

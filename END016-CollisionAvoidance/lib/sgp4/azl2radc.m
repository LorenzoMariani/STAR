
% azl2radc
%
% this function finds the rtasc decl values given the az-el
%
%
%
function [rtasc,decl] = azl2radc(az, el, lat, lst)


decl = asin( sin(el)*sin(lat) + cos(el)*cos(lat)*cos(az) );

slha1 = -( sin(az)*cos(el)*cos(lat) ) / ( cos(decl)*cos(lat) );
clha1 = ( sin(el) - sin(lat)*sin(decl) ) / ( cos(decl)*cos(lat) );

lha1 = atan2(slha1,clha1);

% alt approach
slha2 = -( sin(az)*cos(el) ) / ( cos(decl) );
clha2 = ( cos(lat)*sin(el) - sin(lat)*cos(el)*cos(az) ) / ( cos(decl) );


rtasc = lst - lha1;



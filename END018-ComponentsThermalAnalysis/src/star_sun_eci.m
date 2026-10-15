function su = star_sun_eci(dateUTC)
% STAR_SUN_ECI  Versore Sole in ECI (equatoriale), modello a bassa precisione.
%   Accuratezza ~0.01 deg, piu' che sufficiente per beta e carichi termici.
d   = days(dateUTC - datetime(2000,1,1,12,0,0,'TimeZone','UTC'));   % giorni da J2000
L   = deg2rad(mod(280.460 + 0.9856474*d, 360));        % longitudine media
g   = deg2rad(mod(357.528 + 0.9856003*d, 360));        % anomalia media
lam = L + deg2rad(1.915)*sin(g) + deg2rad(0.020)*sin(2*g);   % longitudine eclittica
ecl = deg2rad(23.439 - 4e-7*d);                        % obliquita'
su  = [cos(lam); cos(ecl)*sin(lam); sin(ecl)*sin(lam)];
su  = su/norm(su);
end

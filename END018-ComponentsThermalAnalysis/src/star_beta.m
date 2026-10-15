function beta = star_beta(orb)
% STAR_BETA  Angolo beta [deg] all'inizio missione, da orbita + data.
%   sin(beta) = s_hat . h_hat  (s = Sole ECI, h = normale al piano orbitale).
su = star_sun_eci(orb.start);
i  = deg2rad(orb.incl); Om = deg2rad(orb.raan);
h  = [sin(Om)*sin(i); -cos(Om)*sin(i); cos(i)];
beta = rad2deg(asin(max(-1,min(1, dot(su,h)))));
end

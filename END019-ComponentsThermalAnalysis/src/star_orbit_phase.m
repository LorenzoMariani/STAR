function [r, uDot, phi0] = star_orbit_phase(cfg, orb)
% STAR_ORBIT_PHASE  Raggio, velocita' angolare e fase iniziale dell'orbita STAR.
%   [r, uDot, phi0] = star_orbit_phase(cfg, orb)
%   r    [m]     raggio orbitale: quota sopra il raggio equatoriale WGS84,
%                come la definisce END-001 (Re_eq + alt)
%   uDot [rad/s] velocita' media dell'argomento di latitudine con i termini
%                secolari J2 del propagatore di END-001 (propagate_orbit_j2):
%                n_bar + d(omega)/dt, ~0.1% sotto il moto kepleriano
%   phi0 [rad]   angolo, nel piano orbitale, del satellite a t = 0 dalla
%                proiezione del Sole (l'asse x del sistema di star_thermal_run:
%                s = [cos(beta); 0; sin(beta)], z = normale all'orbita), dagli
%                elementi di satellite_XX.json (RAAN, inclinazione, nu) e dal
%                Sole all'inizio missione. Fino al 2026-10-15 ogni satellite
%                partiva a phi = 0 (mezzogiorno orbitale) con r = 6371 km + alt
%                e moto kepleriano: le eclissi non erano allineate ai pass
%                reali di END-003.
e = cfg.env;
r = e.Req + orb.alt;
i = deg2rad(orb.incl);
n = sqrt(e.mu/r^3);
k = 0.75*e.J2*(e.Req/r)^2;
nbar = n*(1 + k*(2 - 3*sin(i)^2));
uDot = nbar*(1 + k*(4 - 5*sin(i)^2));
su = star_sun_eci(orb.start);
Om = deg2rad(orb.raan); u0 = deg2rad(orb.omega + orb.nu);
h  = [sin(Om)*sin(i); -cos(Om)*sin(i); cos(i)];          % normale all'orbita (come star_beta)
e1 = su - (su'*h)*h;                                       % proiezione del Sole sul piano
if norm(e1) < 1e-9                                         % beta = +-90 deg: fase indifferente
    a = [1; 0; 0]; if abs(h(1)) > 0.9, a = [0; 1; 0]; end
    e1 = cross(h, a);
end
e1 = e1/norm(e1);
e2 = cross(h, e1);
r0 = [cos(Om)*cos(u0) - sin(Om)*sin(u0)*cos(i); ...
      sin(Om)*cos(u0) + cos(Om)*sin(u0)*cos(i); ...
      sin(u0)*sin(i)];
phi0 = atan2(r0'*e2, r0'*e1);
end

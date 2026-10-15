function Phi = twobody_stm(r0, v0, dt)
%TWOBODY_STM 6x6 two-body state transition matrix in ECI.
%
%   Phi = twobody_stm(r0, v0, dt) returns the 6x6 STM that maps a small
%   variation of the ECI state at t0 to its propagated value at t0 + dt
%   under Keplerian (point-mass Earth) dynamics:
%
%       [ dr(t0+dt); dv(t0+dt) ] = Phi * [ dr(t0); dv(t0) ]
%
%   Inputs in km, km/s; dt in seconds.
%
%   Implementation: central finite-difference of the Lagrange f/g universal-
%   variable Kepler propagator (kepler_fg below). For the small propagation
%   intervals encountered in this prototype (latest TLE epoch -> TCA,
%   typically << 1 day) two-body dominates the SGP4 covariance evolution
%   and the finite-difference STM converges to many digits with default
%   step sizes. Not a substitute for an SGP4-linearized STM over multi-day
%   propagations.

r0 = r0(:); v0 = v0(:);
x0 = [r0; v0];

% Step sizes (km / km/s); scaled by state magnitude to keep relative
% perturbation in the well-conditioned range for double precision.
h_r = max(1e-3, 1e-7 * norm(r0));     % km
h_v = max(1e-6, 1e-7 * norm(v0));     % km/s
h   = [h_r; h_r; h_r; h_v; h_v; h_v];

Phi = zeros(6, 6);
for k = 1:6
    xp = x0;  xp(k) = xp(k) + h(k);
    xm = x0;  xm(k) = xm(k) - h(k);
    yp = kepler_fg(xp(1:3), xp(4:6), dt);
    ym = kepler_fg(xm(1:3), xm(4:6), dt);
    Phi(:, k) = (yp - ym) / (2 * h(k));
end
end

% -----------------------------------------------------------------------
function y = kepler_fg(r0, v0, dt)
%KEPLER_FG Two-body propagation via universal-variable f/g (Vallado Alg. 8).

mu = 398600.4418;     % km^3/s^2
r0n = norm(r0);
v0n = norm(v0);
energy = 0.5*v0n^2 - mu/r0n;
alpha  = -2*energy/mu;             % = 1/a  (sign: + ellipse, 0 parabola, - hyperbola)
sqmu   = sqrt(mu);

% Initial guess for chi
if alpha > 1e-10
    chi = sqmu * dt * alpha;
elseif alpha < -1e-10
    a   = 1/alpha;
    chi = sign(dt) * sqrt(-a) * ...
          log( -2*mu*alpha*dt / ...
               (dot(r0,v0) + sign(dt)*sqrt(-mu*a)*(1 - r0n*alpha)) );
else
    chi = sqmu*dt/r0n;
end

sigma0 = dot(r0, v0) / sqmu;

% Newton-Raphson on universal Kepler equation
for it = 1:60
    psi = chi^2 * alpha;
    [c2, c3] = stumpff(psi);
    r  = chi^2*c2 + sigma0*chi*(1 - psi*c3) + r0n*(1 - psi*c2);
    F  = sigma0*chi^2*c2 + (1 - r0n*alpha)*chi^3*c3 + r0n*chi - sqmu*dt;
    dchi = -F / r;
    chi = chi + dchi;
    if abs(dchi) < 1e-11 * max(1, abs(chi))
        break
    end
end
psi = chi^2 * alpha;
[c2, c3] = stumpff(psi);
r  = chi^2*c2 + sigma0*chi*(1 - psi*c3) + r0n*(1 - psi*c2);

f    = 1 - chi^2*c2/r0n;
g    = dt - chi^3*c3/sqmu;
fdot = sqmu/(r*r0n) * chi * (psi*c3 - 1);
gdot = 1 - chi^2*c2/r;

r1 = f*r0    + g*v0;
v1 = fdot*r0 + gdot*v0;
y  = [r1; v1];
end

% -----------------------------------------------------------------------
function [c2, c3] = stumpff(psi)
if psi > 1e-6
    s = sqrt(psi);
    c2 = (1 - cos(s))/psi;
    c3 = (s - sin(s))/s^3;
elseif psi < -1e-6
    s = sqrt(-psi);
    c2 = (1 - cosh(s))/psi;
    c3 = (sinh(s) - s)/s^3;
else
    c2 = 0.5 - psi/24 + psi^2/720;
    c3 = 1/6 - psi/120 + psi^2/5040;
end
end

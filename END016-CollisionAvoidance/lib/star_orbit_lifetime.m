function L = star_orbit_lifetime(alt_km, incl_deg, B, f107, opts)
%STAR_ORBIT_LIFETIME Orbital lifetime under drag and post-mission disposal (STAR END-016).
%   L = star_orbit_lifetime(alt_km, incl_deg, B, f107, opts) for a circular
%   orbit at alt_km [km] (altitude above the WGS84 equatorial radius, as
%   END-001) and inclination incl_deg [deg], ballistic coefficient
%   B = Cd*A/m [m^2/kg], constant solar activity F10.7 = F10.7A = f107 [sfu].
%   opts (all optional): .ap (15), .reentry_km (120), .max_years (200),
%   .rules_years ([5 25]), .h_step_km (5), .doy (80).
%
%   Density: NRLMSISE-00 (atmosnrlmsise00) averaged over the orbit (argument
%   of latitude) and over local solar time, tabulated in altitude and
%   interpolated in log. Decay: Gauss equations for a tangential drag
%   acceleration -0.5*rho*v^2*B, averaged over the mean anomaly, integrated
%   in (a, e) until the perigee is below opts.reentry_km.
%
%   L fields: passive_years (Inf beyond max_years), curve_t_years /
%   curve_alt_km (mean altitude), drag_dv_m_s_per_year (to hold alt_km),
%   rules_years, disposal_dv_m_s (one per rule: perigee-lowering burn at
%   alt_km that brings the lifetime within the rule; 0 when the passive
%   lifetime already complies), disposal_perigee_km, rho_kg_m3 (at alt_km).
if nargin < 5, opts = struct(); end
ap = getf(opts, 'ap', 15); hre = getf(opts, 'reentry_km', 120); ymax = getf(opts, 'max_years', 200);
rules = getf(opts, 'rules_years', [5 25]); dh = getf(opts, 'h_step_km', 5); doy = getf(opts, 'doy', 80);
mu = 398600.4418e9; Re = 6378137; yr = 365.25*86400;

% orbit- and local-time-averaged density table
h = (100:dh:max(alt_km + 50, 300))';
u = linspace(0, 2*pi, 25); u(end) = [];
lst = 0:2:22;
[H, U, LST] = ndgrid(h, u, lst);
lat = asind(sind(incl_deg)*sin(U(:)));
[~, rho] = atmosnrlmsise00(H(:)*1e3, lat, zeros(numel(lat), 1), 2026*ones(numel(lat), 1), doy*ones(numel(lat), 1), ...
    LST(:)*3600, f107*ones(numel(lat), 1), f107*ones(numel(lat), 1), ap*ones(numel(lat), 1));
rhoTab = mean(reshape(rho(:, 6), size(H)), [2 3]);
logrho = @(hq) interp1(h, log(rhoTab), hq, 'linear', 'extrap');
density = @(hq) exp(logrho(max(hq, h(1))));

L.rho_kg_m3 = density(alt_km);
r0 = Re + alt_km*1e3; v0 = sqrt(mu/r0);
L.drag_dv_m_s_per_year = 0.5*L.rho_kg_m3*v0^2*B*yr;

% passive decay from the circular orbit
[L.passive_years, L.curve_t_years, L.curve_alt_km] = decay(r0, 0);
L.rules_years = rules;
L.disposal_dv_m_s = zeros(size(rules));
L.disposal_perigee_km = nan(size(rules));
for k = 1:numel(rules)
    if L.passive_years <= rules(k)
        L.disposal_perigee_km(k) = alt_km;
        continue
    end
    lo = hre; hi = alt_km;                 % lifetime grows with the perigee: bisection on it
    for it = 1:30
        mid = 0.5*(lo + hi);
        if decay_life(mid) <= rules(k), lo = mid; else, hi = mid; end
        if hi - lo < 0.5, break; end
    end
    hp = lo;
    a = (r0 + Re + hp*1e3)/2;
    L.disposal_perigee_km(k) = hp;
    L.disposal_dv_m_s(k) = v0 - sqrt(mu*(2/r0 - 1/a));
end

    function y = decay_life(hp_km)
        rp = Re + hp_km*1e3;
        a = (r0 + rp)/2; e = (r0 - rp)/(r0 + rp);
        y = decay(a, e);
    end

    function [years, ty, hy] = decay(a0, e0)
        if e0 == 0, x0 = [a0; 0]; else, x0 = [a0; e0]; end
        o = odeset('Events', @perigee_event, 'RelTol', 1e-6, 'AbsTol', [1; 1e-9], 'MaxStep', ymax*yr/200);
        [tt, xx, te] = ode45(@rates, [0 ymax*yr], x0, o);
        if isempty(te), years = Inf; else, years = te(1)/yr; end
        ty = tt/yr; hy = (xx(:, 1) - Re)/1e3;
    end

    function [value, terminal, direction] = perigee_event(~, x)
        value = x(1)*(1 - x(2)) - Re - hre*1e3;      % perigee altitude above the re-entry altitude
        terminal = 1; direction = -1;
    end

    function dx = rates(~, x)
        % 2026-10-17: with a fast decay (low orbit, high solar activity) an ode45 trial step can go past the re-entry
        % (a < Re, complex velocity and density); the rates are then evaluated at the re-entry altitude, the state stays
        % real and the perigee event still stops the integration
        a = max(real(x(1)), Re + hre*1e3); e = min(max(real(x(2)), 0), 0.99);
        M = linspace(0, 2*pi, 73); M(end) = [];
        E = M;
        for it = 1:8, E = E - (E - e*sin(E) - M)./(1 - e*cos(E)); end
        r = a*(1 - e*cos(E));
        cf = (cos(E) - e)./(1 - e*cos(E));
        v = sqrt(mu*(2./r - 1/a));
        rho_ = density((r - Re)/1e3);
        da = -mean(rho_.*B.*v.^3)*a^2/mu;
        de = -mean((e + cf).*rho_.*B.*v);
        if e <= 0 && de < 0, de = 0; end
        dx = [da; de];
    end
end

function v = getf(s, f, d)
if isfield(s, f) && ~isempty(s.(f)), v = s.(f); else, v = d; end
end

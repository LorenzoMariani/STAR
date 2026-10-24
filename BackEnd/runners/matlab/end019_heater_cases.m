function H = end019_heater_cases(cfg_json)
% END019_HEATER_CASES  Battery heater of the END-019 cold case: sizing and verification (STAR phase F4, 2026-10-23).
%   H = end019_heater_cases('input_termico.json') reads the same configuration as star_thermal_main and writes
%   heater_cases.json into its output_dir. END-019 is a black box: this file lives outside the module and only
%   calls its functions (star_config, star_build_model, star_orbit_phase, star_beta, star_read_orbit,
%   star_read_passes, star_thermal_step) without modifying them.
%
%   The thermostat acts from outside the step: before each star_thermal_step call the battery power of the
%   model is P.M.Pc(iBAT) = Pconst + Q_heater.
%   - Sizing (ideal thermostat, cold case: beta and idle dissipation of the case named 'cold' in cfg.cases,
%     nadir, SAR off, periodic orbit as star_design_case). For a given previous temperature the Backward-Euler
%     step is linear in Q, so two calls (Q = 0 and Q = 1 W) give the Q >= 0 that holds T_BAT at the setpoint.
%     Over the periodic orbit: required peak and orbit mean, and the fraction of the orbit the thermostat heats.
%     The sizing does not depend on the heater of the design (stable across the CEF iterations).
%   - Verification (bang-bang, +-hysteresis_K around the setpoint) with the heater power of the design
%     (opts.battery_heater.power_w): battery min / max in the cold case and over the mission window
%     (window run as star_thermal_run, SAR in the imaging passes, nominal dissipation).
%   Setpoint: opts.battery_heater.setpoint_c, else the battery lower limit (bat_min_C, the discharge limit) + 5 K; with
%   opts.bat_charge_min_C (charge lower limit of the battery datasheet) at least that + the hysteresis, so that the battery
%   is not colder than the charge limit when the sunlit part, and the charge, starts (battery_charge_start_C below).
%   The heater heat stays inside END-019; its energy is END-004's (mean_W of the cold case).
if nargin < 1 || isempty(cfg_json), cfg_json = 'input_termico.json'; end
cfg_json = char(cfg_json);
if ~isfile(cfg_json)
    error('end019_heater_cases:config', 'Configuration file not found: %s', cfg_json);
end
opts = jsondecode(fileread(cfg_json));
base = fileparts(cfg_json);
for f = {'star_input_dir', 'output_dir'}
    if isfield(opts, f{1}) && ~isempty(opts.(f{1})) && ~is_absolute(opts.(f{1}))
        opts.(f{1}) = fullfile(base, opts.(f{1}));
    end
end
cfg = star_config(opts);
hyst = 1.0;                                                  % [K] thermostat hysteresis (+-)
heater = getf(opts, 'battery_heater', struct());
Ph = getf(heater, 'power_w', 0);
H = struct('module_id', 'END-019', 'tool', 'end019_heater_cases (outside the END-019 module)', ...
           'generated_at', char(datetime('now', 'Format', 'yyyy-MM-dd HH:mm:ss')), 'status', 'completed', 'reason', '', ...
           'bat_min_limit_C', cfg.limits.BAT_min, 'setpoint_C', NaN, 'hysteresis_K', hyst, ...
           'heater_in_design', struct('power_W', Ph, 'setpoint_C', getf(heater, 'setpoint_c', NaN)), ...
           'rule', ['ideal thermostat in the cold case (sizing), bang-bang with the heater of the design (verification); ' ...
                    'setpoint = battery lower limit + 5 K unless the design sets it'], ...
           'satellites', {{}}, 'worst', struct());
M0 = star_build_model(cfg);
if isempty(M0.iBAT) || isnan(cfg.limits.BAT_min)
    H.status = 'not_applicable';
    H.reason = 'the model has no battery node or no battery lower limit';
    write_out(cfg, H);
    return
end
Tchg = getf(opts, 'bat_charge_min_C', NaN);
H.bat_charge_min_limit_C = Tchg;
H.setpoint_C = getf(heater, 'setpoint_c', max([cfg.limits.BAT_min + 5, Tchg + hyst]));
Tset = H.setpoint_C;
cs = cold_case(cfg);
sats = dir(fullfile(cfg.io.sat_dir, cfg.io.sat_glob));
if isempty(sats)
    error('end019_heater_cases:noinput', 'No satellite_*.json in: %s', cfg.io.sat_dir);
end
cache = containers.Map();
S = cell(1, numel(sats));
for k = 1:numel(sats)
    orb = star_read_orbit(fullfile(sats(k).folder, sats(k).name));
    b = star_beta(orb); Pint = sum(cfg.nodes.Pconst);
    if ~isempty(cs)
        Pint = cs.P_internal_W;
        j = [];
        if isfield(cs, 'satellite_index'), j = find(cs.satellite_index(:) == orb.index, 1); end
        if ~isempty(j) && isfield(cs, 'beta_deg'), b = cs.beta_deg(j); end
    end
    key = sprintf('%.0f|%.3f|%.2f|%.4f', orb.alt, orb.incl, b, Pint);
    if isKey(cache, key)
        C = cache(key);
    else
        C = cold_heater(cfg, orb, b, Pint, Tset, hyst, Ph);
        cache(key) = C;
    end
    s = struct('satellite_index', orb.index, 'satellite_label', sprintf('SAT-%02d', orb.index), 'cold', C, 'window', struct());
    if Ph > 0
        passes = zeros(0, 2);
        if isfile(cfg.io.pass_csv)
            passes = star_read_passes(cfg.io.pass_csv, orb.index, cfg.io.imaging_purpose, orb.start);
        end
        s.window = window_heater(cfg, orb, passes, Tset, hyst, Ph);
    end
    S{k} = s;
end
H.satellites = S;
peak = cellfun(@(s) s.cold.needed_peak_W, S); mean_w = cellfun(@(s) s.cold.needed_mean_W, S);
[~, kw] = max(peak);
H.worst = struct('needed_peak_W', round(max(peak), 4), 'needed_mean_W_cold', round(max(mean_w), 4), ...
                 'duty_cold_pct', S{kw}.cold.ideal_on_pct, 'satellite_label', S{kw}.satellite_label);
if Ph > 0
    tmin = cellfun(@(s) min(s.cold.verify.battery_min_C, s.window.battery_min_C), S);
    tmax = cellfun(@(s) max(s.cold.verify.battery_max_C, s.window.battery_max_C), S);
    H.worst.battery_min_with_heater_C = round(min(tmin), 2);
    H.worst.battery_max_with_heater_C = round(max(tmax), 2);
    cs0 = cellfun(@(s) s.cold.verify.charge_start_C, S);
    if any(~isnan(cs0)), H.worst.battery_charge_start_C = round(min(cs0), 2); end
    H.worst.duty_cold_pct = S{kw}.cold.verify.duty_pct;
    H.worst.mean_W_cold_design_heater = S{kw}.cold.verify.mean_W;
end
write_out(cfg, H);
fprintf('END-019 heater cases: peak %.3f W, mean %.3f W (cold case, setpoint %.1f degC)\n', H.worst.needed_peak_W, ...
        H.worst.needed_mean_W_cold, Tset);
end

% ---------------------------------------------------------------------------------------------------------------
function cs = cold_case(cfg)
cs = [];
cases = cfg.cases;
for c = 1:numel(cases)
    x = cases(c);
    if iscell(x), x = x{1}; end      % jsondecode gives a cell array when the cases have different fields
    if isfield(x, 'name') && strcmp(x.name, 'cold'), cs = x; return; end
end
end

function [P, nO, Torb] = case_model(cfg, orb, beta, Pint)
% same model as star_design_case: periodic orbit at fixed beta, dissipation Pint split as cfg.nodes.Pdefault
c2 = cfg;
c2.nodes.Pconst = Pint*cfg.nodes.Pdefault/sum(cfg.nodes.Pdefault);
M = star_build_model(c2);
[r, uDot] = star_orbit_phase(c2, orb);
Torb = 2*pi/uDot;
s = [cosd(beta); 0; sind(beta)];
P = struct('M', M, 'e', c2.env, 'r', r, 'uDot', uDot, 'phi0', 0, 's', s, 'Cdt', M.C/c2.sim.dt, ...
           'cfg', c2, 'passes', zeros(0, 2), 'Torb', Torb, 'hasSAR', false);
nO = round(Torb/c2.sim.dt);
end

function C = cold_heater(cfg, orb, beta, Pint, Tset, hyst, Ph)
[P, nO, Torb] = case_model(cfg, orb, beta, Pint);
dt = cfg.sim.dt; iB = P.M.iBAT; Ts = 273.15 + Tset;
nmax = max(cfg.sim.spinup_orbits, 200);
% ideal thermostat: T_BAT never below the setpoint
T = (273.15 + cfg.T0)*ones(P.M.Nn, 1);
q = zeros(nO, 1); Tb = zeros(nO, 1); lit = zeros(nO, 1);
for o = 1:nmax
    T1 = T;
    for n = 1:nO
        [T, q(n), lit(n)] = ideal_step(P, T, (n-1)*dt, iB, Ts);
        Tb(n) = T(iB) - 273.15;
    end
    if max(abs(T - T1)) < cfg.sim.spinup_tol, break; end
end
C = struct('beta_deg', round(beta, 3), 'P_internal_W', round(Pint, 4), 'eclipse_min', round((1 - mean(lit))*Torb/60, 2), ...
           'needed_peak_W', round(max(q), 4), 'needed_mean_W', round(mean(q), 4), 'ideal_on_pct', round(100*mean(q > 1e-9), 2), ...
           'ideal_battery_min_C', round(min(Tb), 2), 'ideal_charge_start_C', exit_temp(Tb, lit), 'periodic_orbits', o, 'verify', struct());
if Ph <= 0, return; end
% bang-bang with the heater of the design, from the ideal periodic state (a limit cycle need not repeat orbit by
% orbit: at most cfg.sim.spinup_orbits orbits)
on = false; u = zeros(nO, 1); Tb = zeros(nO, 1);
for o = 1:cfg.sim.spinup_orbits
    T1 = T;
    for n = 1:nO
        [T, on, lit(n)] = bang_step(P, T, (n-1)*dt, iB, Ts, hyst, Ph, on);
        u(n) = on; Tb(n) = T(iB) - 273.15;
    end
    if max(abs(T - T1)) < cfg.sim.spinup_tol, break; end
end
C.verify = struct('power_W', Ph, 'battery_min_C', round(min(Tb), 2), 'battery_max_C', round(max(Tb), 2), ...
                  'charge_start_C', exit_temp(Tb, lit), 'mean_W', round(Ph*mean(u), 4), 'duty_pct', round(100*mean(u), 2), 'orbits', o);
end

function W = window_heater(cfg, orb, passes, Tset, hyst, Ph)
% the mission window as star_thermal_run (real phase, beta of the date, nominal dissipation, SAR in the passes), heater on
M = star_build_model(cfg);
[r, uDot, phi0] = star_orbit_phase(cfg, orb);
Torb = 2*pi/uDot;
beta = star_beta(orb); s = [cosd(beta); 0; sind(beta)];
dt = cfg.sim.dt; N = round(orb.sim_hours*3600/dt);
P = struct('M', M, 'e', cfg.env, 'r', r, 'uDot', uDot, 'phi0', phi0, 's', s, 'Cdt', M.C/dt, ...
           'cfg', cfg, 'passes', passes, 'Torb', Torb, 'hasSAR', ~isempty(M.iSAR));
iB = M.iBAT; Ts = 273.15 + Tset;
T = (273.15 + cfg.T0)*ones(M.Nn, 1); on = false;
nO = round(Torb/dt);
for o = 1:cfg.sim.spinup_orbits
    T1 = T;
    for n = 1:nO
        [T, on] = bang_step(P, T, (n-1-nO)*dt, iB, Ts, hyst, Ph, on);
    end
    if max(abs(T - T1)) < cfg.sim.spinup_tol, break; end
end
u = zeros(N, 1); Tb = zeros(N, 1);
for n = 1:N
    [T, on] = bang_step(P, T, (n-1)*dt, iB, Ts, hyst, Ph, on);
    u(n) = on; Tb(n) = T(iB) - 273.15;
end
W = struct('power_W', Ph, 'beta_deg', round(beta, 3), 'battery_min_C', round(min(Tb), 2), 'battery_max_C', round(max(Tb), 2), ...
           'mean_W', round(Ph*mean(u), 4), 'duty_pct', round(100*mean(u), 2));
end

function [T, q, L] = ideal_step(P, T, ts, iB, Ts)
[T0, L] = star_thermal_step(P, T, ts);
q = 0;
if T0(iB) >= Ts, T = T0; return; end
P1 = P; P1.M.Pc(iB) = P1.M.Pc(iB) + 1;          % +1 W at the battery: the step is linear in Q
T1 = star_thermal_step(P1, T, ts);
q = (Ts - T0(iB))/(T1(iB) - T0(iB));
T = T0 + q*(T1 - T0);
end

function [T, on, L] = bang_step(P, T, ts, iB, Ts, hyst, Ph, on)
if T(iB) < Ts - hyst, on = true; elseif T(iB) > Ts + hyst, on = false; end
if on, P.M.Pc(iB) = P.M.Pc(iB) + Ph; end
[T, L] = star_thermal_step(P, T, ts);
end

function v = exit_temp(Tb, lit)
% battery temperature [C] at the eclipse exit (first sunlit step after an eclipse step), the lowest of the orbit; NaN without eclipse
sun = lit(:) > 0.5;
k = find(sun & ~circshift(sun, 1));
if isempty(k), v = NaN; else, v = round(min(Tb(k)), 2); end
end

function write_out(cfg, H)
if ~exist(cfg.io.out_dir, 'dir'), mkdir(cfg.io.out_dir); end
fid = fopen(fullfile(cfg.io.out_dir, 'heater_cases.json'), 'w');
fwrite(fid, jsonencode(H, 'PrettyPrint', true)); fclose(fid);
end

function v = getf(s, f, d)
if isstruct(s) && isfield(s, f) && ~isempty(s.(f)), v = s.(f); else, v = d; end
end

function tf = is_absolute(p)
tf = ~isempty(regexp(char(p), '^([A-Za-z]:[\\/]|[\\/])', 'once'));
end

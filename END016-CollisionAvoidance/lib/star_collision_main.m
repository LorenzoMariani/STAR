function S = star_collision_main(cfg_json)
%STAR_COLLISION_MAIN END-016 inside STAR: space-safety checks of a designed constellation.
%   S = star_collision_main('input_collision_avoidance.json') reads the END-001
%   products of a STAR run (satellite_NN.json and satellite_NN_ephemeris.csv
%   in cfg.star_input_dir) and writes in cfg.output_dir:
%   1. close approaches between satellites of the constellation (every pair,
%      over the ephemeris window): intra_pair_min_distance.csv,
%      intra_close_approaches.csv (events closer than screening_km);
%   2. orbital lifetime and post-mission disposal of every orbit shell under
%      the solar activity levels requested: disposal_lifetime.csv;
%   3. space_safety_summary.json with the configuration, KPIs, the events, the
%      pair matrix, the distance history of the closest pair and the decay
%      curves (read by the STAR results tab END016).
%
%   Close approaches: minima of the sampled distance of each pair refined by
%   cubic Hermite interpolation of the ephemeris (positions and their exact
%   time derivatives), so the time of closest approach (TCA) and the miss
%   distance do not depend on the 10 s sampling. At the TCA: miss vector in
%   the radial / in-track / cross-track frame of the first satellite,
%   relative speed, sub-satellite point, collision probability Pc (Chan,
%   chan_pc) with the declared 1-sigma position uncertainty of each satellite
%   (independent, Gaussian), its circumscribing-square upper bound, and Pc_max:
%   the largest Pc over every possible covariance, whatever the uncertainty
%   (the hard-body disc lies inside the strip |x| <= R across the miss
%   direction, so Pc <= max over sigma of P(|d + sigma*xi| <= R), reached by a
%   covariance stretched along the miss vector).
%
%   Configuration (JSON; relative paths are relative to the JSON file):
%     star_input_dir, output_dir
%     spacecraft: mass_kg, drag_area_m2, cd
%     hard_body_radius_m        combined radius of the two objects
%     position_sigma_rtn_m      [radial in-track cross-track] 1-sigma of each satellite
%     screening_km              report close approaches closer than this (10)
%     pc_threshold              Pc above which an event is flagged (1e-4)
%     mission_lifetime_years    operational life before disposal
%     disposal_rules_years      e.g. [5 25] (FCC 5-year, IADC 25-year)
%     solar_f107                F10.7 levels, e.g. [70 140 220] (low, mean, high)
%     reentry_km                120
if nargin < 1 || isempty(cfg_json), cfg_json = 'input_collision_avoidance.json'; end
cfg_json = char(cfg_json);
if ~isfile(cfg_json), error('star_collision_main:config', 'Configuration file not found: %s', cfg_json); end
if isempty(regexp(cfg_json, '^([A-Za-z]:[\\/]|[\\/])', 'once')), cfg_json = fullfile(pwd, cfg_json); end
cfg = jsondecode(fileread(cfg_json));
base = fileparts(cfg_json);
cfg.star_input_dir = absdir(getf(cfg, 'star_input_dir', 'star_input'), base);
cfg.output_dir = absdir(getf(cfg, 'output_dir', 'output'), base);
if ~exist(cfg.output_dir, 'dir'), mkdir(cfg.output_dir); end
sc = getf(cfg, 'spacecraft', struct());
mass = getf(sc, 'mass_kg', 100); area = getf(sc, 'drag_area_m2', 1); cd = getf(sc, 'cd', 2.2);
hbr_km = getf(cfg, 'hard_body_radius_m', 2*sqrt(area/pi)) / 1e3;
sig_km = reshape(getf(cfg, 'position_sigma_rtn_m', [50 200 50]), 1, 3) / 1e3;
scr_km = getf(cfg, 'screening_km', 10);
pc_thr = getf(cfg, 'pc_threshold', 1e-4);
life_y = getf(cfg, 'mission_lifetime_years', NaN);
rules = reshape(getf(cfg, 'disposal_rules_years', [5 25]), 1, []);
f107 = reshape(getf(cfg, 'solar_f107', [70 140 220]), 1, []);
hre = getf(cfg, 'reentry_km', 120);

fprintf('== STAR END-016 space safety ==\ninput : %s\noutput: %s\n', cfg.star_input_dir, cfg.output_dir);
sats = read_constellation(cfg.star_input_dir);
n = numel(sats);
fprintf('%d satellite(s), %d pair(s), ephemeris %s -> %s, step %g s\n', n, n*(n - 1)/2, ...
    char(sats(1).t0 + seconds(sats(1).t(1))), char(sats(1).t0 + seconds(sats(1).t(end))), sats(1).t(2) - sats(1).t(1));

%% 1. close approaches inside the constellation
pairMin = nan(n); events = [];
for i = 1:n - 1
    for j = i + 1:n
        [dmin, ev] = pair_close_approaches(sats(i), sats(j), scr_km);
        pairMin(i, j) = dmin.miss_km; pairMin(j, i) = dmin.miss_km;
        pairInfo(i, j) = dmin; %#ok<AGROW>
        for e = ev
            events = [events, finish_event(e, sats(i), sats(j), i, j)]; %#ok<AGROW>
        end
    end
end
if ~isempty(events)
    [~, o] = sort([events.miss_km]); events = events(o);
end
fprintf('close approaches below %g km: %d\n', scr_km, numel(events));

%% 2. orbital lifetime and disposal per shell
B = cd*area/mass;
shellKey = round([[sats.alt_km]' [sats.incl_deg]'], 3);
[shells, ~, shellOf] = unique(shellKey, 'rows', 'stable');
life = struct('alt_km', {}, 'incl_deg', {}, 'f107', {}, 'passive_years', {}, 'drag_dv_m_s_per_year', {}, ...
    'rules_years', {}, 'disposal_dv_m_s', {}, 'disposal_perigee_km', {}, 'curve_t_years', {}, 'curve_alt_km', {}, 'satellites', {});
ws = warning('off', 'all');
for s = 1:size(shells, 1)
    for f = f107
        L = star_orbit_lifetime(shells(s, 1), shells(s, 2), B, f, struct('rules_years', rules, 'reentry_km', hre));
        k = numel(life) + 1;
        life(k).alt_km = shells(s, 1); life(k).incl_deg = shells(s, 2); life(k).f107 = f;
        life(k).passive_years = L.passive_years; life(k).drag_dv_m_s_per_year = L.drag_dv_m_s_per_year;
        life(k).rules_years = rules; life(k).disposal_dv_m_s = L.disposal_dv_m_s; life(k).disposal_perigee_km = L.disposal_perigee_km;
        idx = unique(round(linspace(1, numel(L.curve_t_years), min(200, numel(L.curve_t_years)))));
        life(k).curve_t_years = L.curve_t_years(idx)'; life(k).curve_alt_km = L.curve_alt_km(idx)';
        life(k).satellites = find(shellOf == s)';
        fprintf('shell %.1f km %.2f deg, F10.7 %g: passive lifetime %s, disposal dv %s m/s\n', shells(s, 1), shells(s, 2), f, ...
            years_str(L.passive_years), mat2str(round(L.disposal_dv_m_s, 1)));
    end
end
warning(ws);

%% 3. outputs
labels = arrayfun(@(s) s.label, sats, 'UniformOutput', false);
write_pair_matrix(fullfile(cfg.output_dir, 'intra_pair_min_distance.csv'), labels, pairMin);
write_events(fullfile(cfg.output_dir, 'intra_close_approaches.csv'), events);
write_life(fullfile(cfg.output_dir, 'disposal_lifetime.csv'), life);

S = struct();
S.module_id = 'END-016';
S.generated_at = char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss'));
S.config = struct('mass_kg', mass, 'drag_area_m2', area, 'cd', cd, 'ballistic_coefficient_m2_kg', B, ...
    'hard_body_radius_m', hbr_km*1e3, 'position_sigma_rtn_m', sig_km*1e3, 'screening_km', scr_km, 'pc_threshold', pc_thr, ...
    'mission_lifetime_years', life_y, 'disposal_rules_years', rules, 'solar_f107', f107, 'reentry_km', hre);
S.window = struct('start_utc', iso(sats(1).t0 + seconds(sats(1).t(1))), 'end_utc', iso(sats(1).t0 + seconds(sats(1).t(end))), ...
    'hours', (sats(1).t(end) - sats(1).t(1))/3600, 'step_s', sats(1).t(2) - sats(1).t(1));
S.satellites = arrayfun(@(s) struct('label', s.label, 'alt_km', s.alt_km, 'incl_deg', s.incl_deg, 'raan_deg', s.raan_deg, 'nu_deg', s.nu_deg), sats);
S.pair_min_distance_km = pairMin;
S.events = events;
% KPIs
kp = struct();
kp.n_satellites = n; kp.n_pairs = n*(n - 1)/2;
if n > 1
    [m, ij] = min(pairMin(:)); [pi_, pj] = ind2sub([n n], ij);
    if pi_ > pj, [pi_, pj] = deal(pj, pi_); end           % named as the events: lower index first
    kp.min_separation_km = m; kp.min_separation_pair = sprintf('%s - %s', labels{pi_}, labels{pj});
    best = pairInfo(min(pi_, pj), max(pi_, pj));
    kp.min_separation_tca_utc = best.tca_utc;
    S.closest_pair = struct('pair', kp.min_separation_pair, 'history_t_hours', best.hist_t_hours, 'history_distance_km', best.hist_km);
else
    kp.min_separation_km = NaN; kp.min_separation_pair = ''; kp.min_separation_tca_utc = '';
end
kp.n_events_below_screening = numel(events);
kp.events_per_day = numel(events) / max(S.window.hours/24, eps);
if isempty(events)
    kp.n_events_below_1km = 0; kp.max_pc = 0; kp.max_pc_max = 0; kp.n_events_above_pc_threshold = 0;
else
    kp.n_events_below_1km = sum([events.miss_km] < 1);
    kp.max_pc = max([events.pc]); kp.max_pc_max = max([events.pc_max]);
    kp.n_events_above_pc_threshold = sum([events.pc] > pc_thr);
end
fmean = find(f107 == median(f107), 1); if isempty(fmean), fmean = 1; end
mid = life([life.f107] == f107(fmean));
kp.passive_lifetime_years_mean_activity = max([mid.passive_years]);
kp.passive_lifetime_years_min = min([life.passive_years]);      % over the solar activity levels
kp.passive_lifetime_years_max = max([life.passive_years]);
for r = 1:numel(rules)
    kp.(sprintf('complies_%dy_rule_mean_activity', rules(r))) = all([mid.passive_years] <= rules(r));
    kp.(sprintf('disposal_dv_m_s_%dy_rule_mean_activity', rules(r))) = max(arrayfun(@(x) x.disposal_dv_m_s(r), mid));
end
kp.drag_makeup_dv_m_s_per_year_mean_activity = max([mid.drag_dv_m_s_per_year]);
if ~isnan(life_y)
    kp.orbit_maintenance_needed = any([mid.passive_years] < life_y);
end
S.kpis = kp;
S.lifetime = life;
S.notes = { ...
    'Close approaches between satellites of the designed constellation only (END-001 orbits, J2 secular); other space objects are not included.', ...
    sprintf('Pc with the declared 1-sigma position uncertainty [%g %g %g] m (radial, in-track, cross-track) of each satellite; Pc_max is the largest Pc any uncertainty could give.', sig_km*1e3), ...
    'Lifetime: NRLMSISE-00 averaged over the orbit and the local time, constant solar activity per level; real decay crosses solar cycles (low and high levels bound it).', ...
    'Disposal: one perigee-lowering burn at the operational altitude bringing the lifetime within each rule.'};
fid = fopen(fullfile(cfg.output_dir, 'space_safety_summary.json'), 'w');
fwrite(fid, jsonencode(clean_json(S), 'PrettyPrint', true)); fclose(fid);
fprintf('OK: %d satellite(s); minimum separation %.3f km (%s); %d event(s) below %g km; written in %s\n', ...
    n, kp.min_separation_km, kp.min_separation_pair, numel(events), scr_km, cfg.output_dir);

    %% nested helpers using the configuration ------------------------------
    function e = finish_event(e, si, sj, i, j)
        % RTN components of the miss in the frame of the first satellite, Pc
        M = rot_eci2rtc(e.r1(:), e.v1(:));
        rel = e.r2(:) - e.r1(:); vrel = e.v2(:) - e.v1(:);
        ric = M*rel;
        P1 = M.'*diag(sig_km.^2)*M;
        M2 = rot_eci2rtc(e.r2(:), e.v2(:));
        P2 = M2.'*diag(sig_km.^2)*M2;
        [r2d, C2d] = conjunction_plane_2d(rel, vrel, P1 + P2);
        e.pair = sprintf('%s - %s', si.label, sj.label); e.i = i; e.j = j;
        e.radial_km = ric(1); e.intrack_km = ric(2); e.crosstrack_km = ric(3);
        e.rel_speed_km_s = norm(vrel);
        e.pc = chan_pc(r2d, C2d, hbr_km);
        e.pc_upper_bound = pc_upper_bound_square(r2d, C2d, hbr_km);
        e.pc_max = pc_max_any_covariance(norm(r2d), hbr_km);
        [e.lat_deg, e.lon_deg, e.alt_km] = subpoint(e.r1, e.tca);
        e.tca_utc = iso(e.tca);
        e = rmfield(e, {'r1', 'v1', 'r2', 'v2', 'tca'});
    end
end

%% ========================================================================
function sats = read_constellation(dirIn)
% satellite_NN.json (elements, epoch) and satellite_NN_ephemeris.csv (END-001)
dj = [dir(fullfile(dirIn, 'satellite_*.json')); dir(fullfile(dirIn, '*', 'satellite_*.json'))];
dj = dj(~contains({dj.name}, 'ephemeris'));
if isempty(dj), error('star_collision_main:input', 'No satellite_NN.json in %s', dirIn); end
[~, o] = sort({dj.name}); dj = dj(o);
sats = struct('label', {}, 'alt_km', {}, 'incl_deg', {}, 'raan_deg', {}, 'nu_deg', {}, 't0', {}, 't', {}, 'r', {}, 'v', {});
for k = 1:numel(dj)
    s = jsondecode(fileread(fullfile(dj(k).folder, dj(k).name)));
    [~, nm] = fileparts(dj(k).name);
    num = regexp(nm, '\d+', 'match', 'once');
    eph = fullfile(dj(k).folder, [nm '_ephemeris.csv']);
    if ~isfile(eph)
        error('star_collision_main:input', '%s has no ephemeris (%s): END-001 writes it since 2026-10-15.', dj(k).name, eph);
    end
    T = readtable(eph, 'TextType', 'string', 'Delimiter', ',');
    tt = datetime(T.time_utc, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss''Z''', 'TimeZone', 'UTC');
    sats(k).label = sprintf('SAT-%s', num);
    sats(k).alt_km = (s.orbit.alt_perigee_m + s.orbit.alt_apogee_m)/2e3;
    sats(k).incl_deg = s.orbit.inclination_deg; sats(k).raan_deg = s.orbit.raan_deg; sats(k).nu_deg = s.orbit.nu_deg;
    sats(k).t0 = tt(1); sats(k).t = seconds(tt - tt(1));
    sats(k).r = [T.x_eci_km T.y_eci_km T.z_eci_km];
    sats(k).v = [T.vx_eci_km_s T.vy_eci_km_s T.vz_eci_km_s];
end
for k = 2:numel(sats)
    if sats(k).t0 ~= sats(1).t0 || numel(sats(k).t) ~= numel(sats(1).t)
        error('star_collision_main:input', 'The ephemerides do not share the same time grid.');
    end
end
end

function [dmin, ev] = pair_close_approaches(a, b, scr_km)
% local minima of |r_b - r_a| on the time grid, refined by cubic Hermite
% interpolation on the two neighbouring steps
t = a.t; h = t(2) - t(1);
p = b.r - a.r; q = b.v - a.v;
d = vecnorm(p, 2, 2); s = vecnorm(q, 2, 2);
k = find(d(2:end-1) <= d(1:end-2) & d(2:end-1) <= d(3:end)) + 1;
cand = k(d(k) - s(k)*h < max(scr_km, 0) | d(k) == min(d));     % the true minimum is within one step
ev = struct('tca', {}, 'miss_km', {}, 'r1', {}, 'v1', {}, 'r2', {}, 'v2', {});
best = struct('miss_km', Inf, 'tca_utc', '');
for c = cand(:)'
    [tm, dm] = refine(c);
    if dm < best.miss_km
        best.miss_km = dm; best.tca_utc = iso(a.t0 + seconds(tm));
    end
    if dm < scr_km
        [r1, v1] = herm(a.r, a.v, t, tm); [r2, v2] = herm(b.r, b.v, t, tm);
        ev(end + 1) = struct('tca', a.t0 + seconds(tm), 'miss_km', dm, 'r1', r1, 'v1', v1, 'r2', r2, 'v2', v2); %#ok<AGROW>
    end
end
if isinf(best.miss_km)                       % minimum at the edge of the window
    [best.miss_km, kk] = min(d); best.tca_utc = iso(a.t0 + seconds(t(kk)));
end
stride = max(1, round(60/h));                % distance history every minute for the plot
best.hist_t_hours = (t(1:stride:end) - t(1))'/3600;
best.hist_km = d(1:stride:end)';
dmin = best;

    function [tm, dm] = refine(c)
        lo = t(max(c - 1, 1)); hi = t(min(c + 1, numel(t)));
        f = @(tq) norm(herm(b.r, b.v, t, tq) - herm(a.r, a.v, t, tq));
        [tm, dm] = fminbnd(f, lo, hi, optimset('TolX', 1e-4));
    end
end

function [r, v] = herm(R, V, t, tq)
% cubic Hermite interpolation of positions R (with derivatives V) at time tq
h = t(2) - t(1);
k = min(max(floor((tq - t(1))/h) + 1, 1), numel(t) - 1);
s = (tq - t(k))/h;
h00 = 2*s^3 - 3*s^2 + 1; h10 = s^3 - 2*s^2 + s; h01 = -2*s^3 + 3*s^2; h11 = s^3 - s^2;
r = h00*R(k, :) + h10*h*V(k, :) + h01*R(k + 1, :) + h11*h*V(k + 1, :);
if nargout > 1
    v = ((6*s^2 - 6*s)*R(k, :) + (3*s^2 - 4*s + 1)*h*V(k, :) + (-6*s^2 + 6*s)*R(k + 1, :) + (3*s^2 - 2*s)*h*V(k + 1, :))/h;
end
end

function pm = pc_max_any_covariance(d, R)
% supremum of Pc over every 2-D Gaussian covariance for miss distance d and
% hard-body radius R: max over sigma of P(|d + sigma*xi| <= R), xi ~ N(0,1)
if d <= R, pm = 1; return, end
Phi = @(x) 0.5*erfc(-x/sqrt(2));
f = @(ls) -(Phi((R - d)/exp(ls)) - Phi((-R - d)/exp(ls)));
ls = fminbnd(f, log(d) - 5, log(d) + 5, optimset('TolX', 1e-8));
pm = -f(ls);
end

function [lat, lon, alt] = subpoint(r, tca)
% geocentric sub-satellite point: ECEF = R3(GMST) ECI (IAU-82 GMST, as END-001's ephemeris)
d = days(tca - datetime(2000, 1, 1, 12, 0, 0, 'TimeZone', 'UTC'));
tut1 = d/36525;
g = mod(67310.54841 + (876600*3600 + 8640184.812866)*tut1 + 0.093104*tut1^2 - 6.2e-6*tut1^3, 86400)*2*pi/86400;
x = cos(g)*r(1) + sin(g)*r(2); y = -sin(g)*r(1) + cos(g)*r(2); z = r(3);
lat = atan2d(z, hypot(x, y)); lon = atan2d(y, x); alt = norm(r) - 6378.137;
end

function write_pair_matrix(file, labels, M)
fid = fopen(file, 'w');
fprintf(fid, 'satellite,%s\n', strjoin(labels, ','));
for i = 1:numel(labels)
    v = arrayfun(@(x) sprintf('%.4f', x), M(i, :), 'UniformOutput', false);
    v(isnan(M(i, :))) = {''};
    fprintf(fid, '%s,%s\n', labels{i}, strjoin(v, ','));
end
fclose(fid);
end

function write_events(file, ev)
fid = fopen(file, 'w');
fprintf(fid, 'pair,tca_utc,miss_km,radial_km,intrack_km,crosstrack_km,rel_speed_km_s,lat_deg,lon_deg,alt_km,pc,pc_upper_bound,pc_max\n');
for e = ev
    fprintf(fid, '%s,%s,%.6f,%.6f,%.6f,%.6f,%.6f,%.4f,%.4f,%.3f,%.6e,%.6e,%.6e\n', e.pair, e.tca_utc, e.miss_km, e.radial_km, ...
        e.intrack_km, e.crosstrack_km, e.rel_speed_km_s, e.lat_deg, e.lon_deg, e.alt_km, e.pc, e.pc_upper_bound, e.pc_max);
end
fclose(fid);
end

function write_life(file, life)
fid = fopen(file, 'w');
r = life(1).rules_years;
hdr = 'alt_km,incl_deg,f107,passive_lifetime_years,drag_makeup_dv_m_s_per_year';
for k = r, hdr = [hdr sprintf(',disposal_dv_m_s_%dy,disposal_perigee_km_%dy,complies_%dy', k, k, k)]; end %#ok<AGROW>
fprintf(fid, '%s\n', hdr);
for L = life
    fprintf(fid, '%.3f,%.3f,%g,%s,%.4f', L.alt_km, L.incl_deg, L.f107, years_str(L.passive_years), L.drag_dv_m_s_per_year);
    for k = 1:numel(r)
        fprintf(fid, ',%.2f,%.1f,%d', L.disposal_dv_m_s(k), L.disposal_perigee_km(k), L.passive_years <= r(k));
    end
    fprintf(fid, '\n');
end
fclose(fid);
end

function s = years_str(y)
if isinf(y), s = 'Inf'; else, s = sprintf('%.2f', y); end
end

function x = clean_json(x)
% jsonencode writes Inf/NaN as null: keep Inf readable as a string where it matters
if isstruct(x)
    for k = 1:numel(x)
        f = fieldnames(x(k));
        for m = 1:numel(f)
            x(k).(f{m}) = clean_json(x(k).(f{m}));
        end
    end
elseif isnumeric(x) && isscalar(x) && isinf(x)
    x = 'Inf';
end
end

function s = iso(t)
s = char(datetime(t, 'Format', 'yyyy-MM-dd''T''HH:mm:ss.SSS''Z'''));
end

function d = absdir(p, base)
p = char(p);
if isempty(regexp(p, '^([A-Za-z]:[\\/]|[\\/])', 'once')), d = fullfile(base, p); else, d = p; end
end

function v = getf(s, f, d)
if isstruct(s) && isfield(s, f) && ~isempty(s.(f)), v = s.(f); else, v = d; end
end

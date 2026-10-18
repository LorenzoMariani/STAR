function star_attitude_propagation_star(configFile, outputFolder)
%STAR_ATTITUDE_PROPAGATION_STAR  END-003 Attitude Propagation, version for STAR (2026-10-17).
%
%   star_attitude_propagation_star(configFile, outputFolder)
%
%   Same products as the legacy star_attitude_propagation.m (own orbit
%   propagation; moved to _old/ on 2026-10-17), made to run inside STAR:
%   - ORBIT: taken from END-001, not propagated. END-001 writes for every
%     satellite satellite_NN_ephemeris.csv (ECI position and velocity every
%     10 s, the frame where ECEF = R3(GMST) ECI, from the END-001 epoch). The
%     states between two rows come from a cubic Hermite interpolation with the
%     tabulated velocity (sub-metre). The satellites are therefore exactly the
%     ones END-001 designed and evaluated.
%   - PASSES: chosen by END-001 (pass_selection.json, 2026-10-17): the imaging
%     pass in daylight over the area of interest and the first night pass
%     visible from the observatory. END-003 computes the attitude on them.
%   - ATTITUDE on a 1 s grid: 'nadir' (+Z to nadir, +X along track, body rate
%     = orbital rate about the orbit normal), 'follow_site' (+Z to the target
%     while it is above the elevation threshold, nadir otherwise, slews limited
%     to sat.max_slew_rate_deg_s) and 'dynamics' (Euler equations + quaternion
%     kinematics with gravity-gradient, SRP and drag torques, free motion).
%   - OUTPUTS: the CSV of the imaging pass for END-007 / END-018 / END-004 and
%     of the light-curve pass for END-010 on a fixed step (integer seconds,
%     exact timestamps), selected_passes.json, the KPI catalog, the dashboard
%     data, the PNG figures, and the CCSDS AEM of both passes with the figures
%     that describe the attitude (end003_aem_figures.m reads the AEM).
%
%   Conventions: quaternions are Hamilton, body -> ECI (v_eci = R(q) v_body),
%   stored scalar-last [qx qy qz qw] (CSV columns q_w,q_x,q_y,q_z as before);
%   angular velocity in the body frame.

    set(0, 'DefaultFigureVisible', 'off');
    total_tic = tic;
    configFile = char(configFile);
    outputFolder = char(outputFolder);
    results_dir = fullfile(outputFolder, 'results_attitude_propagator');
    product_dir = fullfile(outputFolder, 'output_attitude_propagation');
    if ~exist(results_dir, 'dir'), mkdir(results_dir); end
    if ~exist(product_dir, 'dir'), mkdir(product_dir); end
    if ~isfile(configFile)
        error('STAR:END003:Config', 'Input JSON not found: %s', configFile);
    end
    cfg = jsondecode(fileread(configFile));
    S = read_settings(cfg);
    fprintf('--- END-003 (STAR version) attitude propagation, %s mode ---\n', S.mode);

    %% == ORBIT FROM END-001 ==================================================
    eph = read_end001_ephemerides(cfg);
    epoch = eph(1).epoch;
    T = eph(1).t(end);
    if isfield(cfg, 'sim_hours') && ~isempty(cfg.sim_hours) && cfg.sim_hours*3600 < T
        T = floor(cfg.sim_hours*3600/eph(1).h)*eph(1).h;
    end
    ctx.jd0 = juliandate(epoch);
    ctx.epoch = epoch;
    fprintf('Orbit: END-001 ephemerides of %d satellite(s), from %s UTC for %.1f h, %g s step (no orbit propagation in END-003).\n', ...
        numel(eph), char(string(epoch, 'yyyy-MM-dd HH:mm:ss')), T/3600, eph(1).h);

    %% == PASSES SELECTED BY END-001 ===========================================
    [plan, sites, S] = plan_from_end001(cfg, eph, S);

    %% == ATTITUDE (1 s grid) ==================================================
    tb = (0:S.base_step:T)';
    ki = plan.imaging.sat_pos;
    site = plan.imaging.site;
    fprintf('Attitude of %s on a %g s grid...\n', eph(ki).label, S.base_step);
    A_img = attitude_history(eph(ki), tb, S, ctx, site);
    A_lc = [];
    if plan.lightcurve.found
        if plan.lightcurve.sat_pos == ki
            A_lc = A_img;
        else
            fprintf('Attitude of %s (light-curve pass)...\n', eph(plan.lightcurve.sat_pos).label);
            A_lc = attitude_history(eph(plan.lightcurve.sat_pos), tb, S, ctx, site);
        end
    end

    %% == IMAGING PASS CSV (END-007, END-018, END-004) =========================
    step = S.sel.img.output_step_s;                   % rows on the END-001 grid (multiples of step from the epoch)
    t_img = (ceil(plan.imaging.aos_t/step)*step:step:floor(plan.imaging.los_t/step)*step)';
    if numel(t_img) < 2
        t_img = unique(min(max(round(plan.imaging.peak_t) + (-2:2)'*step, 0), T));
    end
    G_img = pass_geometry(A_img, t_img, S, ctx, site);
    write_pass_csvs(results_dir, product_dir, epoch, t_img, G_img);
    fprintf('Imaging pass CSV saved: %d samples every %g s (%s -> %s UTC).\n', numel(t_img), step, ...
        utc_str(epoch, t_img(1)), utc_str(epoch, t_img(end)));

    %% == AEM OF THE PASSES + ATTITUDE FIGURES =================================
    aem_step = S.sel.aem_step_s;
    aem = struct('key', {}, 'label', {}, 'file', {}, 'figures', {}, 'rotational_state', {});
    t_aem = (ceil(plan.imaging.aos_t):aem_step:floor(plan.imaging.los_t))';
    if numel(t_aem) < 2, t_aem = (t_img(1):aem_step:t_img(end))'; end
    aem(end+1) = make_aem_and_figures('imaging', sprintf('Imaging pass (END-007), %s over %s', eph(ki).label, site.name), ...
        eph(ki), A_img, t_aem, S, ctx, product_dir, results_dir, site);
    if plan.lightcurve.found
        k2 = plan.lightcurve.sat_pos;
        t_lc_aem = (plan.lightcurve.start_t_s:aem_step:plan.lightcurve.end_t_s)';
        obs = struct('name', plan.lightcurve.observer.name, 'lat', deg2rad(plan.lightcurve.observer.site_lat_deg), ...
            'lon', deg2rad(plan.lightcurve.observer.site_lon_deg), 'alt', plan.lightcurve.observer.site_alt_m);
        aem(end+1) = make_aem_and_figures('lightcurve', sprintf('Light-curve pass (END-010), %s seen from %s', eph(k2).label, obs.name), ...
            eph(k2), A_lc, t_lc_aem, S, ctx, product_dir, results_dir, obs);
    end

    %% == SELECTED PASSES (+ light-curve ephemeris for END-010) ================
    sel_info = export_selected_passes(product_dir, results_dir, plan, S, epoch, t_img, G_img, A_lc, eph, sites, aem);

    %% == FULL-SPAN SERIES (dashboard grid) ====================================
    td = (0:S.dash_step:T)';
    D = dashboard_series(A_img, td, S, ctx, site, eph(ki));
    fprintf('\n--- Mean disturbance torques [Nm] (%s, whole window) ---\n', eph(ki).label);
    fprintf('GG %.2e | SRP %.2e | Drag %.2e\n', mean(D.M(:,1)), mean(D.M(:,2)), mean(D.M(:,4)));

    %% == PLOTS (01-06) ========================================================
    make_standard_plots(results_dir, D, S, site);

    %% == DASHBOARD DATA =======================================================
    export_dashboard_data(results_dir, cfg, epoch, D, S, site, plan, t_img, aem);

    %% == KPI CATALOG ==========================================================
    export_kpis(results_dir, S, plan, D, G_img, sel_info, numel(eph));

    fprintf('\nEND-003 (STAR version) completed in %.1f s\n', toc(total_tic));
end

%% =========================================================================
%  SETTINGS
%  =========================================================================
function S = read_settings(cfg)
    sat = cfg_get(cfg, 'sat', struct());
    S.mode = lower(char(cfg_get(sat, 'attitude_mode', 'nadir')));
    if ~ismember(S.mode, {'nadir', 'follow_site', 'dynamics'})
        error('STAR:END003:AttitudeMode', 'attitude_mode "%s" is not supported (nadir, follow_site, dynamics).', S.mode);
    end
    q0 = cfg_get(sat, 'q0', [0 0 0 1]);
    S.q0 = q0(:)/norm(q0);                            % scalar last
    w0 = cfg_get(sat, 'w0', [0 0 0]);
    S.w0 = w0(:);
    S.m = cfg_get(sat, 'm', 4);
    S.A_ref = cfg_get(sat, 'A_ref', 0.03);
    S.Cr = cfg_get(sat, 'Cr', 1.2);
    S.Cd = cfg_get(sat, 'Cd', 2.2);
    r_cp = cfg_get(sat, 'r_cp', [0 0 0]);
    S.r_cp = r_cp(:);
    S.Ivec = [cfg_get(sat, 'Ix', 0.03); cfg_get(sat, 'Iy', 0.03); cfg_get(sat, 'Iz', 0.01)];
    S.I = diag(S.Ivec);
    S.invI = diag(1./S.Ivec);
    S.max_slew_rate = deg2rad(cfg_get(sat, 'max_slew_rate_deg_s', 3));
    env = cfg_get(cfg, 'env', struct());
    fl = cfg_get(env, 'flags', struct());
    S.flags.gg = logical(cfg_get(fl, 'gg', true));
    S.flags.srp = logical(cfg_get(fl, 'srp', true));
    S.flags.drag = logical(cfg_get(fl, 'drag', true));
    S.P_sun = 4.56e-6;
    S.mu = 3.986004415e14;
    S.Re = 6378137.0;                                 % WGS84, as END-001
    tg = cfg_get(cfg, 'target', struct());
    S.elev_threshold = cfg_get(tg, 'elev_threshold', 10);
    S.sun_enabled = logical(cfg_get(tg, 'Sun_Constraint', false));
    S.sun_mode = lower(char(cfg_get(tg, 'Sun_Constraint_Mode', 'day')));
    S.sun_thr = cfg_get(tg, 'Sun_Elevation_Threshold_Deg', 0);
    if S.sun_enabled && ~ismember(S.sun_mode, {'day', 'night'})
        error('STAR:END003:SunMode', 'Sun_Constraint_Mode must be "day" or "night".');
    end
    S.sel = read_pass_selection_config(cfg);
    S.base_step = 1;                                  % s, attitude grid
    S.dash_step = 60;                                 % s, dashboard / whole-window plots
    S.dims = equivalent_box(S.m, S.Ivec);
end

function sel = read_pass_selection_config(cfg)
    sel.img.preferred_sun_elevation_deg = 20;
    sel.img.output_step_s = 10;
    sel.aem_step_s = 1;
    sel.lc.enabled = true;
    sel.lc.name = 'Matera';
    sel.lc.lat_deg = 40.6492;
    sel.lc.lon_deg = 16.7039;
    sel.lc.alt_m = 400;
    sel.lc.elev_threshold_deg = 10;
    sel.lc.elev_margin_deg = 1;
    sel.lc.sun_elev_max_deg = -12;
    sel.lc.require_sunlit = true;
    sel.lc.min_duration_s = 120;
    sel.lc.output_step_s = 10;
    sel.lc.edge_margin_s = 10;

    ps = cfg_get(cfg, 'pass_selection', struct());
    img = cfg_get(ps, 'imaging', struct());
    sel.img.preferred_sun_elevation_deg = cfg_get(img, 'preferred_sun_elevation_deg', sel.img.preferred_sun_elevation_deg);
    sel.img.output_step_s = max(1, round(cfg_get(img, 'output_step_s', sel.img.output_step_s)));
    sel.aem_step_s = max(1, round(cfg_get(ps, 'aem_step_s', sel.aem_step_s)));
    lc = cfg_get(ps, 'lightcurve', struct());
    ob = cfg_get(lc, 'observer', struct());
    sel.lc.enabled = logical(cfg_get(lc, 'enabled', sel.lc.enabled));
    sel.lc.name = char(cfg_get(ob, 'name', sel.lc.name));
    sel.lc.lat_deg = cfg_get(ob, 'site_lat_deg', sel.lc.lat_deg);
    sel.lc.lon_deg = cfg_get(ob, 'site_lon_deg', sel.lc.lon_deg);
    sel.lc.alt_m = cfg_get(ob, 'site_alt_m', sel.lc.alt_m);
    sel.lc.elev_threshold_deg = cfg_get(lc, 'elev_threshold_deg', sel.lc.elev_threshold_deg);
    sel.lc.elev_margin_deg = cfg_get(lc, 'elev_margin_deg', sel.lc.elev_margin_deg);
    sel.lc.sun_elev_max_deg = cfg_get(lc, 'observer_sun_elevation_max_deg', sel.lc.sun_elev_max_deg);
    sel.lc.require_sunlit = logical(cfg_get(lc, 'require_satellite_sunlit', sel.lc.require_sunlit));
    sel.lc.min_duration_s = cfg_get(lc, 'min_duration_s', sel.lc.min_duration_s);
    sel.lc.output_step_s = max(1, round(cfg_get(lc, 'output_step_s', sel.lc.output_step_s)));
    sel.lc.edge_margin_s = cfg_get(lc, 'edge_margin_s', sel.lc.edge_margin_s);
end

function v = cfg_get(s, name, default)
    % CFG_GET  Field of a jsondecode struct, or the default when absent/empty.
    if isstruct(s) && isfield(s, name) && ~isempty(s.(name))
        v = s.(name);
    else
        v = default;
    end
end

function d = equivalent_box(m, Ivec)
    % Sides [x y z] (m) of the uniform box with mass m and principal inertia Ivec
    % (drawing of the attitude figures); 3U if the inertia is not a box.
    a2 = 6*(Ivec(2) + Ivec(3) - Ivec(1))/m;
    b2 = 6*(Ivec(1) + Ivec(3) - Ivec(2))/m;
    c2 = 6*(Ivec(1) + Ivec(2) - Ivec(3))/m;
    if all([a2 b2 c2] > 0)
        d = sqrt([a2 b2 c2]);
    else
        d = [0.1 0.1 0.34];
    end
end

%% =========================================================================
%  END-001 EPHEMERIDES
%  =========================================================================
function eph = read_end001_ephemerides(cfg)
    if ~isfield(cfg, 'end001_ephemeris') || isempty(cfg.end001_ephemeris)
        error('STAR:END003:NoEphemeris', ['END-003 (STAR version) needs the END-001 ephemerides ', ...
            '(satellite_NN_ephemeris.csv): run END-001 in the same workflow first.']);
    end
    items = cfg.end001_ephemeris;
    if ~iscell(items), items = num2cell(items(:)); end
    orbits = struct('index', {}, 'orbit', {});
    if isfield(cfg, 'constellation') && ~isempty(cfg.constellation)
        c = cfg.constellation;
        if ~iscell(c), c = num2cell(c(:)); end
        for k = 1:numel(c)
            o = c{k};
            orbits(end+1).index = cfg_get(o, 'satellite_index', k); %#ok<AGROW>
            orbits(end).orbit = struct('alt_perigee_m', o.alt_perigee_m, 'alt_apogee_m', o.alt_apogee_m, ...
                'inclination_deg', o.inclination_deg, 'raan_deg', o.raan_deg, 'omega_deg', o.omega_deg, 'nu_deg', o.nu_deg);
        end
    end
    tmpl = struct('index', 0, 'label', '', 'file', '', 'epoch', NaT, 't', [], 'h', 10, 'r', [], 'v', [], 'orbit', struct());
    eph = repmat(tmpl, numel(items), 1);
    for k = 1:numel(items)
        it = items{k};
        f = char(it.file);
        if ~isfile(f)
            error('STAR:END003:NoEphemeris', 'END-001 ephemeris not found: %s', f);
        end
        opts = detectImportOptions(f, 'Delimiter', ',', 'FileType', 'text');
        opts = setvartype(opts, 'time_utc', 'string');
        Tb = readtable(f, opts);
        ts = parse_utc(Tb.time_utc);
        t = seconds(ts - ts(1));
        dtk = diff(t);
        h = median(dtk);
        if any(abs(dtk - h) > 1e-3)
            error('STAR:END003:Ephemeris', 'Non-uniform time step in %s', f);
        end
        eph(k).index = cfg_get(it, 'satellite_index', k);
        eph(k).label = sprintf('SAT-%02d', eph(k).index);
        eph(k).file = f;
        eph(k).epoch = ts(1);
        eph(k).t = t;
        eph(k).h = h;
        eph(k).r = [Tb.x_eci_km, Tb.y_eci_km, Tb.z_eci_km]*1e3;
        eph(k).v = [Tb.vx_eci_km_s, Tb.vy_eci_km_s, Tb.vz_eci_km_s]*1e3;
        j = find([orbits.index] == eph(k).index, 1);
        if ~isempty(j), eph(k).orbit = orbits(j).orbit; end
    end
    for k = 2:numel(eph)
        if eph(k).epoch ~= eph(1).epoch || numel(eph(k).t) ~= numel(eph(1).t) || eph(k).h ~= eph(1).h
            error('STAR:END003:Ephemeris', 'The END-001 ephemerides do not share the same time grid (%s).', eph(k).file);
        end
    end
end

function ts = parse_utc(s)
    s = replace(erase(string(s), "Z"), "T", " ");
    frac = contains(s, ".");
    ts = NaT(numel(s), 1);
    if any(~frac), ts(~frac) = datetime(s(~frac), 'InputFormat', 'yyyy-MM-dd HH:mm:ss'); end
    if any(frac), ts(frac) = datetime(s(frac), 'InputFormat', 'yyyy-MM-dd HH:mm:ss.SSS'); end
end

function [r, v] = eph_eval(E, t)
    % Cubic Hermite interpolation of the END-001 ephemeris (positions and
    % tabulated velocities), uniform grid. r [m], v [m/s], rows = times.
    t = t(:);
    h = E.h;
    nn = size(E.r, 1);
    s = (t - E.t(1))/h;
    i0 = min(max(floor(s), 0), nn - 2);
    u = s - i0;
    a = i0 + 1; b = i0 + 2;
    p0 = E.r(a, :); p1 = E.r(b, :); m0 = E.v(a, :)*h; m1 = E.v(b, :)*h;
    u2 = u.^2; u3 = u2.*u;
    r = (2*u3 - 3*u2 + 1).*p0 + (u3 - 2*u2 + u).*m0 + (-2*u3 + 3*u2).*p1 + (u3 - u2).*m1;
    if nargout > 1
        v = ((6*u2 - 6*u).*p0 + (3*u2 - 4*u + 1).*m0 + (-6*u2 + 6*u).*p1 + (3*u2 - 2*u).*m1)/h;
    end
end

%% =========================================================================
%  FRAMES, SUN, SITES
%  =========================================================================
function th = gmst_rad(jd)
    % GMST (IAU-82, UT1 ~ UTC), as END-001 (export_downstream_ephemeris) and END-007.
    th = deg2rad(mod(280.46061837 + 360.98564736629*(jd(:) - 2451545.0), 360));
end

function x = rot_eci2ecef(x, th)
    c = cos(th); s = sin(th);
    x = [c.*x(:,1) + s.*x(:,2), -s.*x(:,1) + c.*x(:,2), x(:,3)];
end

function x = rot_ecef2eci(x, th)
    c = cos(th); s = sin(th);
    x = [c.*x(:,1) - s.*x(:,2), s.*x(:,1) + c.*x(:,2), x(:,3)];
end

function [p, up] = geodetic_ecef(lat, lon, alt)
    % WGS84 position [m] and geodetic vertical of ground points (lat, lon in rad).
    a = 6378137.0; f = 1/298.257223563; e2 = f*(2 - f);
    lat = lat(:); lon = lon(:); alt = alt(:);
    N = a./sqrt(1 - e2*sin(lat).^2);
    p = [(N + alt).*cos(lat).*cos(lon), (N + alt).*cos(lat).*sin(lon), (N*(1 - e2) + alt).*sin(lat)];
    up = [cos(lat).*cos(lon), cos(lat).*sin(lon), sin(lat)];
end

function S = sun_vectors_eci(jd)
    % Low-precision solar ephemeris (Almanac, ~0.01 deg), unit vectors n x 3.
    n = jd(:) - 2451545.0;
    L = mod(280.460 + 0.9856474*n, 360);
    g = mod(357.528 + 0.9856003*n, 360);
    lam = L + 1.915*sind(g) + 0.020*sind(2*g);
    ecl = 23.439 - 0.0000004*n;
    S = [cosd(lam), sind(lam).*cosd(ecl), sind(lam).*sind(ecl)];
end

function lit = sunlit_flags(r, Sun, Re)
    rm = vecnorm(r, 2, 2);
    lit = ~(sum(Sun.*r, 2)./rm < -sqrt(1 - (Re./rm).^2));     % cylindrical shadow
end

function el = elevation_deg(r_ecef, p, up)
    rho = r_ecef - p;
    el = asind(sum(rho.*up, 2)./vecnorm(rho, 2, 2));
end

function [s_idx, e_idx] = find_runs(mask)
    d = diff([0; mask(:); 0]);
    s_idx = find(d == 1);
    e_idx = find(d == -1) - 1;
end

function [plan, sites, S] = plan_from_end001(cfg, eph, S)
    % Passes chosen by END-001 (pass_selection.json): the imaging pass over the
    % AOI and the first night pass from the observatory, in the struct the rest
    % of END-003 uses. The selection thresholds of END-001 replace the template ones.
    f = char(cfg_get(cfg, 'end001_pass_selection', ''));
    if isempty(f) || ~isfile(f)
        error('STAR:END003:NoPassSelection', ['END-003 (STAR version) needs the passes selected by END-001 ', ...
            '(pass_selection.json next to the END-001 ephemerides): run END-001 in the same workflow first.']);
    end
    P = jsondecode(fileread(f));
    idx = [eph.index];
    st = P.settings;
    S.elev_threshold = st.img.elev;
    S.sun_enabled = logical(st.img.sun_enabled);
    S.sun_mode = char(st.img.sun_mode);
    S.sun_thr = st.img.sun_thr;
    plan.n_satellites = numel(eph);
    plan.source_file = f;

    im = P.imaging_pass;
    k = find(idx == im.satellite_index, 1);
    if isempty(k)
        error('STAR:END003:PassSelection', 'Satellite %d of pass_selection.json has no END-001 ephemeris.', im.satellite_index);
    end
    plan.candidates = struct('sat', {}, 'site_name', {}, 'aos_t', {}, 'los_t', {}, 'peak_t', {}, 'peak_el', {}, 'sun_el_peak', {}, ...
        'sun_el_min', {}, 'sun_el_sub_min', {}, 'sunlit_frac', {}, 'ok', {}, 'truncated', {}, 'selected', {});
    C = P.imaging_candidates;
    if iscell(C), C = [C{:}]; end
    for i = 1:numel(C)
        plan.candidates(i) = struct('sat', find(idx == C(i).satellite_index, 1), 'site_name', C(i).site, 'aos_t', C(i).aos_t_s, ...
            'los_t', C(i).los_t_s, 'peak_t', C(i).peak_t_s, 'peak_el', C(i).peak_elevation_deg, ...
            'sun_el_peak', C(i).site_sun_elevation_at_peak_deg, 'sun_el_min', C(i).site_sun_elevation_min_deg, ...
            'sun_el_sub_min', C(i).subsatellite_sun_elevation_min_deg, 'sunlit_frac', C(i).satellite_sunlit_fraction, ...
            'ok', logical(C(i).sun_constraint_ok), 'truncated', logical(C(i).truncated_by_window), 'selected', logical(C(i).selected));
    end
    c = struct('sat', k, 'site_name', im.site.name, 'aos_t', im.start_t_s, 'los_t', im.end_t_s, 'peak_t', im.peak_t_s, ...
        'peak_el', im.peak_elevation_deg, 'sun_el_peak', im.site_sun_elevation_at_peak_deg, 'sun_el_min', im.site_sun_elevation_min_deg, ...
        'sun_el_sub_min', im.subsatellite_sun_elevation_min_deg, 'sunlit_frac', im.satellite_sunlit_fraction, ...
        'ok', logical(im.constraint_met), 'truncated', false, 'selected', true);
    plan.imaging.pass_found = logical(im.pass_found);
    plan.imaging.constraint_met = logical(im.constraint_met);
    plan.imaging.found = true;
    plan.imaging.cand = c;
    plan.imaging.sat_pos = k;
    plan.imaging.sat_index = eph(k).index;
    plan.imaging.label = eph(k).label;
    plan.imaging.orbit_cfg = eph(k).orbit;
    plan.imaging.aos_t = im.start_t_s;
    plan.imaging.los_t = im.end_t_s;
    plan.imaging.peak_t = im.peak_t_s;
    plan.imaging.site = struct('name', im.site.name, 'lat', deg2rad(im.site.lat_deg), 'lon', deg2rad(im.site.lon_deg), ...
        'alt', im.site.alt_m, 'index', im.site.index);
    sites = struct('source', 'END-001 pass_selection.json', 'description', im.target.description, 'n_points', im.target.n_points);
    fprintf('Passes from END-001 (%s): imaging %s over %s, %s -> %s\n', f, eph(k).label, im.site.name, im.start_utc, im.end_utc);

    L = P.lightcurve_pass;
    plan.lightcurve = struct('found', false, 'enabled', logical(L.enabled), 'rule', char(cfg_get(L, 'rule', 'first useful pass')));
    plan.lightcurve.observer = L.observer;
    plan.lightcurve.n_windows = cfg_get(L, 'n_windows', 0);
    plan.lightcurve.observer_sun_elevation_max_deg = cfg_get(L, 'observer_sun_elevation_max_deg', NaN);
    plan.lightcurve.observer_sun_elevation_used_deg = cfg_get(L, 'observer_sun_elevation_used_deg', NaN);
    if logical(L.found)
        k2 = find(idx == L.satellite_index, 1);
        so = S.sel.lc.output_step_s;                  % rows on the END-001 grid (multiples of the step)
        t_out = (ceil(L.start_t_s/so)*so:so:floor(L.end_t_s/so)*so)';
        if numel(t_out) < 2, t_out = (L.start_t_s:so:L.end_t_s)'; end
        lc = plan.lightcurve;
        lc.found = true;
        lc.sat_pos = k2;
        lc.sat_index = eph(k2).index;
        lc.label = eph(k2).label;
        lc.orbit_cfg = eph(k2).orbit;
        lc.start_t_s = t_out(1);
        lc.end_t_s = t_out(end);
        lc.t_out = t_out;
        lc.peak_t_s = L.peak_t_s;
        lc.peak_el = L.peak_elevation_deg;
        lc.sun_el_obs_at_peak = L.observer_sun_elevation_at_peak_deg;
        lc.min_range_km = L.min_range_km;
        lc.sunlit_fraction = L.satellite_sunlit_fraction;
        plan.lightcurve = lc;
        fprintf('Passes from END-001: light curve (%s) %s from %s, %s -> %s\n', lc.rule, lc.label, L.observer.name, L.start_utc, L.end_utc);
    end
end

%% =========================================================================
%  ATTITUDE
%  =========================================================================
function A = attitude_history(E, tb, S, ctx, site)
    [r, v] = eph_eval(E, tb);
    n = numel(tb);
    A.t = tb; A.r = r; A.v = v; A.qnorm_drift = zeros(n, 1);
    switch S.mode
        case 'nadir'
            [xb, yb, zb] = nadir_axes(r, v);
            A.q = continuous_sign(axes2quat(xb, yb, zb));
            w_eci = cross(r, v, 2)./sum(r.^2, 2);      % rate of the orbital frame
            A.w = [sum(xb.*w_eci, 2), sum(yb.*w_eci, 2), sum(zb.*w_eci, 2)];
        case 'follow_site'
            th = gmst_rad(ctx.jd0 + tb/86400);
            [p, up] = geodetic_ecef(site.lat, site.lon, site.alt);
            p_eci = rot_ecef2eci(repmat(p, n, 1), th);
            el = elevation_deg(rot_eci2ecef(r, th), p, up);
            zb = -r./vecnorm(r, 2, 2);
            vis = el > S.elev_threshold;
            los = p_eci(vis, :) - r(vis, :);
            zb(vis, :) = los./vecnorm(los, 2, 2);
            xb = v - sum(v.*zb, 2).*zb; xb = xb./vecnorm(xb, 2, 2);
            yb = cross(zb, xb, 2); yb = yb./vecnorm(yb, 2, 2);
            xb = cross(yb, zb, 2);
            q_cmd = continuous_sign(axes2quat(xb, yb, zb));
            q = q_cmd;
            dt = tb(2) - tb(1);
            max_step = S.max_slew_rate*dt;
            for i = 2:n                                 % rate-limited tracking (slews)
                qp = q(i-1, :); qc = q_cmd(i, :);
                d = qp*qc';
                if d < 0, qc = -qc; d = -d; end
                ang = 2*acos(min(1, d));
                if ang > max_step
                    q(i, :) = slerp_q(qp, qc, max_step/ang);
                else
                    q(i, :) = qc;
                end
            end
            A.q = q;
            A.w = body_rate_from_quat(q, dt);
        case 'dynamics'
            rho_t = (0:60:tb(end))';
            if S.flags.drag
                rho = density_table(E, rho_t, ctx);
            else
                rho = zeros(size(rho_t));
            end
            opts = odeset('RelTol', 1e-10, 'AbsTol', 1e-12);
            f = @(t, y) attitude_rhs(t, y, S, E, ctx, rho_t, rho);
            [~, Y] = ode113(f, tb, [S.q0; S.w0], opts);
            qn = vecnorm(Y(:, 1:4), 2, 2);
            A.qnorm_drift = abs(qn - 1);
            A.q = continuous_sign(Y(:, 1:4)./qn);
            A.w = Y(:, 5:7);
    end
end

function [xb, yb, zb] = nadir_axes(r, v)
    zb = -r./vecnorm(r, 2, 2);
    xb = v - sum(v.*zb, 2).*zb; xb = xb./vecnorm(xb, 2, 2);
    yb = cross(zb, xb, 2); yb = yb./vecnorm(yb, 2, 2);
    xb = cross(yb, zb, 2);
end

function q = axes2quat(xb, yb, zb)
    % Quaternion [qx qy qz qw] of R = [xb yb zb] (columns: body axes in ECI).
    R11 = xb(:,1); R21 = xb(:,2); R31 = xb(:,3);
    R12 = yb(:,1); R22 = yb(:,2); R32 = yb(:,3);
    R13 = zb(:,1); R23 = zb(:,2); R33 = zb(:,3);
    d = [1 + R11 + R22 + R33, 1 + R11 - R22 - R33, 1 - R11 + R22 - R33, 1 - R11 - R22 + R33];
    [~, m] = max(d, [], 2);
    q = zeros(size(xb, 1), 4);
    i = m == 1; f = 2*sqrt(d(i,1));
    q(i,:) = [(R32(i) - R23(i))./f, (R13(i) - R31(i))./f, (R21(i) - R12(i))./f, f/4];
    i = m == 2; f = 2*sqrt(d(i,2));
    q(i,:) = [f/4, (R12(i) + R21(i))./f, (R13(i) + R31(i))./f, (R32(i) - R23(i))./f];
    i = m == 3; f = 2*sqrt(d(i,3));
    q(i,:) = [(R12(i) + R21(i))./f, f/4, (R23(i) + R32(i))./f, (R13(i) - R31(i))./f];
    i = m == 4; f = 2*sqrt(d(i,4));
    q(i,:) = [(R13(i) + R31(i))./f, (R23(i) + R32(i))./f, f/4, (R21(i) - R12(i))./f];
    q = q./vecnorm(q, 2, 2);
end

function q = continuous_sign(q)
    s = sign(sum(q(2:end, :).*q(1:end-1, :), 2));
    s(s == 0) = 1;
    q = q.*cumprod([1; s]);
end

function q = slerp_q(a, b, f)
    d = min(1, max(-1, a*b'));
    om = acos(d);
    if om < 1e-9
        q = a;
    else
        q = (sin((1 - f)*om)*a + sin(f*om)*b)/sin(om);
    end
    q = q/norm(q);
end

function w = body_rate_from_quat(q, dt)
    % omega_body = 2 vec(conj(q) x qdot), q scalar last, central differences.
    qd = zeros(size(q));
    qd(2:end-1, :) = (q(3:end, :) - q(1:end-2, :))/(2*dt);
    qd(1, :) = (q(2, :) - q(1, :))/dt;
    qd(end, :) = (q(end, :) - q(end-1, :))/dt;
    qv = q(:, 1:3); qw = q(:, 4);
    w = 2*(qw.*qd(:, 1:3) - qd(:, 4).*qv - cross(qv, qd(:, 1:3), 2));
end

function v2 = quat_rotate(q, v)
    % v2 = R(q) v (body -> ECI) row-wise, q scalar last.
    qv = q(:, 1:3); qw = q(:, 4);
    if size(v, 1) == 1, v = repmat(v, size(q, 1), 1); end
    t = 2*cross(qv, v, 2);
    v2 = v + qw.*t + cross(qv, t, 2);
end

function A = qdcm(q)
    % Rotation matrix body -> ECI of one quaternion [qx qy qz qw].
    q = q/norm(q); x = q(1); y = q(2); z = q(3); w = q(4);
    A = [1-2*(y^2+z^2) 2*(x*y-z*w) 2*(x*z+y*w); 2*(x*y+z*w) 1-2*(x^2+z^2) 2*(y*z-x*w); 2*(x*z-y*w) 2*(y*z+x*w) 1-2*(x^2+y^2)];
end

function dY = attitude_rhs(t, Y, S, E, ctx, rho_t, rho)
    q = Y(1:4)/norm(Y(1:4)); w = Y(5:7);
    [r, v] = eph_eval(E, t);
    Sun = sun_vectors_eci(ctx.jd0 + t/86400);
    rhot = interp_lin(rho_t, rho, t);
    M = disturbance_torques(r(:), v(:), qdcm(q'), Sun(:), rhot, S);
    dw = S.invI*(M(:,1) + M(:,2) + M(:,4) - cross(w, S.I*w));
    dq = 0.5*[q(4)*w + cross(q(1:3), w); -dot(q(1:3), w)];
    dY = [dq; dw];
end

function y = interp_lin(x, v, t)
    h = x(2) - x(1);
    i = min(max(floor((t - x(1))/h) + 1, 1), numel(x) - 1);
    u = (t - x(i))/h;
    y = v(i)*(1 - u) + v(i + 1)*u;
end

function M = disturbance_torques(r, v, A, Sun, rho, S)
    % Columns: gravity gradient, SRP, (magnetic: not modelled), drag, 0, 0.
    M = zeros(3, 6);
    rm = norm(r);
    if S.flags.gg
        rb = A'*r;
        M(:, 1) = 3*S.mu/rm^5*cross(rb, S.I*rb);
    end
    if S.flags.srp && dot(Sun, r/rm) >= -sqrt(1 - (S.Re/rm)^2)
        M(:, 2) = cross(S.r_cp, -S.P_sun*S.A_ref*S.Cr*(A'*Sun));
    end
    if S.flags.drag && rho > 0
        v_rel = A'*(v - cross([0; 0; 7.2921150e-5], r));
        M(:, 4) = cross(S.r_cp, -0.5*rho*S.Cd*S.A_ref*norm(v_rel)*v_rel);
    end
end

function rho = density_table(E, t, ctx)
    % NRLMSISE-00 total density on the given times (F10.7 = 150, Ap = 15),
    % faded to zero between 700 and 1000 km as in the original END-003.
    [r, ~] = eph_eval(E, t);
    th = gmst_rad(ctx.jd0 + t/86400);
    lla = ecef2lla(rot_eci2ecef(r, th));
    alt = lla(:, 3);
    rho = zeros(size(t));
    ok = alt < 1000e3;
    if any(ok)
        ts = ctx.epoch + seconds(t(ok));
        [~, d] = atmosnrlmsise00(alt(ok), lla(ok, 1), lla(ok, 2), year(ts), day(ts, 'dayofyear'), ...
            seconds(timeofday(ts)), 150*ones(nnz(ok), 1), 150*ones(nnz(ok), 1), 15*ones(nnz(ok), 7));
        fade = ones(nnz(ok), 1);
        hi = alt(ok) > 700e3;
        a2 = alt(ok);
        fade(hi) = 0.5*(1 + cos(pi*(a2(hi) - 700e3)/(1000e3 - 700e3)));
        rho(ok) = d(:, 6).*fade;
    end
end

%% =========================================================================
%  PASS GEOMETRY AND CSV EXPORTS
%  =========================================================================
function G = pass_geometry(A, t, S, ctx, site)
    idx = round(t/S.base_step) + 1;
    G.t = t;
    G.r = A.r(idx, :); G.v = A.v(idx, :); G.q = A.q(idx, :); G.w = A.w(idx, :);
    th = gmst_rad(ctx.jd0 + t/86400);
    [p, up] = geodetic_ecef(site.lat, site.lon, site.alt);
    G.el = elevation_deg(rot_eci2ecef(G.r, th), p, up);
    p_eci = rot_ecef2eci(repmat(p, numel(t), 1), th);
    zb = quat_rotate(G.q, [0 0 1]);
    G.offset = angle_deg(zb, -G.r);
    G.target_offset = angle_deg(zb, p_eci - G.r);
    Sun = sun_vectors_eci(ctx.jd0 + t/86400);
    G.sun_site = asind(rot_eci2ecef(Sun, th)*up');
    G.sunlit = sunlit_flags(G.r, Sun, S.Re);
end

function a = angle_deg(u, v)
    a = atan2d(vecnorm(cross(u, v, 2), 2, 2), sum(u.*v, 2));
    a(a < 1e-10) = 0;
end

function s = utc_str(epoch, t)
    s = char(string(epoch + seconds(t), 'yyyy-MM-dd''T''HH:mm:ss''Z'''));
end

function write_pass_csvs(results_dir, product_dir, epoch, t, G)
    header = 'timestamp_utc,eci_x_km,eci_y_km,eci_z_km,q_w,q_x,q_y,q_z,nadir_offset_deg\n';
    fid_eci = fopen(fullfile(results_dir, 'output_attitude_propagation_ECI.csv'), 'w');
    fid_unity = fopen(fullfile(results_dir, 'output_attitude_propagation_Unity.csv'), 'w');
    fid_unreal = fopen(fullfile(product_dir, 'output_attitude_propagation.csv'), 'w');
    if any([fid_eci fid_unity fid_unreal] < 0)
        error('STAR:END003:Output', 'Unable to write the pass CSV files.');
    end
    fprintf(fid_eci, header); fprintf(fid_unity, header); fprintf(fid_unreal, header);
    fmt = '%s,%.3f,%.3f,%.3f,%.4f,%.4f,%.4f,%.4f,%.2f\n';
    for k = 1:numel(t)
        ts = utc_str(epoch, t(k));
        r = G.r(k, :)/1000;
        qx = G.q(k, 1); qy = G.q(k, 2); qz = G.q(k, 3); qw = G.q(k, 4);
        % 1. ECI (right-handed), quaternion body -> ECI
        fprintf(fid_eci, fmt, ts, r(1), r(2), r(3), qw, qx, qy, qz, G.offset(k));
        % 2. Unity (left-handed, Y up): X->X, Y->Z, Z->Y, quaternion (w, -x, -z, -y)
        fprintf(fid_unity, fmt, ts, r(1), r(3), r(2), qw, -qx, -qz, -qy, G.offset(k));
        % 3. Unreal / END-007 (EarthSim): ECI position unchanged, conjugate
        %    quaternion (validated by the END-007 renders, see _old/star_attitude_propagation.m)
        fprintf(fid_unreal, fmt, ts, r(1), r(2), r(3), qw, -qx, -qy, -qz, G.offset(k));
    end
    fclose(fid_eci); fclose(fid_unity); fclose(fid_unreal);
end

%% =========================================================================
%  AEM (CCSDS ADM, S5Lab BILAR layout) + ATTITUDE FIGURES
%  =========================================================================
function a = make_aem_and_figures(key, label, E, A, t, S, ctx, product_dir, results_dir, site)
    idx = round(t/S.base_step) + 1;
    t0 = ctx.epoch + seconds(t(1));
    name = sprintf('AEM_END003_%s_%s_%s.xml', strrep(E.label, '-', ''), key, char(string(t0, 'yyyyMMdd''T''HHmmss')));
    file = fullfile(product_dir, name);
    % AEM in J2000: STAR frame (ECEF = R3(GMST) x) -> J2000 with the IAU-76
    % precession at the middle of the pass (constant over a pass to 1e-8 rad)
    M = to_j2000(ctx.jd0 + mean(t([1 end]))/86400);
    write_aem(file, E.label, sprintf('STAR-%s', E.label), ctx.epoch, t, rotate_quat(M, A.q(idx, :)), A.w(idx, :), S.mode, label);
    fprintf('AEM saved: %s (%d states, %g s step)\n', name, numel(t), t(2) - t(1));
    opts = struct();
    opts.out_dir = results_dir;
    opts.prefix = ['07_aem_' key];
    opts.title = label;
    opts.I = S.I;
    opts.dims = S.dims;
    opts.mode = S.mode;
    opts.orbit_rv = @(ts) rv_j2000(E, seconds(ts - ctx.epoch), M);   % ts: datetime UTC, J2000
    opts.frame_rot = M;                                               % STAR frame -> J2000 (ground point)
    opts.gmst = @(ts) gmst_rad(juliandate(ts));
    opts.site = site;
    opts.site_role = ternary(strcmp(key, 'imaging'), 'target site', 'observer');
    info = end003_aem_figures(file, opts);
    a = struct('key', key, 'label', label, 'file', name, 'figures', info.figures, 'rotational_state', info.rotational_state);
end

function write_aem(file, obj_name, obj_id, epoch, t, q, w, mode, label)
    fid = fopen(file, 'w');
    if fid < 0, error('STAR:END003:Output', 'Unable to write %s', file); end
    tf = @(s) char(string(epoch + seconds(s), 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS'));
    fprintf(fid, '<?xml version="1.0" encoding="utf-8"?>\n');
    fprintf(fid, ['<aem xmlns:ndm="urn:ccsds:schema:ndmxml"\n     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"\n', ...
        '     id="CCSDS_AEM_VERS"\n     version="2.0"\n', ...
        '     xsi:noNamespaceSchemaLocation="https://sanaregistry.org/r/ndmxml_unqualified/ndmxml-4.0.0-master-4.0.xsd">\n']);
    fprintf(fid, '   <header>\n');
    fprintf(fid, '      <COMMENT>The format of this NDM/XML is reported in ADM CCSDS 504.0-B-2 documentation</COMMENT>\n');
    fprintf(fid, '      <CREATION_DATE>%s</CREATION_DATE>\n', char(string(datetime('now', 'TimeZone', 'UTC'), 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS')));
    fprintf(fid, '      <ORIGINATOR>S5LAB</ORIGINATOR>\n');
    fprintf(fid, '      <MESSAGE_ID>STAR-END003</MESSAGE_ID>\n');
    fprintf(fid, '   </header>\n   <body>\n      <segment>\n         <metadata>\n');
    fprintf(fid, '            <COMMENT>Attitude of spacecraft body frame relative to inertial frame.</COMMENT>\n');
    fprintf(fid, '            <COMMENT>%s; STAR END-003 attitude mode: %s; orbit: END-001 ephemeris.</COMMENT>\n', xml_escape(label), mode);
    fprintf(fid, ['            <COMMENT>J2000: STAR inertial frame (ECEF = R3(GMST) x inertial, the frame of the END-001 ephemerides) ', ...
        'rotated with the IAU-76 precession; nutation (&lt; 0.005 deg) neglected.</COMMENT>\n']);
    fprintf(fid, '            <OBJECT_NAME>%s</OBJECT_NAME>\n', xml_escape(obj_name));
    fprintf(fid, '            <OBJECT_ID>%s</OBJECT_ID>\n', xml_escape(obj_id));
    fprintf(fid, '            <REF_FRAME_A>J2000</REF_FRAME_A>\n            <REF_FRAME_B>SC_BODY</REF_FRAME_B>\n');
    fprintf(fid, '            <TIME_SYSTEM>UTC</TIME_SYSTEM>\n');
    fprintf(fid, '            <START_TIME>%s</START_TIME>\n            <STOP_TIME>%s</STOP_TIME>\n', tf(t(1)), tf(t(end)));
    fprintf(fid, '            <ATTITUDE_TYPE>QUATERNION/ANGVEL</ATTITUDE_TYPE>\n         </metadata>\n         <data>\n');
    fprintf(fid, ['            <COMMENT>Quaternion components are Q1, Q2, Q3, QC (scalar last): rotation body -&gt; J2000 ', ...
        '(frame transformation J2000 -&gt; body). ANGVEL: body frame, rad/s.</COMMENT>\n']);
    for i = 1:numel(t)
        fprintf(fid, ['            <attitudeState>\n               <quaternionAngVel>\n                  <EPOCH>%s</EPOCH>\n', ...
            '                  <quaternion>\n                     <Q1>%.7f</Q1>\n                     <Q2>%.7f</Q2>\n', ...
            '                     <Q3>%.7f</Q3>\n                     <QC>%.7f</QC>\n                  </quaternion>\n', ...
            '                  <angVel>\n                     <ANGVEL_X>%.9f</ANGVEL_X>\n                     <ANGVEL_Y>%.9f</ANGVEL_Y>\n', ...
            '                     <ANGVEL_Z>%.9f</ANGVEL_Z>\n                  </angVel>\n               </quaternionAngVel>\n', ...
            '            </attitudeState>\n'], tf(t(i)), q(i, 1), q(i, 2), q(i, 3), q(i, 4), w(i, 1), w(i, 2), w(i, 3));
    end
    fprintf(fid, '         </data>\n      </segment>\n   </body>\n</aem>\n');
    fclose(fid);
end

function M = to_j2000(jd)
    % Rotation STAR frame (mean of date, ECEF = R3(GMST) x) -> J2000:
    % transpose of the IAU-76 precession matrix J2000 -> mean of date.
    T = (jd - 2451545.0)/36525; as = pi/180/3600;
    zeta = (2306.2181*T + 0.30188*T^2 + 0.017998*T^3)*as;
    th = (2004.3109*T - 0.42665*T^2 - 0.041833*T^3)*as;
    z = (2306.2181*T + 1.09468*T^2 + 0.018203*T^3)*as;
    R3 = @(a) [cos(a) sin(a) 0; -sin(a) cos(a) 0; 0 0 1];
    R2 = @(a) [cos(a) 0 -sin(a); 0 1 0; sin(a) 0 cos(a)];
    M = (R3(-z)*R2(th)*R3(-zeta))';
end

function q2 = rotate_quat(M, q)
    % Quaternions of M*R(q) (body -> new frame), scalar last, sign kept continuous.
    qm = axes2quat(M(:, 1)', M(:, 2)', M(:, 3)');
    av = qm(1:3); aw = qm(4);
    bv = q(:, 1:3); bw = q(:, 4);
    q2 = [aw*bv + bw.*av + cross(repmat(av, size(q, 1), 1), bv, 2), aw*bw - bv*av'];
    q2 = continuous_sign(q2./vecnorm(q2, 2, 2));
end

function [r, v] = rv_j2000(E, t, M)
    [r, v] = eph_eval(E, t);
    r = r*M'; v = v*M';
end

function s = xml_escape(s)
    s = strrep(strrep(strrep(char(s), '&', '&amp;'), '<', '&lt;'), '>', '&gt;');
end

function v = ternary(c, a, b)
    if c, v = a; else, v = b; end
end

%% =========================================================================
%  SELECTED PASSES
%  =========================================================================
function info = export_selected_passes(product_dir, results_dir, plan, S, epoch, t_img, G, A_lc, eph, sites, aem)
    info.imaging_sat_index = plan.imaging.sat_index;
    info.lightcurve_found = false;
    P = struct();
    P.module_id = 'END-003';
    P.generated_at = char(string(datetime('now', 'TimeZone', 'UTC'), 'yyyy-MM-dd HH:mm:ss'));
    P.simulation = struct('start_utc', utc_str(epoch, 0), 'hours', eph(1).t(end)/3600, 'attitude_mode', S.mode, ...
        'orbit_source', 'END-001 ephemeris (satellite_NN_ephemeris.csv), no propagation in END-003', ...
        'ephemeris_step_s', eph(1).h, 'attitude_step_s', S.base_step);
    P.constellation = struct('n_satellites', plan.n_satellites, 'source', 'END-001 constellation_optimizer_output.csv + satellite_NN_ephemeris.csv');

    c = plan.imaging.cand;
    site = plan.imaging.site;
    [pk, ip] = max(G.el);
    im = struct();
    im.purpose = 'END-007 synthetic imagery: satellite in visibility of the target site, daylight at the site';
    im.found = plan.imaging.pass_found;
    im.satellite_index = plan.imaging.sat_index;
    im.satellite_label = plan.imaging.label;
    im.orbit = plan.imaging.orbit_cfg;
    im.pass_date_utc = utc_str(epoch, t_img(1)); im.pass_date_utc = im.pass_date_utc(1:10);
    im.start_utc = utc_str(epoch, t_img(1));
    im.end_utc = utc_str(epoch, t_img(end));
    im.duration_min = (t_img(end) - t_img(1))/60;
    im.peak_time_utc = utc_str(epoch, t_img(ip));
    im.aos_utc = utc_str(epoch, round(c.aos_t));
    im.los_utc = utc_str(epoch, round(c.los_t));
    im.subsatellite_sun_elevation_min_deg = c.sun_el_sub_min;
    im.peak_elevation_deg = pk;
    rr = G.r(ip, :); th = gmst_rad(juliandate(epoch) + t_img(ip)/86400);
    [p, ~] = geodetic_ecef(site.lat, site.lon, site.alt);
    im.min_off_nadir_deg = angle_deg(-rr, rot_ecef2eci(p, th) - rr);
    im.target_site = struct('name', site.name, 'lat_deg', rad2deg(site.lat), 'lon_deg', rad2deg(site.lon), ...
        'elev_threshold_deg', S.elev_threshold, 'source', sites.source, 'description', sites.description, 'n_points', sites.n_points);
    im.selected_by = 'END-001 (pass_selection.json)';
    im.site_sun_elevation_at_peak_deg = G.sun_site(ip);
    im.site_sun_elevation_min_deg = min(G.sun_site);
    im.satellite_sunlit_fraction = mean(G.sunlit);
    im.mean_nadir_offset_deg = mean(G.offset);
    im.n_samples = numel(t_img);
    im.sample_step_s = S.sel.img.output_step_s;
    im.sun_constraint = struct('enabled', S.sun_enabled, 'mode', S.sun_mode, 'threshold_deg', S.sun_thr, ...
        'met', logical(plan.imaging.constraint_met && plan.imaging.pass_found));
    im.csv = 'output_attitude_propagation.csv';
    im.aem = aem(1).file;
    im.n_candidate_passes = numel(plan.candidates);
    if isempty(plan.candidates)
        im.n_candidates_satisfying_sun_constraint = 0;
    else
        im.n_candidates_satisfying_sun_constraint = sum([plan.candidates.ok]);
    end
    P.imaging_pass = im;

    lc = plan.lightcurve;
    L = struct();
    L.purpose = 'END-010 reflectance / light curve: first pass of a sunlit satellite visible from the observatory at night';
    L.enabled = logical(lc.enabled);
    L.found = logical(lc.found);
    L.selected_by = 'END-001 (pass_selection.json)';
    L.rule = lc.rule;
    if lc.enabled
        L.observer = lc.observer;
        L.observer_sun_elevation_max_deg = lc.observer_sun_elevation_max_deg;
    end
    if lc.found
        info.lightcurve_found = true;
        L.satellite_index = lc.sat_index;
        L.satellite_label = lc.label;
        L.orbit = lc.orbit_cfg;
        L.pass_date_utc = utc_str(epoch, lc.start_t_s); L.pass_date_utc = L.pass_date_utc(1:10);
        L.start_utc = utc_str(epoch, lc.start_t_s);
        L.end_utc = utc_str(epoch, lc.end_t_s);
        L.duration_min = (lc.end_t_s - lc.start_t_s)/60;
        L.peak_time_utc = utc_str(epoch, lc.peak_t_s);
        L.peak_elevation_deg = lc.peak_el;
        L.observer_sun_elevation_at_peak_deg = lc.sun_el_obs_at_peak;
        L.observer_sun_elevation_used_deg = lc.observer_sun_elevation_used_deg;
        L.min_range_km = lc.min_range_km;
        L.satellite_sunlit_fraction = lc.sunlit_fraction;
        L.n_visible_windows_found = lc.n_windows;
        L.n_samples = numel(lc.t_out);
        L.sample_step_s = S.sel.lc.output_step_s;
        L.attitude_mode = S.mode;
        L.ephemeris_csv = 'output_attitude_propagation_lightcurve_ECI.csv';
        if numel(aem) > 1, L.aem = aem(2).file; end
        % ephemeris + attitude of the light-curve pass (ECI, quaternion body -> ECI)
        % END-010 reads the positions as J2000 (Vallado IAU-76/FK5 chain): CSV in
        % J2000 (IAU-76 precession of the STAR GMST frame, positions and attitude)
        idx = round(lc.t_out/S.base_step) + 1;
        Mj = to_j2000(juliandate(epoch) + mean(lc.t_out([1 end]))/86400);
        off = angle_deg(quat_rotate(A_lc.q(idx, :), [0 0 1]), -A_lc.r(idx, :));
        q = rotate_quat(Mj, A_lc.q(idx, :));
        r = A_lc.r(idx, :)*Mj'/1000;
        L.ephemeris_frame = 'J2000 (IAU-76 precession of the STAR GMST frame, nutation neglected): the frame END-010 reads';
        fid = fopen(fullfile(product_dir, L.ephemeris_csv), 'w');
        if fid < 0, error('STAR:END003:Output', 'Unable to open the light-curve ephemeris CSV in %s', product_dir); end
        fprintf(fid, 'timestamp_utc,eci_x_km,eci_y_km,eci_z_km,q_w,q_x,q_y,q_z,nadir_offset_deg\n');
        for i = 1:numel(lc.t_out)
            fprintf(fid, '%s,%.3f,%.3f,%.3f,%.4f,%.4f,%.4f,%.4f,%.2f\n', utc_str(epoch, lc.t_out(i)), r(i, 1), r(i, 2), r(i, 3), ...
                q(i, 4), q(i, 1), q(i, 2), q(i, 3), off(i));
        end
        fclose(fid);
        fprintf('Light-curve ephemeris CSV saved: %s (%d samples)\n', L.ephemeris_csv, numel(lc.t_out));
    end
    P.lightcurve_pass = L;

    cand_rows = struct('satellite_index', {}, 'site', {}, 'start_utc', {}, 'end_utc', {}, 'peak_time_utc', {}, ...
        'peak_elevation_deg', {}, 'site_sun_elevation_at_peak_deg', {}, 'site_sun_elevation_min_deg', {}, ...
        'subsatellite_sun_elevation_min_deg', {}, 'satellite_sunlit_fraction', {}, 'sun_constraint_ok', {}, ...
        'truncated_by_window', {}, 'selected', {});
    for i = 1:numel(plan.candidates)
        cc = plan.candidates(i);
        cand_rows(i).satellite_index = eph(cc.sat).index;
        cand_rows(i).site = cc.site_name;
        cand_rows(i).start_utc = utc_str(epoch, round(cc.aos_t));
        cand_rows(i).end_utc = utc_str(epoch, round(cc.los_t));
        cand_rows(i).peak_time_utc = utc_str(epoch, cc.peak_t);
        cand_rows(i).peak_elevation_deg = cc.peak_el;
        cand_rows(i).site_sun_elevation_at_peak_deg = cc.sun_el_peak;
        cand_rows(i).site_sun_elevation_min_deg = cc.sun_el_min;
        cand_rows(i).subsatellite_sun_elevation_min_deg = cc.sun_el_sub_min;
        cand_rows(i).satellite_sunlit_fraction = cc.sunlit_frac;
        cand_rows(i).sun_constraint_ok = cc.ok;
        cand_rows(i).truncated_by_window = cc.truncated;
        cand_rows(i).selected = cc.selected;
    end
    P.imaging_candidates = cand_rows;
    txt = jsonencode(P, 'PrettyPrint', true);
    write_text(fullfile(product_dir, 'selected_passes.json'), txt);
    write_text(fullfile(results_dir, 'selected_passes.json'), txt);

    fid = fopen(fullfile(product_dir, 'selected_pass_summary.csv'), 'w');
    fprintf(fid, 'purpose,satellite_index,satellite_label,date_utc,start_utc,end_utc,duration_min,peak_time_utc,peak_elevation_deg,ground_site,site_lat_deg,site_lon_deg,sun_elevation_at_peak_deg,satellite_sunlit_fraction\n');
    fprintf(fid, 'imaging_END-007,%d,%s,%s,%s,%s,%.2f,%s,%.2f,%s,%.4f,%.4f,%.2f,%.3f\n', im.satellite_index, im.satellite_label, ...
        im.pass_date_utc, im.start_utc, im.end_utc, im.duration_min, im.peak_time_utc, im.peak_elevation_deg, ...
        strrep(site.name, ',', ' '), rad2deg(site.lat), rad2deg(site.lon), im.site_sun_elevation_at_peak_deg, im.satellite_sunlit_fraction);
    if lc.found
        fprintf(fid, 'lightcurve_END-010,%d,%s,%s,%s,%s,%.2f,%s,%.2f,%s,%.4f,%.4f,%.2f,%.3f\n', L.satellite_index, L.satellite_label, ...
            L.pass_date_utc, L.start_utc, L.end_utc, L.duration_min, L.peak_time_utc, L.peak_elevation_deg, ...
            lc.observer.name, lc.observer.site_lat_deg, lc.observer.site_lon_deg, L.observer_sun_elevation_at_peak_deg, L.satellite_sunlit_fraction);
    end
    fclose(fid);

    fid = fopen(fullfile(product_dir, 'pass_candidates.csv'), 'w');
    fprintf(fid, 'satellite_index,site,start_utc,end_utc,peak_time_utc,peak_elevation_deg,site_sun_elevation_at_peak_deg,site_sun_elevation_min_deg,subsatellite_sun_elevation_min_deg,satellite_sunlit_fraction,sun_constraint_ok,truncated_by_window,selected\n');
    for i = 1:numel(cand_rows)
        r = cand_rows(i);
        fprintf(fid, '%d,%s,%s,%s,%s,%.2f,%.2f,%.2f,%.2f,%.3f,%d,%d,%d\n', r.satellite_index, strrep(r.site, ',', ' '), r.start_utc, r.end_utc, ...
            r.peak_time_utc, r.peak_elevation_deg, r.site_sun_elevation_at_peak_deg, r.site_sun_elevation_min_deg, ...
            r.subsatellite_sun_elevation_min_deg, r.satellite_sunlit_fraction, r.sun_constraint_ok, r.truncated_by_window, r.selected);
    end
    fclose(fid);

    fprintf('\n=== SELECTED PASSES ===\n');
    fprintf('Imaging   (END-007): %s over %s | %s -> %s | peak %.2f deg | site Sun %.2f deg\n', im.satellite_label, site.name, ...
        im.start_utc, im.end_utc, im.peak_elevation_deg, im.site_sun_elevation_at_peak_deg);
    if lc.found
        fprintf('Lightcurve(END-010): %s | %s -> %s | peak %.2f deg from %s | observer Sun %.2f deg\n', L.satellite_label, ...
            L.start_utc, L.end_utc, L.peak_elevation_deg, lc.observer.name, L.observer_sun_elevation_at_peak_deg);
    else
        fprintf('Lightcurve(END-010): no sunlit night pass found for the configured observer.\n');
    end
end

function write_text(path, text)
    fid = fopen(path, 'w');
    if fid < 0, error('STAR:END003:Output', 'Unable to open output file: %s', path); end
    fprintf(fid, '%s', text);
    fclose(fid);
end

%% =========================================================================
%  WHOLE-WINDOW SERIES, PLOTS, DASHBOARD, KPIs
%  =========================================================================
function D = dashboard_series(A, td, S, ctx, site, E)
    idx = round(td/S.base_step) + 1;
    n = numel(td);
    D.t = td;
    D.r = A.r(idx, :); D.v = A.v(idx, :); D.q = A.q(idx, :); D.w = A.w(idx, :);
    D.qnorm_drift = A.qnorm_drift(idx);
    D.alt = vecnorm(D.r, 2, 2) - S.Re;
    th = gmst_rad(ctx.jd0 + td/86400);
    D.th = th;
    [p, up] = geodetic_ecef(site.lat, site.lon, site.alt);
    D.el = elevation_deg(rot_eci2ecef(D.r, th), p, up);
    p_eci = rot_ecef2eci(repmat(p, n, 1), th);
    zb = quat_rotate(D.q, [0 0 1]);
    D.offset = angle_deg(zb, -D.r);
    D.target_offset = angle_deg(zb, p_eci - D.r);
    Sun = sun_vectors_eci(ctx.jd0 + td/86400);
    D.sunlit = sunlit_flags(D.r, Sun, S.Re);
    if S.flags.drag
        rho = density_table(E, td, ctx);
    else
        rho = zeros(n, 1);
    end
    D.M = zeros(n, 6);
    for i = 1:n
        M = disturbance_torques(D.r(i, :)', D.v(i, :)', qdcm(D.q(i, :)), Sun(i, :)', rho(i), S);
        D.M(i, :) = vecnorm(M, 2, 1);
    end
    D.eul = quat2eul([D.q(:, 4), D.q(:, 1:3)], 'ZYX');
    D.H_body = D.w.*S.Ivec';
    D.H_mag = vecnorm(D.H_body, 2, 2);
    D.H_eci = quat_rotate(D.q, D.H_body);
    D.H_dir = D.H_eci./max(D.H_mag, eps);
    D.H_dir(D.H_mag == 0, :) = 0;
    D.energy = 0.5*sum(D.w.*D.H_body, 2);
    [D.start_idx, D.end_idx] = find_runs(D.el > S.elev_threshold);
    % illumination of the body faces (+X -X +Y -Y +Z -Z): mean cosine of the Sun
    % incidence over the sunlit time, for the solar panels of END-006 (END-004)
    s_b = quat_rotate([-D.q(:, 1:3), D.q(:, 4)], Sun);
    cosf = max(0, s_b*[1 0 0; -1 0 0; 0 1 0; 0 -1 0; 0 0 1; 0 0 -1]');
    D.face_illum = mean(cosf(D.sunlit, :), 1);
end

function make_standard_plots(out_dir, D, S, site)
    set(groot, 'DefaultFigureColor', 'w'); set(groot, 'DefaultAxesColor', 'w');
    set(groot, 'DefaultAxesXColor', 'k'); set(groot, 'DefaultAxesYColor', 'k'); set(groot, 'DefaultAxesZColor', 'k');
    set(groot, 'DefaultTextColor', 'k'); set(groot, 'DefaultLegendColor', 'w'); set(groot, 'DefaultLegendTextColor', 'k');
    th = D.t/3600;
    f1 = light_figure('Color', [0.94 0.94 0.94], 'Visible', 'off', 'Position', [100 100 1200 900]);
    subplot(3,2,1); plot(th, rad2deg(D.w)); grid on; xlabel('Time [h]'); ylabel('Angular velocity [deg/s]'); title('Angular Velocity (body)'); legend('\omega_x','\omega_y','\omega_z');
    subplot(3,2,2); plot(th, rad2deg(D.eul)); grid on; xlabel('Time [h]'); ylabel('Euler angles [deg]'); title('Euler Angles (ZYX)'); legend('Z','Y','X');
    subplot(3,2,3); plot(th, D.M(:, [1 2 4])); grid on; xlabel('Time [h]'); ylabel('Torque [Nm]'); title('Disturbance Torques'); legend('GG','SRP','Drag');
    subplot(3,2,4); semilogy(th, D.M(:, [1 2 4]) + 1e-25); grid on; xlabel('Time [h]'); ylabel('Torque [Nm]'); title('Disturbance Torques (log)'); ylim([1e-15 1e-4]); legend('GG','SRP','Drag');
    subplot(3,2,5); plot(th, D.energy); grid on; xlabel('Time [h]'); ylabel('Energy [J]'); title('Rotational Energy');
    subplot(3,2,6); plot(th, D.alt/1000); grid on; xlabel('Time [h]'); ylabel('Altitude [km]'); title('Altitude (END-001 orbit)');
    save_png(f1, fullfile(out_dir, '01_telemetry.png'));

    f2 = light_figure('Color', 'w', 'Visible', 'off', 'Position', [100 100 1100 850]);
    subplot(3,1,1); plot(th, D.el, 'LineWidth', 1.2); grid on; ylabel('Elevation [deg]'); title(sprintf('Elevation over %s', site.name));
    subplot(3,1,2); plot(th, D.offset, 'LineWidth', 1.2, 'Color', [0.85 0.33 0.1]); grid on; ylabel('Nadir offset [deg]'); title('+Z from nadir');
    subplot(3,1,3); plot(th, D.target_offset, 'LineWidth', 1.2, 'Color', [0.2 0.6 0.2]); grid on; ylabel('Target offset [deg]'); title('+Z from the target'); xlabel('Time [h]');
    save_png(f2, fullfile(out_dir, '02_tracking.png'));

    f3 = light_figure('Color', 'w', 'Visible', 'off', 'Position', [100 100 1100 750]);
    subplot(2,1,1); plot(th, D.H_mag, 'k', 'LineWidth', 1.2); title('Angular Momentum Modulus'); xlabel('Time [h]'); ylabel('|H| [Nms]'); grid on;
    subplot(2,1,2); plot(th, D.H_dir, 'LineWidth', 1.1); title('Angular Momentum Direction (ECI)'); xlabel('Time [h]'); ylabel('Components'); legend('H_x','H_y','H_z'); grid on;
    save_png(f3, fullfile(out_dir, '03_angular_momentum.png'));

    % ground track (geocentric latitude of the sub-satellite point)
    r_ecef = rot_eci2ecef(D.r, D.th);
    lon = rad2deg(atan2(r_ecef(:,2), r_ecef(:,1)));
    lat = rad2deg(atan2(r_ecef(:,3), hypot(r_ecef(:,1), r_ecef(:,2))));
    f4 = light_figure('Color', 'w', 'Visible', 'off', 'Position', [100 100 1300 700]); hold on;
    try
        cl = load('coastlines'); plot(cl.coastlon, cl.coastlat, 'Color', [0.5 0.5 0.5]);
    catch
    end
    lonp = lon; lonp(abs([0; diff(lon)]) > 180) = NaN;
    plot(lonp, lat, 'b', 'LineWidth', 1);
    for i = 1:numel(D.start_idx)
        k = D.start_idx(i):D.end_idx(i);
        plot(lon(k), lat(k), 'Color', [0 0.8 0], 'LineWidth', 3);
    end
    plot(rad2deg(site.lon), rad2deg(site.lat), 'ro', 'MarkerFaceColor', 'r');
    text(rad2deg(site.lon) + 1, rad2deg(site.lat) + 1, site.name, 'Color', 'r', 'FontWeight', 'bold');
    title('Ground Track (END-001 orbit)'); xlabel('Longitude [deg]'); ylabel('Latitude [deg]'); grid on; axis equal; axis([-180 180 -90 90]);
    save_png(f4, fullfile(out_dir, '04_ground_track.png'));

    Re_km = S.Re/1000;
    for frame = ["ECEF", "ECI"]
        f = light_figure('Color', 'w', 'Visible', 'off', 'Position', [150 100 800 600]);
        [Xs, Ys, Zs] = sphere(50);
        surf(Xs*Re_km, Ys*Re_km, Zs*Re_km, 'FaceColor', [0.8 0.9 1], 'EdgeColor', 'none', 'FaceAlpha', 0.85); hold on; axis equal; grid on;
        if frame == "ECEF", rr = r_ecef/1000; else, rr = D.r/1000; end
        plot3(rr(:,1), rr(:,2), rr(:,3), 'Color', [0.6 0.6 0.6]);
        for i = 1:numel(D.start_idx)
            k = D.start_idx(i):D.end_idx(i);
            plot3(rr(k,1), rr(k,2), rr(k,3), 'Color', [0 0.8 0], 'LineWidth', 3);
        end
        xlabel('X [km]'); ylabel('Y [km]'); zlabel('Z [km]'); view(15, 35);
        title(sprintf('3D Orbit (%s frame, END-001 ephemeris)', frame));
        if frame == "ECEF"
            save_png(f, fullfile(out_dir, '05_orbit_3d_ecef.png'));
        else
            save_png(f, fullfile(out_dir, '06_orbit_3d_eci.png'));
        end
    end
end

function f = light_figure(varargin)
    % Light theme whatever the desktop theme (R2025a+), keeping the requested colour.
    f = figure(varargin{:});
    try
        f.Theme = 'light';
    catch
    end
    i = find(strcmpi(varargin(1:2:end), 'Color'), 1);
    if ~isempty(i), f.Color = varargin{2*i}; end
end

function save_png(fig, file)
    try
        drawnow;
        exportgraphics(fig, file, 'Resolution', 150, 'BackgroundColor', 'current');
    catch
        try
            print(fig, file, '-dpng', '-r150');
        catch err
            warning('STAR:PNGSaveFailed', 'Could not save PNG %s: %s', file, err.message);
        end
    end
    close(fig);
end

function export_dashboard_data(out_dir, cfg, epoch, D, S, site, plan, t_img, aem)
    r_eci_km = D.r/1000;
    r_ecef_m = rot_eci2ecef(D.r, D.th);
    r_ecef_km = r_ecef_m/1000;
    r_ground = S.Re*r_ecef_m./vecnorm(r_ecef_m, 2, 2)/1000;
    lon = mod(rad2deg(atan2(r_ecef_m(:,2), r_ecef_m(:,1))) + 180, 360) - 180;
    lat = rad2deg(atan2(r_ecef_m(:,3), hypot(r_ecef_m(:,1), r_ecef_m(:,2))));
    coverage = struct([]);
    for i = 1:numel(D.start_idx)
        k = D.start_idx(i):D.end_idx(i);
        coverage(i).start_index = D.start_idx(i);
        coverage(i).end_index = D.end_idx(i);
        coverage(i).time_h = D.t(k)/3600;
        coverage(i).ground_lon_deg = lon(k);
        coverage(i).ground_lat_deg = lat(k);
        coverage(i).r_eci_km = r_eci_km(k, :);
        coverage(i).r_ecef_km = r_ecef_km(k, :);
        coverage(i).r_ground_ecef_km = r_ground(k, :);
    end
    db = struct();
    db.summary = struct('module', 'STAR END-003 Attitude Propagation (STAR version: orbit from END-001)', ...
        'sim_start_date', char(string(epoch, 'yyyy-MM-dd HH:mm:ss')), 'sim_hours', D.t(end)/3600, ...
        'attitude_mode', S.mode, 'best_elevation_deg', max(D.el), 'elevation_threshold_deg', S.elev_threshold, ...
        'sample_count', numel(D.t), 'sample_step_s', S.dash_step, 'exported_pass_sample_count', numel(t_img), ...
        'satellite', plan.imaging.label, 'target_site', site.name, 'orbit_source', 'END-001 ephemeris');
    db.input = cfg;
    db.time_s = D.t;
    db.time_h = D.t/3600;
    db.angular_velocity_deg_s = rad2deg(D.w);
    db.euler_angles_deg = rad2deg(D.eul);
    db.torques = struct('gravity_gradient_Nm', D.M(:,1), 'solar_radiation_pressure_Nm', D.M(:,2), 'drag_Nm', D.M(:,4));
    db.rotational_energy_J = D.energy;
    db.altitude_km = D.alt/1000;
    db.elevation_deg = D.el;
    db.nadir_offset_deg = D.offset;
    db.target_offset_deg = D.target_offset;
    db.angular_momentum = struct('magnitude_Nms', D.H_mag, 'direction_eci', D.H_dir);
    db.orbit = struct('r_eci_km', r_eci_km, 'r_ecef_km', r_ecef_km, 'r_ground_ecef_km', r_ground, ...
        'ground_lon_deg', lon, 'ground_lat_deg', lat, 'coverage', coverage);
    [p, ~] = geodetic_ecef(site.lat, site.lon, site.alt);
    db.site = struct('name', site.name, 'lat_deg', rad2deg(site.lat), 'lon_deg', rad2deg(site.lon), ...
        'elev_threshold_deg', S.elev_threshold, 'r_ecef_km', p/1000);
    db.report = struct('mean_torques', struct('whole_window', struct('gravity_gradient_Nm', mean(D.M(:,1)), ...
        'solar_radiation_pressure_Nm', mean(D.M(:,2)), 'drag_Nm', mean(D.M(:,4)))));
    db.png_outputs = {'01_telemetry.png', '02_tracking.png', '03_angular_momentum.png', '04_ground_track.png', ...
        '05_orbit_3d_ecef.png', '06_orbit_3d_eci.png'};
    db.aem = aem;
    txt = jsonencode(db);
    write_text(fullfile(out_dir, 'attitude_propagation_plots_data.json'), txt);
    write_text(fullfile(out_dir, 'attitude_propagation_plots_data.js'), ['window.attitudePropagationData = ' txt ';' newline]);
    fprintf('Dashboard data saved: %s\n', fullfile(out_dir, 'attitude_propagation_plots_data.js'));
end

function export_kpis(out_dir, S, plan, D, G, sel_info, n_sat)
    pass_found = plan.imaging.pass_found;
    if ~pass_found || ~S.sun_enabled
        sun_kpi = NaN;
    else
        sun_kpi = plan.imaging.constraint_met;
    end
    if strcmp(S.mode, 'follow_site')
        mto = mean(G.target_offset); xto = max(G.target_offset);
    else
        mto = NaN; xto = NaN;
    end
    peak = max(G.el);
    rate = rad2deg(vecnorm(G.w, 2, 2));
    H_growth = (D.H_mag(end) - D.H_mag(1))/(D.t(end)/86400);
    k = struct([]);
    k = [k, kpi_entry('KPI-01', 'Ground Station Pass Found', pass_found, 'bool', 'run_validity', pass_found, NaN, NaN)];
    k = [k, kpi_entry('KPI-02', 'Elevation Threshold Met', peak, 'deg', 'run_validity', peak >= S.elev_threshold, S.elev_threshold, NaN)];
    k = [k, kpi_entry('KPI-03', 'Sun Constraint Satisfied', sun_kpi, 'bool', 'run_validity', sun_kpi, NaN, NaN)];
    k = [k, kpi_entry('KPI-04', 'Max Quaternion Norm Drift', max(D.qnorm_drift), '-', 'run_validity', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-05', 'Peak Elevation', peak, 'deg', 'pointing_performance', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-06', 'Pass Duration', (G.t(end) - G.t(1))/60, 'min', 'pointing_performance', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-07', 'Mean Nadir Offset During Pass', mean(G.offset), 'deg', 'pointing_performance', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-08', 'Max Nadir Offset During Pass', max(G.offset), 'deg', 'pointing_performance', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-09', 'Mean Target Offset During Pass', mto, 'deg', 'pointing_performance', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-10', 'Max Target Offset During Pass', xto, 'deg', 'pointing_performance', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-11', 'Mean Gravity-Gradient Torque', mean(D.M(:,1)), 'Nm', 'disturbance_environment', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-12', 'Mean SRP Torque', mean(D.M(:,2)), 'Nm', 'disturbance_environment', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-13', 'Mean Drag Torque', mean(D.M(:,4)), 'Nm', 'disturbance_environment', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-14', 'Eclipse Fraction', 100*mean(~D.sunlit), '%', 'disturbance_environment', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-15', 'Peak Angular Momentum Magnitude', max(D.H_mag), 'Nms', 'momentum_and_rates', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-16', 'Angular Momentum Net Growth Rate', H_growth, 'Nms/day', 'momentum_and_rates', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-17', 'Constellation Satellites Screened', n_sat, '-', 'pass_selection', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-18', 'Imaging Pass Satellite Index', sel_info.imaging_sat_index, '-', 'pass_selection', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-19', 'Night Light-Curve Pass Found', sel_info.lightcurve_found, 'bool', 'pass_selection', sel_info.lightcurve_found, NaN, NaN)];
    k = [k, kpi_entry('KPI-20', 'Mean Body Rate During Imaging Pass', mean(rate), 'deg/s', 'momentum_and_rates', NaN, NaN, NaN)];
    k = [k, kpi_entry('KPI-21', 'Max Body Rate During Imaging Pass', max(rate), 'deg/s', 'momentum_and_rates', NaN, NaN, NaN)];
    cat = struct('module_id', 'END-003', 'attitude_mode', S.mode, 'orbit_source', 'END-001 ephemeris', ...
        'generated_at', char(string(datetime('now', 'TimeZone', 'UTC'), 'yyyy-MM-dd HH:mm:ss')), 'kpis', k);
    f = D.face_illum;
    cat.illumination = struct('mean_cos_sunlit', struct('x_plus', f(1), 'x_minus', f(2), 'y_plus', f(3), 'y_minus', f(4), ...
        'z_plus', f(5), 'z_minus', f(6)), 'sunlit_fraction', mean(D.sunlit), 'satellite', plan.imaging.label, ...
        'note', ['mean cosine of the Sun incidence on each body face over the sunlit time of the whole window ', ...
        '(attitude of this run, eclipses excluded): P_face = P_peak x factor']);
    file = fullfile(out_dir, 'attitude_summary.json');
    write_text(file, jsonencode(cat, 'PrettyPrint', true));
    fprintf('KPI catalog saved: %s\n', file);
end

function k = kpi_entry(id, name, value, unit, category, meets_requirement, threshold_ok, threshold_bad)
    k.id = id;
    k.name = name;
    k.value = value;
    k.unit = unit;
    k.category = category;
    k.meets_requirement = meets_requirement;
    k.threshold_ok = threshold_ok;
    k.threshold_bad = threshold_bad;
end

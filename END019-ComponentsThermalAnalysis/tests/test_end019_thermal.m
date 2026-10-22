function tests = test_end019_thermal
%TEST_END019_THERMAL  Checks of END-019 (lumped-capacitance thermal model) against hand-computed cases (2026-10-20).
%
%   From END019-ComponentsThermalAnalysis:   results = runtests('tests/test_end019_thermal.m')
%
%   Steady state of the Backward-Euler step with linearised radiation (exact at the fixed point):
%     sum_i sigma epsA_i (T_i^4 - T_space^4) = absorbed + internal power, the conduction network carries no net heat;
%     one internal node of power P linked to the 6 faces by G/6 each: T_CTR - mean(T_faces) = P / G.
%   Cylindrical shadow of a circular orbit of height h and radius r = R + h at beta angle beta:
%     eclipse fraction = acos(sqrt(h^2 + 2 R h) / (r cos beta)) / pi, none above beta* = asin(R / r).
%   Rate of the argument of latitude with the secular J2 terms (Vallado, circular orbit):
%     n_bar + omega_dot, n_bar = n (1 + 3/2 J2 (R/r)^2 (1 - 3/2 sin^2 i)), omega_dot = 3/4 n J2 (R/r)^2 (4 - 5 sin^2 i).
%   Sun direction: declination 23.44 deg at the 2025 June solstice, 0 deg (and right ascension 0) at the March equinox.
%   Examples (examples/, inputs of a STAR run of 2026-09-22): the test case of the report (input_test.json, SAR at
%   30% duty) within 3 degC of the report (SAR 217, CTR 172, BAT 103, solar panels 192 degC); input_termico.json
%   (SAR in the imaging passes) as in README.md (SAT-01: SAR 122.6, BAT 54.5, CTR 85.6 degC).
    tests = functiontests(localfunctions);
end

function setupOnce(tc)
    root = fileparts(fileparts(mfilename('fullpath')));
    tc.TestData.src = fullfile(root, 'src');
    tc.TestData.examples = fullfile(root, 'examples');
    addpath(tc.TestData.src);
    tc.TestData.work = tempname;
    mkdir(tc.TestData.work);
    % the two example configurations, run once on the example STAR inputs
    star_in = fullfile(tc.TestData.examples, 'esempi_io_star');
    for c = {'input_test', 'input_termico'}
        opts = jsondecode(fileread(fullfile(tc.TestData.examples, [c{1} '.json'])));
        opts.star_input_dir = star_in;
        opts.output_dir = fullfile(tc.TestData.work, c{1});
        f = fullfile(tc.TestData.work, [c{1} '.json']);
        write_json(f, opts);
        evalc('rows = star_thermal_main(f);');
        tc.TestData.(c{1}) = struct('rows', rows, 'out', opts.output_dir);
    end
end

function teardownOnce(tc)
    rmpath(tc.TestData.src);
    if isfolder(tc.TestData.work), rmdir(tc.TestData.work, 's'); end
end

%% =========================================================================
function test_steady_state_in_the_dark(tc)
    % no Sun, albedo or Earth IR: the 7 W of the central node leave as radiation from the faces
    cfg = direct_cfg('nadir', 0, 80);
    cfg.env.Gs = 0; cfg.env.albedo = 0; cfg.env.qIR = 0;
    R = lcm_solve(cfg);
    T = R.T(end, :)' + 273.15; M = R.M;
    verifyEqual(tc, sum(cfg.env.sigma*M.epsA.*(T.^4 - cfg.env.Tspace^4)), 7, 'RelTol', 1e-6);
    verifyEqual(tc, T(M.iCTR) - mean(T(1:6)), 7/cfg.cond.Gw_ctr, 'RelTol', 1e-6);
    verifyLessThan(tc, max(abs(R.T(end, :) - R.T(end - round(R.Torb/cfg.sim.dt), :))), 1e-3);   % no drift in the last orbit
end

function test_steady_state_in_constant_sunlight(tc)
    % beta = 90 deg (never in eclipse), +Z to the Sun, no albedo or Earth IR: absorbed = alpha_z Gs A_z
    cfg = direct_cfg('sun', 90, 80);
    cfg.env.albedo = 0; cfg.env.qIR = 0;
    R = lcm_solve(cfg);
    T = R.T(end, :)' + 273.15; M = R.M;
    verifyTrue(tc, all(R.lit == 1));
    absorbed = cfg.sat.alpha_z*cfg.env.Gs*cfg.sat.dims(1)*cfg.sat.dims(2);
    verifyEqual(tc, sum(cfg.env.sigma*M.epsA.*(T.^4 - cfg.env.Tspace^4)), absorbed + 7, 'RelTol', 1e-6);
    verifyGreaterThan(tc, T(5), max(T([1:4 6])));                                % the sunlit +Z face is the hottest
end

function test_eclipse_fraction_matches_the_cylindrical_shadow(tc)
    for beta = [0 40 75]
        cfg = direct_cfg('nadir', beta, 4);
        R = lcm_solve(cfg);
        h = cfg.orbit.alt; Re = cfg.env.Re; r = Re + h;
        expected = 0;
        if abs(beta) < asind(Re/r), expected = acos(sqrt(h^2 + 2*Re*h)/(r*cosd(beta)))/pi; end
        verifyEqual(tc, mean(R.lit == 0), expected, 'AbsTol', 2*cfg.sim.dt/R.Torb, sprintf('beta = %g deg', beta));
    end
end

function test_sar_duty_cycle(tc)
    cfg = star_config(struct('form_factor', '3U', 'panels', 'both', 'n_internal_nodes', 3, 'sar_power_W', 200));
    cfg.orbit = direct_cfg('nadir', 0, 4).orbit;
    cfg.sar.source = 'duty'; cfg.sar.duty = 0.25;
    R = lcm_solve(cfg);
    verifyEqual(tc, mean(R.sar_on), 0.25, 'AbsTol', 2*cfg.sim.dt/R.Torb);
end

function test_model_network_conserves_heat(tc)
    dims = struct('U1', [0.1 0.1 0.1], 'U3', [0.1 0.1 0.3], 'U6', [0.1 0.2 0.3], 'U12', [0.2 0.2 0.3]);
    for form = {'1U', '3U', '6U', '12U'}
        for panels = {'body', 'deployable', 'both'}
            for nodes = 1:3
                cfg = star_config(struct('form_factor', form{1}, 'panels', panels{1}, 'n_internal_nodes', nodes));
                M = star_build_model(cfg);
                id = sprintf('%s %s %d nodes', form{1}, panels{1}, nodes);
                d = dims.(['U' form{1}(1:end-1)]);
                npan = 2*~strcmp(panels{1}, 'body');
                verifyEqual(tc, M.Nn, 6 + npan + nodes, id);
                verifyEqual(tc, M.Aface', [d(2)*d(3) d(2)*d(3) d(1)*d(3) d(1)*d(3) d(1)*d(2) d(1)*d(2)], 'AbsTol', 1e-15, id);
                verifyEqual(tc, M.Lc, M.Lc', id);
                verifyEqual(tc, sum(M.Lc, 2), zeros(M.Nn, 1), 'AbsTol', 1e-12, id);   % conduction moves heat, makes none
                verifyGreaterThan(tc, min(eig(M.Lc)), -1e-12, id);
                verifyTrue(tc, all(M.C > 0), id);
                verifyEqual(tc, M.epsA(end-nodes+1:end), zeros(nodes, 1), id);         % internal nodes do not radiate
                internal = [0.60 0.60 0.87];                                           % fraction of 1.33 kg per U
                verifyEqual(tc, sum(cfg.nodes.mass), internal(nodes)*1.33*round(prod(d)/0.001), 'RelTol', 1e-12, id);
            end
        end
    end
end

function test_sun_direction_and_beta(tc)
    solstice = datetime(2025, 6, 21, 2, 42, 0, 'TimeZone', 'UTC');
    equinox = datetime(2025, 3, 20, 9, 1, 0, 'TimeZone', 'UTC');
    s = star_sun_eci(solstice);
    verifyEqual(tc, asind(s(3)), 23.44, 'AbsTol', 0.02);
    s = star_sun_eci(equinox);
    verifyEqual(tc, [asind(s(3)), atan2d(s(2), s(1))], [0 0], 'AbsTol', 0.02);
    % polar orbit with the normal along the Sun (beta 90), across it (beta 0); equatorial orbit at the solstice
    verifyEqual(tc, star_beta(struct('incl', 90, 'raan', 90, 'start', equinox)), 90, 'AbsTol', 0.1);
    verifyEqual(tc, star_beta(struct('incl', 90, 'raan', 0, 'start', equinox)), 0, 'AbsTol', 0.02);
    verifyEqual(tc, star_beta(struct('incl', 0, 'raan', 0, 'start', solstice)), 23.44, 'AbsTol', 0.02);
end

function test_orbit_radius_rate_and_phase(tc)
    cfg = star_config();
    orb = struct('alt', 550e3, 'incl', 97.6, 'raan', 30, 'omega', 0, 'nu', 10, ...
        'start', datetime(2026, 5, 21, 13, 41, 10, 'TimeZone', 'UTC'));
    [r, uDot, phi0] = star_orbit_phase(cfg, orb);
    e = cfg.env;
    verifyEqual(tc, r, e.Req + orb.alt);                                          % altitude above the equatorial radius
    n = sqrt(e.mu/r^3); k = e.J2*(e.Req/r)^2; si2 = sind(orb.incl)^2;
    verifyEqual(tc, uDot, n*(1 + 1.5*k*(1 - 1.5*si2)) + 0.75*n*k*(4 - 5*si2), 'RelTol', 1e-6);
    orb.nu = orb.nu + 40;                                                          % 40 deg further along the orbit
    [~, ~, phi1] = star_orbit_phase(cfg, orb);
    verifyEqual(tc, angle(exp(1i*(phi1 - phi0))), deg2rad(40), 'AbsTol', 1e-9);
end

function test_design_cases_and_star_satellite(tc)
    % phase D (2026-10-21): END-006 envelope / mass / solar faces, END-004 dissipation split in the calibrated ratio,
    % hot case (high beta, max dissipation) warmer than the cold case (beta 0, idle) on every internal node
    cfg = star_config(struct('form_factor', '12U', 'n_internal_nodes', 2, 'dims_m', [0.2263 0.2263 0.366], 'mass_kg', 7.8, ...
        'solar_faces', {{'+X', '-X'}}, 'P_internal_W', 3.5, 'bat_min_C', -10, 'bat_max_C', 45));
    verifyEqual(tc, cfg.sat.dims, [0.2263 0.2263 0.366]);
    verifyEqual(tc, sum(cfg.nodes.mass), 0.6*7.8, 'AbsTol', 1e-12);
    verifyEqual(tc, cfg.nodes.Pconst, [2.5 1.0], 'AbsTol', 1e-12);                 % 3.5 W in the 5:2 ratio
    verifyEqual(tc, cfg.sat.solar_faces, [1 2]);
    verifyEqual(tc, cfg.sat.alpha([1 3 5]), [cfg.sat.alpha_solar cfg.sat.alpha_z cfg.sat.alpha_z]);
    verifyEqual(tc, [cfg.limits.BAT_min cfg.limits.BAT], [-10 45]);
    orb = struct('alt', 600e3, 'incl', 53, 'raan', 30, 'omega', 0, 'nu', 0, 'start', datetime(2026, 5, 21, 'TimeZone', 'UTC'));
    hot = star_design_case(cfg, orb, struct('name', 'hot', 'beta_deg', 70, 'P_internal_W', 8));
    cold = star_design_case(cfg, orb, struct('name', 'cold', 'beta_deg', 0, 'P_internal_W', 1.5));
    verifyEqual(tc, hot.eclipse_min, 0, 'beta 70 deg at 600 km: no eclipse');
    r = cfg.env.Req + orb.alt; T = 2*pi*sqrt(r^3/cfg.env.mu)/60;
    verifyEqual(tc, cold.eclipse_min, acosd(sqrt(r^2 - cfg.env.Re^2)/r)/180*T, 'RelTol', 0.02, 'cylindrical shadow at beta 0');
    verifyLessThan(tc, hot.orbits, 200, 'periodic regime not reached');
    for n = {'CTR', 'BAT'}
        k = find(strcmp(hot.names, n{1}));
        verifyGreaterThan(tc, hot.Tmax(k), cold.Tmax(k), n{1});
        verifyGreaterThan(tc, hot.Tmin(k), cold.Tmin(k), n{1});
    end
end

function test_hot_case_is_the_hottest_beta_of_the_life(tc)
    % 2026-10-22: the hot case searches |beta| over the life range; it is at least as hot as both range ends and as
    % every beta it scanned, and the sign of beta does not change the result
    cfg = star_config(struct('form_factor', '12U', 'n_internal_nodes', 2, 'dims_m', [0.2263 0.2263 0.366], 'mass_kg', 7.8, ...
        'solar_faces', {{'+X', '-X', '+Y', '-Y'}}, 'panels', 'body'));
    orb = struct('alt', 627.6e3, 'incl', 53.3, 'raan', 30, 'omega', 0, 'nu', 0, 'start', datetime(2026, 5, 21, 'TimeZone', 'UTC'));
    cs = struct('name', 'hot', 'P_internal_W', 2.6);
    hot = star_hot_case(cfg, orb, cs, -76.7, 76.4);
    k = find(strcmp(hot.names, 'BAT'));
    verifyEqual(tc, hot.Tmax(k), max(hot.scan(:, 2)));
    verifyGreaterThanOrEqual(tc, hot.beta_deg, 0); verifyLessThanOrEqual(tc, hot.beta_deg, 76.7);
    for b = [0 76.7]
        c = star_design_case(cfg, orb, struct('name', 'hot', 'beta_deg', b, 'P_internal_W', 2.6));
        verifyGreaterThanOrEqual(tc, hot.Tmax(k), c.Tmax(k) - 1e-9, sprintf('hotter than beta %g', b));
    end
    m = star_design_case(cfg, orb, struct('name', 'hot', 'beta_deg', -hot.beta_deg, 'P_internal_W', 2.6));
    verifyEqual(tc, m.Tmax(k), hot.Tmax(k), 'AbsTol', 1e-9, 'symmetric in the sign of beta');
    verifyTrue(tc, contains(hot.rule, 'hottest BAT'));
end

function test_attitude_file_is_read_as_body_to_eci(tc)
    % END-003's file for Unreal holds the ECI->body quaternion: read with 'eci2body', +Z body points to nadir in the pass
    csv = fullfile(tc.TestData.examples, 'esempi_io_star', 'output_attitude_propagation', 'output_attitude_propagation.csv');
    start = datetime(2026, 5, 21, 13, 41, 10, 'TimeZone', 'UTC');
    att = star_read_attitude(csv, start, 'eci2body');
    verifyLessThan(tc, max(angle_to_nadir(att)), 0.1);
    wrong = star_read_attitude(csv, start, 'body2eci');                           % the reading before 2026-10-15
    verifyGreaterThan(tc, max(angle_to_nadir(wrong)), 10);
end

function test_report_test_case(tc)
    % input_test.json: 3U, deployable panels, 3 internal nodes, SAR 200 W at 30% duty; SAT-01 against the report
    rows = tc.TestData.input_test.rows;
    verifyEqual(tc, height(rows), 5);
    s1 = rows(rows.satellite_index == 1, :);
    verifyEqual(tc, [s1.SAR_max_C, s1.CTR_max_C, s1.BAT_max_C, s1.solarpanel_max_C], [217 172 103 192], 'AbsTol', 3);
    verifyEqual(tc, rows.BAT_over_limit, rows.BAT_max_C > 25);
    check_products(tc, tc.TestData.input_test.out, 5);
end

function test_sar_on_only_in_the_imaging_passes(tc)
    % input_termico.json: SAR on in the imaging passes of each satellite (only SAT-01 has one), not in the
    % lightcurve pass of SAT-04
    D = tc.TestData.input_termico;
    s1 = D.rows(D.rows.satellite_index == 1, :);
    verifyEqual(tc, [s1.SAR_max_C, s1.BAT_max_C, s1.CTR_max_C], [122.6 54.5 85.6], 'AbsTol', 0.5);
    verifyEqual(tc, D.rows.n_imaging_passes', [1 0 0 0 0]);
    pass_csv = fullfile(tc.TestData.examples, 'esempi_io_star', 'output_attitude_propagation', 'selected_pass_summary.csv');
    start = datetime(2026, 5, 21, 13, 41, 10, 'TimeZone', 'UTC');
    W = star_read_passes(pass_csv, 1, 'imaging', start);
    T = readtable(fullfile(D.out, 'output_thermal_SAT-01.csv'), 'TextType', 'string');
    t = seconds(datetime(T.timestamp_utc, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss''Z''', 'TimeZone', 'UTC') - start);
    on = T.sar_on == 1;
    verifyTrue(tc, all(any(t(on) >= W(:, 1)' & t(on) < W(:, 2)', 2)), 'SAR on outside the imaging pass');
    verifyGreaterThanOrEqual(tc, nnz(on), floor((W(1, 2) - W(1, 1))/60));        % 60 s samples over the 12.8 min pass
    for k = 2:5
        T = readtable(fullfile(D.out, sprintf('output_thermal_SAT-%02d.csv', k)), 'TextType', 'string');
        verifyFalse(tc, any(T.sar_on == 1), sprintf('SAT-%02d', k));
    end
    check_products(tc, D.out, 5);
end

function test_internal_node_options_and_relative_paths(tc)
    % one satellite, 6 h; the JSON gives its folders relative to itself
    base = fullfile(tc.TestData.work, 'nodes');
    ex = fullfile(tc.TestData.examples, 'esempi_io_star');
    mkdir(fullfile(base, 'in', 'output_constellation_optimizer'));
    mkdir(fullfile(base, 'in', 'output_attitude_propagation'));
    sat = jsondecode(fileread(fullfile(ex, 'output_constellation_optimizer', 'satellite_01.json')));
    sat.sim_hours = 6;
    write_json(fullfile(base, 'in', 'output_constellation_optimizer', 'satellite_01.json'), sat);
    for f = {'selected_pass_summary.csv', 'output_attitude_propagation.csv'}
        copyfile(fullfile(ex, 'output_attitude_propagation', f{1}), fullfile(base, 'in', 'output_attitude_propagation'));
    end
    expected = {{'CTR'}, {'CTR', 'BAT'}, {'CTR', 'BAT', 'SAR'}};
    for nodes = 1:3
        out = sprintf('out_%d', nodes);
        f = fullfile(base, sprintf('input_%d.json', nodes));
        write_json(f, struct('star_input_dir', './in', 'output_dir', ['./' out], 'form_factor', '3U', ...
            'panels', 'both', 'n_internal_nodes', nodes, 'sar_power_W', 200, 'sar_source', 'passes'));
        evalc('rows = star_thermal_main(f);');
        id = sprintf('%d nodes', nodes);
        verifyEqual(tc, height(rows), 1, id);
        S = jsondecode(fileread(fullfile(base, out, 'thermal_summary_SAT-01.json')));
        T = readtable(fullfile(base, out, 'output_thermal_SAT-01.csv'), 'TextType', 'string');
        for nm = {'CTR', 'BAT', 'SAR'}
            has = ismember(nm{1}, expected{nodes});
            verifyEqual(tc, isfield(S.nodes, nm{1}), has, [id ': node ' nm{1}]);
            verifyEqual(tc, ismember(['T_' nm{1}], T.Properties.VariableNames), has, [id ': column T_' nm{1}]);
        end
        verifyEqual(tc, isfield(S.peaks, 'BAT_max_C'), nodes >= 2, id);
        verifyEqual(tc, isfield(S.peaks, 'SAR_max_C_orbit'), nodes == 3, id);
        verifyEqual(tc, isfield(S.violations, 'SAR_over'), nodes == 3, id);
        verifyEqual(tc, height(T), ceil(6*3600/60), id);                         % one row a minute
    end
end

function test_design_cases_through_the_json_input(tc)
    % the cases as the STAR runner writes them (hot: life beta range, cold: fixed beta; different fields, so jsondecode
    % gives a cell array): every satellite gets the hot / cold columns and the summary blocks; equal satellites share one run
    base = fullfile(tc.TestData.work, 'cases');
    mkdir(base);
    f = fullfile(base, 'input.json');
    fid = fopen(f, 'w');
    fprintf(fid, ['{"star_input_dir": "%s", "output_dir": "./out", "form_factor": "12U", "n_internal_nodes": 2, ', ...
        '"solar_faces": ["+X","-X","+Y","-Y"], "panels": "body", "P_internal_W": 2.0, "bat_min_C": -10, "bat_max_C": 45, ', ...
        '"cases": [{"name": "hot", "P_internal_W": 2.6, "satellite_index": [1,2,3,4,5], "beta_min_deg": [-60,-60,-60,-60,-60], ', ...
        '"beta_max_deg": [75,75,75,75,75]}, {"name": "cold", "P_internal_W": 1.6, "satellite_index": [1,2,3,4,5], ', ...
        '"beta_deg": [0,0,0,0,0]}]}'], replace(fullfile(tc.TestData.examples, 'esempi_io_star'), '\', '/'));
    fclose(fid);
    evalc('rows = star_thermal_main(f);');
    verifyEqual(tc, height(rows), 5);
    verifyTrue(tc, all(rows.hot_BAT_max_C > rows.cold_BAT_min_C));
    verifyTrue(tc, all(abs(rows.cold_beta_deg) < 1e-9));
    verifyTrue(tc, all(rows.hot_beta_deg >= 0 & rows.hot_beta_deg <= 75));
    S = jsondecode(fileread(fullfile(base, 'out', 'thermal_summary_SAT-01.json')));
    verifyTrue(tc, contains(S.design_cases.hot.rule, 'hottest BAT'));
    verifyNotEmpty(tc, S.design_cases.hot.beta_scan);
    verifyEqual(tc, S.limits.BAT_min, -10);
end

function test_invalid_inputs(tc)
    verifyError(tc, @() star_config(struct('form_factor', '2U')), 'star_config:form');
    verifyError(tc, @() star_config(struct('n_internal_nodes', 4)), 'star_config:nodes');
    verifyError(tc, @() star_thermal_main(fullfile(tc.TestData.work, 'missing.json')), 'star_thermal_main:config');
    empty = fullfile(tc.TestData.work, 'empty');
    mkdir(empty);
    cfg = star_config(struct('star_input_dir', empty, 'output_dir', fullfile(empty, 'out')));
    verifyError(tc, @() star_process(cfg), 'star_process:noinput');
end

%% =========================================================================
%  HELPERS
%  =========================================================================
function cfg = direct_cfg(attitude, beta, norb)
    % direct analysis (lcm_solve): 3U, body panels, the central node only (7 W); 550 km, fixed beta
    cfg = star_config(struct('form_factor', '3U', 'panels', 'body', 'n_internal_nodes', 1));
    cfg.orbit = struct('alt', 550e3, 'incl', 97.6, 'raan', 0, 'startDate', datetime(2025, 3, 21), ...
        'beta', beta, 'Norb', norb, 'attitude', attitude);
    cfg.T0 = -60;
end

function a = angle_to_nadir(att)
    % angle [deg] between +Z body (rotated by the body->ECI quaternion, v' = v + 2w(u x v) + 2u x (u x v)) and nadir
    a = zeros(size(att.quat, 1), 1);
    for k = 1:numel(a)
        q = att.quat(k, :)/norm(att.quat(k, :)); w = q(1); u = q(2:4)'; v = [0; 0; 1];
        z = v + 2*w*cross(u, v) + 2*cross(u, cross(u, v));
        nadir = -att.eci(k, :)'/norm(att.eci(k, :));
        a(k) = acosd(max(-1, min(1, z'*nadir)));
    end
end

function check_products(tc, out, nsat)
    for k = 1:nsat
        verifyTrue(tc, isfile(fullfile(out, sprintf('output_thermal_SAT-%02d.csv', k))), sprintf('CSV SAT-%02d', k));
        f = fullfile(out, sprintf('thermal_summary_SAT-%02d.json', k));
        verifyTrue(tc, isfile(f), f);
        S = jsondecode(fileread(f));
        verifyGreaterThan(tc, S.thermal.spinup_orbits, 0);
        verifyLessThan(tc, S.thermal.spinup_orbits, 100, 'periodic regime not reached');
    end
    verifyEqual(tc, height(readtable(fullfile(out, 'thermal_constellation_output.csv'))), nsat);
end

function write_json(f, s)
    fid = fopen(f, 'w'); fprintf(fid, '%s', jsonencode(s)); fclose(fid);
end

function tests = test_end001_constellation
%TEST_END001_CONSTELLATION  Checks of END-001 (END001-ConstellationOptimizer) as STAR uses it (2026-10-19).
%
%   From the STAR folder:   results = runtests('tests/test_end001_constellation.m')
%
%   END-001 is a separate repository (git submodule): its STAR tests live here and its code is not changed.
%   - The module's validation harness (lib/validate_end001_changes.m): each of its 14 checks against an
%     independent reference is one test (placement, visibility, objectives, revisit gaps, propagator, latency,
%     sensor coverage, station visibility, Sun elevation, repeat ground track, periodic statistics, determinism,
%     downstream ephemeris).
%   - propagate_orbit_j2: node rate = -3/2 n J2 (Re/a)^2 cos i (circular orbit, first order in J2).
%   - lib/SSO_RGT_table_Final.csv: the Sun-synchronous orbits (k2rgt semi-major axis, as the fitness functions)
%     turn their node by 360 deg per tropical year.
%   - gmst_iau82 (frame of the exported ephemerides) = the GMST of END-003 (star_attitude_propagation_star
%     gmst_rad), which reads those ephemerides.
%   - export_downstream_ephemeris: satellite_NN_ephemeris.csv as END-003 reads it (columns, UTC timestamps on a
%     uniform step, circular radius, velocity = d r/dt, +Z body to nadir).
    tests = functiontests(localfunctions);
end

function setupOnce(tc)
    star = fileparts(fileparts(mfilename('fullpath')));
    tc.TestData.end001 = fullfile(star, 'END001-ConstellationOptimizer');
    assumeTrue(tc, isfile(fullfile(tc.TestData.end001, 'lib', 'validate_end001_changes.m')), ...
        'END-001 submodule not checked out (git submodule update --init)');
    tc.TestData.path = path;
    tc.TestData.cwd = cd(tc.TestData.end001);
    addpath(genpath(fullfile(tc.TestData.end001, 'lib')));
    tc.TestData.harness = splitlines(evalc('validate_end001_changes'));
    tc.TestData.work = tempname;
    mkdir(tc.TestData.work);
end

function teardownOnce(tc)
    cd(tc.TestData.cwd);
    path(tc.TestData.path);                 % lib/ shadows common names (sun.m ...): leave the path as found
    if isfolder(tc.TestData.work), rmdir(tc.TestData.work, 's'); end
end

%% =========================================================================
%  VALIDATION HARNESS (lib/validate_end001_changes.m)
%  =========================================================================
function test_harness_01_constellation_placement(tc), verify_check(tc, 1); end
function test_harness_02_visibility_run_lengths(tc), verify_check(tc, 2); end
function test_harness_03_sso_objectives(tc), verify_check(tc, 3); end
function test_harness_04_revisit_gaps(tc), verify_check(tc, 4); end
function test_harness_05_propagator(tc), verify_check(tc, 5); end
function test_harness_06_latency(tc), verify_check(tc, 6); end
function test_harness_07_walker_delta_objectives(tc), verify_check(tc, 7); end
function test_harness_08_sensor_coverage(tc), verify_check(tc, 8); end
function test_harness_09_station_visibility(tc), verify_check(tc, 9); end
function test_harness_10_solar_elevation(tc), verify_check(tc, 10); end
function test_harness_11_repeat_ground_track(tc), verify_check(tc, 11); end
function test_harness_12_periodic_statistics(tc), verify_check(tc, 12); end
function test_harness_13_determinism(tc), verify_check(tc, 13); end
function test_harness_14_downstream_ephemeris(tc), verify_check(tc, 14); end

%% =========================================================================
%  ORBITS AND FRAMES
%  =========================================================================
function test_j2_node_rate(tc)
    mu = 3.986004415e14; Re = 6378137.0; J2 = 1.0826261738522227e-3;
    for alt_inc = [400e3 30; 600e3 53; 900e3 98]'
        a = Re + alt_inc(1); inc = deg2rad(alt_inc(2));
        n = sqrt(mu/a^3);
        t = (0:60:2*86400)';
        [r, v] = propagate_orbit_j2(t, a, 0, inc, 0, 0.3, 0);
        h = cross(r, v, 2);
        node = unwrap(atan2(h(:, 1), -h(:, 2)));
        rate = (node(end) - node(1))/(t(end) - t(1));
        verifyEqual(tc, rate, -1.5*n*J2*(Re/a)^2*cos(inc), 'RelTol', 1e-3, sprintf('%g km, %g deg', alt_inc(1)/1e3, alt_inc(2)));
        verifyEqual(tc, vecnorm(r, 2, 2), a/1e3*ones(numel(t), 1), 'RelTol', 1e-12, 'circular orbit');
    end
end

function test_sso_table_orbits_are_sun_synchronous(tc)
    T = readtable(fullfile(tc.TestData.end001, 'lib', 'SSO_RGT_table_Final.csv'), 'Delimiter', ';', 'VariableNamingRule', 'preserve');
    sun_rate = 2*pi/(365.2422*86400);                % mean Sun along the equator, rad/s
    t = (0:600:86400)';
    err = zeros(height(T), 1);
    for k = 1:height(T)                              % every row (2026-10-19: worst 6e-4)
        inc = deg2rad(T.SSO_Incl_deg(k));
        a = k2rgt(T.("Repeat_Days D")(k), T.("Total_Revs R")(k), inc)*1e3;
        [r, v] = propagate_orbit_j2(t, a, 0, inc, 0, 0, 0);
        h = cross(r, v, 2);
        node = unwrap(atan2(h(:, 1), -h(:, 2)));
        err(k) = (node(end) - node(1))/(t(end) - t(1))/sun_rate - 1;
    end
    [worst, k] = max(abs(err));
    verifyLessThan(tc, worst, 1e-3, sprintf('node rate / Sun rate - 1, worst row %d: %.2f km, %.3f deg', ...
        k, T.Altitude_km(k), T.SSO_Incl_deg(k)));
end

function test_gmst_is_the_one_of_end003(tc)
    % END-003 star_attitude_propagation_star>gmst_rad: deg2rad(mod(280.46061837 + 360.98564736629 d, 360))
    d = days(datetime(2026, 1, 1) + hours(0:7:24*365) - datetime(2000, 1, 1, 12, 0, 0))';
    g001 = gmst_iau82(d);
    g003 = deg2rad(mod(280.46061837 + 360.98564736629*d, 360));
    dg = abs(mod(g001 - g003 + pi, 2*pi) - pi);
    verifyLessThan(tc, max(dg), 1e-6, 'GMST of END-001 and END-003 (1e-6 rad = 7 m at 7000 km)');
end

function test_ephemeris_as_end003_reads_it(tc)
    out = fullfile(tc.TestData.work, 'eph');
    mkdir(out);
    a = 6378137.0 + [550e3, 700e3]; inc = [97.6, 53]; raan = [10, 200]; nu = [0, 90];
    epoch = datetime(2026, 5, 21, 13, 41, 0);
    files = export_downstream_ephemeris(out, a, inc, raan, nu, datevec(epoch), epoch, 1, 10);
    verifyEqual(tc, numel(files), 2);
    mu = 398600.4418;
    for k = 1:2
        verifyEqual(tc, char(files(k)), fullfile(out, sprintf('satellite_%02d_ephemeris.csv', k)));
        opts = detectImportOptions(files(k), 'Delimiter', ',', 'FileType', 'text');
        opts = setvartype(opts, 'time_utc', 'string');
        E = readtable(files(k), opts);
        verifyEqual(tc, E.Properties.VariableNames(1:7), {'time_utc', 'x_eci_km', 'y_eci_km', 'z_eci_km', ...
            'vx_eci_km_s', 'vy_eci_km_s', 'vz_eci_km_s'}, 'columns END-003 reads');
        ts = datetime(replace(erase(E.time_utc, "Z"), "T", " "), 'InputFormat', 'yyyy-MM-dd HH:mm:ss');
        verifyEqual(tc, ts(1), epoch);
        verifyEqual(tc, unique(seconds(diff(ts))), 10, 'uniform 10 s step');
        r = [E.x_eci_km, E.y_eci_km, E.z_eci_km];
        v = [E.vx_eci_km_s, E.vy_eci_km_s, E.vz_eci_km_s];
        verifyEqual(tc, vecnorm(r, 2, 2), a(k)/1e3*ones(height(E), 1), 'AbsTol', 2e-6, 'circular radius');
        % velocity = d r / dt (5-point stencil on the 10 s grid, inner rows)
        i = (3:height(E) - 2)';
        dr = (r(i - 2, :) - 8*r(i - 1, :) + 8*r(i + 1, :) - r(i + 2, :))/(12*10);
        verifyLessThan(tc, max(vecnorm(v(i, :) - dr, 2, 2)), 1e-6, 'velocity is the derivative of the positions');
        verifyEqual(tc, vecnorm(v, 2, 2), sqrt(mu/(a(k)/1e3))*ones(height(E), 1), 'RelTol', 3e-3);
        % +Z body (quaternion body -> ECI, scalar first) points to the geocentric nadir
        q = [E.qw_body2eci, E.qx_body2eci, E.qy_body2eci, E.qz_body2eci];
        z = [2*(q(:,2).*q(:,4) + q(:,1).*q(:,3)), 2*(q(:,3).*q(:,4) - q(:,1).*q(:,2)), 1 - 2*(q(:,2).^2 + q(:,3).^2)];
        verifyLessThan(tc, max(vecnorm(z + r./vecnorm(r, 2, 2), 2, 2)), 1e-8, '+Z body to nadir');
    end
end

%% =========================================================================
%  HELPERS
%  =========================================================================
function verify_check(tc, k)
    % [k] header of the harness output, then its first PASS / FAIL line
    L = strtrim(tc.TestData.harness);
    i = find(startsWith(L, sprintf('[%d] ', k)), 1);
    verifyNotEmpty(tc, i, sprintf('check [%d] not printed by validate_end001_changes', k));
    if isempty(i), return; end
    j = i + find(contains(L(i + 1:end), ["PASS", "FAIL"]), 1);
    verifyNotEmpty(tc, j, sprintf('no result for check [%d]', k));
    if isempty(j), return; end
    verifyTrue(tc, startsWith(L{j}, 'PASS'), sprintf('%s  ->  %s', L{i}, L{j}));
end

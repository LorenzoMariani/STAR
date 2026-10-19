function tests = test_end003_attitude
%TEST_END003_ATTITUDE  Checks of END-003 (STAR version) against analytical cases (2026-10-19).
%
%   From END003-AttitudePropagation:   results = runtests('tests/test_end003_attitude.m')
%
%   Disturbance torques (end003_disturbance_torques.m) against closed-form cases:
%     gravity gradient of a body pitched by theta: (3 mu / 2 r^3) (Ix - Iz) sin(2 theta) about Y, zero (not
%     ~1e-22) in the equilibrium; SRP and drag on a known lever arm; Earth shadow; worst case over all attitudes.
%   Nadir guidance law, on a synthetic END-001 ephemeris (circular orbit with J2 nodal precession) where the
%     rate of the nadir frame is known: omega = orbital rate about the orbit axis (-Y) plus the turn of the
%     orbital plane (about Z), no X component.
%   PD control with the wheel limits, on the same ephemeris: pointing error of the order of the attitude
%     knowledge error within the wheel limits; with weak wheels the torque and momentum limits hold.
    tests = functiontests(localfunctions);
end

function setupOnce(tc)
    tc.TestData.root = fileparts(fileparts(mfilename('fullpath')));
    addpath(tc.TestData.root);
    tc.TestData.work = tempname;
    mkdir(tc.TestData.work);
    tc.TestData.O = synthetic_orbit();
    tc.TestData.input = write_end001_inputs(tc.TestData.work, tc.TestData.O);
end

function teardownOnce(tc)
    rmpath(tc.TestData.root);
    if isfolder(tc.TestData.work), rmdir(tc.TestData.work, 's'); end
end

%% =========================================================================
%  DISTURBANCE TORQUES
%  =========================================================================
function test_gravity_gradient_against_pitch_formula(tc)
    S = torque_settings();
    r = [7000e3; 0; 0]; v = [0; 7546; 0];
    k = 3*S.mu/norm(r)^3;
    for th = deg2rad([0 10 30 45 60 90 135])
        [M, Mmax] = end003_disturbance_torques(r, v, Ry(th), [0; 1; 0], 0, S);
        expected = [0; 0.5*k*(S.Ivec(1) - S.Ivec(3))*sin(2*th); 0];
        verifyEqual(tc, M(:, 1), expected, 'AbsTol', 1e-12*Mmax(1));
    end
    verifyEqual(tc, Mmax(1), 0.5*k*(max(S.Ivec) - min(S.Ivec)), 'RelTol', 1e-14);
end

function test_gravity_gradient_equilibrium_is_zero(tc)
    % nadir pointing with the principal axes on the orbital frame: no torque, also after the rounding of the attitude
    S = torque_settings();
    r = [4100e3; -3900e3; 4200e3]; v = [-3.1e3; 2.2e3; 5.1e3];
    z = -r/norm(r); x = v - dot(v, z)*z; x = x/norm(x); y = cross(z, x);
    q = quat_from_axes([x y z]);
    M = end003_disturbance_torques(r, v, quat_dcm(q), [1; 0; 0], 0, S);
    verifyEqual(tc, M(:, 1), zeros(3, 1));
end

function test_gravity_gradient_never_exceeds_worst_case(tc)
    S = torque_settings();
    rng(7);
    r = [0; 6900e3; 0]; v = [-7600; 0; 0];
    for i = 1:200
        q = randn(4, 1); q = q/norm(q);
        [M, Mmax] = end003_disturbance_torques(r, v, quat_dcm(q), [1; 0; 0], 0, S);
        verifyLessThanOrEqual(tc, norm(M(:, 1)), Mmax(1)*(1 + 1e-12));
    end
end

function test_srp_on_lever_arm_and_in_shadow(tc)
    S = torque_settings();
    S.r_cp = [0.1; 0; 0];
    r = [7000e3; 0; 0]; v = [0; 7546; 0];
    F = S.P_sun*S.A_ref*S.Cr;
    [M, Mmax] = end003_disturbance_torques(r, v, eye(3), [0; 1; 0], 0, S);       % Sun along +Y: force along -Y
    verifyEqual(tc, M(:, 2), [0; 0; -0.1*F], 'RelTol', 1e-12);
    verifyEqual(tc, Mmax(2), 0.1*F, 'RelTol', 1e-14);
    [M, Mmax] = end003_disturbance_torques(r, v, eye(3), [-1; 0; 0], 0, S);      % behind the Earth
    verifyEqual(tc, M(:, 2), zeros(3, 1));
    verifyEqual(tc, Mmax(2), 0);
end

function test_drag_on_lever_arm(tc)
    S = torque_settings();
    S.r_cp = [0.1; 0; 0];
    r = [7000e3; 0; 0]; v = [0; 7546; 0]; rho = 1e-12;
    vr = 7546 - 7.2921150e-5*7000e3;                                              % co-rotating atmosphere
    q_v2 = 0.5*rho*S.Cd*S.A_ref*vr^2;
    [M, Mmax] = end003_disturbance_torques(r, v, eye(3), [0; 1; 0], rho, S);
    verifyEqual(tc, M(:, 4), [0; 0; -0.1*q_v2], 'RelTol', 1e-12);
    verifyEqual(tc, Mmax(3), 0.1*q_v2, 'RelTol', 1e-12);
end

function test_models_switched_off_keep_the_worst_case(tc)
    S = torque_settings();
    S.flags = struct('gg', false, 'srp', false, 'drag', false);
    [M, Mmax] = end003_disturbance_torques([7000e3; 0; 0], [0; 7546; 0], Ry(0.3), [0; 1; 0], 1e-12, S);
    verifyEqual(tc, M, zeros(3, 6));
    verifyTrue(tc, all(Mmax > 0));
end

%% =========================================================================
%  NADIR GUIDANCE LAW
%  =========================================================================
function test_nadir_rate_is_orbital_rate_plus_plane_turn(tc)
    O = tc.TestData.O;
    out = run_end003(tc, 'nadir_ideal', 'nadir', struct('enabled', false), struct('gg', true, 'srp', false, 'drag', false));
    [t, w] = read_aem_rates(fullfile(out, 'output_attitude_propagation'), 'imaging', O.epoch);
    w_true = true_nadir_rate(O, t);
    verifyLessThan(tc, max(abs(w - w_true), [], 'all'), 3e-9, 'AEM body rate vs the rate of the nadir frame');
    % n x (orbit axis): no X component, -|h|/r^2 on Y; the Z component is the turn of the orbital plane, which the
    % law before 2026-10-19 left out (it would fail the check above by this much)
    [r, v] = orbit_rv(O, t);
    verifyLessThan(tc, max(abs(w(:, 1))), 3e-9);
    verifyEqual(tc, w(:, 2), -vecnorm(cross(r, v, 2), 2, 2)./vecnorm(r, 2, 2).^2, 'AbsTol', 3e-9);
    verifyGreaterThan(tc, max(abs(w_true(:, 3))), 1e-7);
    % ideal nadir is a gravity-gradient equilibrium: the mean GG torque is 0, not the ~1e-22 rounding
    K = read_kpis(out);
    verifyEqual(tc, K('KPI-11'), 0);
    verifyEqual(tc, K('KPI-29'), 1.5*O.mu/O.a^3*(0.125 - 0.0691), 'RelTol', 1e-9);
end

%% =========================================================================
%  PD CONTROL WITH WHEEL LIMITS
%  =========================================================================
function test_pd_control_tracks_nadir_within_wheel_limits(tc)
    ctrl = struct('enabled', true, 'wheel_momentum_Nms', 0.1, 'wheel_torque_Nm', 0.006, ...
        'attitude_knowledge_deg', 0.00694, 'rate_noise_rad_s', 1e-5);
    out = run_end003(tc, 'nadir_pd', 'nadir', ctrl, struct('gg', true, 'srp', true, 'drag', true));
    K = read_kpis(out);
    verifyTrue(tc, logical(K('KPI-22')));
    % closed loop with white knowledge noise: the error is a fraction of the knowledge error (bandwidth 0.1 rad/s
    % against the 1 Hz measurements), not zero as in the ideal attitude
    verifyGreaterThan(tc, K('KPI-23'), 0);
    verifyLessThan(tc, K('KPI-23'), 0.00694);
    verifyLessThan(tc, K('KPI-24'), 5*0.00694);
    verifyLessThan(tc, K('KPI-26'), 100);
    verifyLessThan(tc, K('KPI-27'), 100);
    verifyEqual(tc, K('KPI-28'), 0);
    % disturbances of the controlled attitude: positive and below the worst case
    for p = {{'KPI-11', 'KPI-29'}, {'KPI-12', 'KPI-30'}, {'KPI-13', 'KPI-31'}}
        verifyGreaterThan(tc, K(p{1}{1}), 0);
        verifyLessThan(tc, K(p{1}{1}), K(p{1}{2}));
    end
    csv = readtable(fullfile(out, 'output_attitude_propagation', 'output_attitude_propagation.csv'));
    verifyLessThan(tc, max(csv.nadir_offset_deg), 5*0.00694);
    verifyTrue(tc, isfile(fullfile(out, 'results_attitude_propagator', '08_attitude_control.png')));
    % guided attitude (2026-10-19): no 07 B and no 03, the 3D orbit in one figure
    verify_figures(tc, out, {'01_telemetry', '02_tracking', '04_ground_track', '05_orbit_3d', '08_attitude_control', ...
        '07_aem_imaging_A_inertial_view', '07_aem_imaging_C_H_orbital_plane', '07_aem_imaging_D_parameters'}, ...
        {'03_angular_momentum', '05_orbit_3d_ecef', '06_orbit_3d_eci', '07_aem_imaging_B_view_along_H'});
end

function test_free_motion_keeps_the_figures_of_the_rotation(tc)
    % 'dynamics' (free motion, no control): 07 B (view along H) and 03 (angular momentum) are drawn
    out = run_end003(tc, 'free', 'dynamics', struct('enabled', false), struct('gg', true, 'srp', false, 'drag', false));
    verify_figures(tc, out, {'03_angular_momentum', '05_orbit_3d', '07_aem_imaging_A_inertial_view', ...
        '07_aem_imaging_B_view_along_H'}, {'06_orbit_3d_eci', '08_attitude_control'});
end

function test_weak_wheels_hold_their_limits(tc)
    ctrl = struct('enabled', true, 'wheel_momentum_Nms', 5e-4, 'wheel_torque_Nm', 1e-5, ...
        'attitude_knowledge_deg', 0.00694, 'rate_noise_rad_s', 1e-5);
    out = run_end003(tc, 'follow_weak', 'follow_site', ctrl, struct('gg', true, 'srp', false, 'drag', false));
    K = read_kpis(out);
    verifyLessThanOrEqual(tc, K('KPI-27'), 100 + 1e-9);
    verifyLessThanOrEqual(tc, K('KPI-26'), 100 + 1e-9);
    verifyGreaterThan(tc, K('KPI-28'), 0);
    verifyGreaterThan(tc, K('KPI-24'), 1, 'the slews towards the site cannot be followed with these wheels');
end

function test_magnetorquers_dump_the_wheel_momentum(tc)
    % wheels starting at 0.02 N m s per axis, no disturbance torque but the gravity gradient of the controlled attitude:
    % without dumping the stored momentum stays (it only turns in the body frame), the magnetorquers take most of it out
    O = tc.TestData.O;
    base = struct('enabled', true, 'wheel_momentum_Nms', 0.1, 'wheel_torque_Nm', 0.006, 'attitude_knowledge_deg', 0.00694, ...
        'rate_noise_rad_s', 1e-5, 'initial_wheel_momentum_Nms', [0.02 0.02 0.02]);
    flags = struct('gg', true, 'srp', false, 'drag', false);
    off = base; off.momentum_dumping = false;
    K_off = read_kpis(run_end003(tc, 'dump_off', 'nadir', off, flags));
    out_on = run_end003(tc, 'dump_on', 'nadir', base, flags);
    K_on = read_kpis(out_on);
    h0_pct = 100*norm([0.02 0.02 0.02])/0.1;
    verifyEqual(tc, K_off('KPI-33'), h0_pct, 'RelTol', 0.02, 'without dumping the wheel momentum is kept');
    verifyLessThan(tc, K_on('KPI-33'), 0.3*h0_pct, 'the magnetorquers dump the wheel momentum');
    verifyGreaterThan(tc, K_on('KPI-32'), 0);
    verifyLessThanOrEqual(tc, K_on('KPI-32'), 100 + 1e-9);
    % no dipole from END-006: the END-006 sizing rule, a full wheel dumped in one orbit, H / (B T)
    s = read_summary(out_on);
    m_rule = 0.1/(3.12e-5*(6378137.0/O.a)^3*2*pi*sqrt(O.a^3/O.mu));
    verifyEqual(tc, s.attitude_control.magnetorquer_dipole_Am2, m_rule, 'RelTol', 1e-6);
    verifySubstring(tc, s.attitude_control.magnetorquer_source, 'END-006 sizing rule');
end

%% =========================================================================
%  HELPERS
%  =========================================================================
function S = torque_settings()
    S.mu = 3.986004415e14; S.Re = 6378137.0; S.P_sun = 4.56e-6;
    S.Ivec = [0.125; 0.125; 0.0691]; S.I = diag(S.Ivec);
    S.A_ref = 0.108; S.Cr = 1.2; S.Cd = 2.2; S.r_cp = [0.002; 0.002; 0.005];
    S.flags = struct('gg', true, 'srp', true, 'drag', true);
end

function R = Ry(a)
    R = [cos(a) 0 sin(a); 0 1 0; -sin(a) 0 cos(a)];
end

function A = quat_dcm(q)
    x = q(1); y = q(2); z = q(3); w = q(4);
    A = [1-2*(y^2+z^2) 2*(x*y-z*w) 2*(x*z+y*w); 2*(x*y+z*w) 1-2*(x^2+z^2) 2*(y*z-x*w); 2*(x*z-y*w) 2*(y*z+x*w) 1-2*(x^2+y^2)];
end

function q = quat_from_axes(R)
    w = 0.5*sqrt(1 + trace(R));
    q = [(R(3,2) - R(2,3))/(4*w); (R(1,3) - R(3,1))/(4*w); (R(2,1) - R(1,2))/(4*w); w];
end

function O = synthetic_orbit()
    % Circular orbit at 600 km, 53 deg, with the J2 nodal precession: r(t), v(t) and the nadir frame are known exactly.
    O.mu = 3.986004415e14; Re = 6378137.0; J2 = 1.08262668e-3;
    O.a = Re + 600e3; O.inc = deg2rad(53); O.raan0 = deg2rad(30);
    O.n = sqrt(O.mu/O.a^3);
    O.raan_dot = -1.5*O.n*J2*(Re/O.a)^2*cos(O.inc);
    O.epoch = datetime(2026, 5, 21, 12, 0, 0);
    O.hours = 3;
    O.t_peak = round(2*pi/O.n);                       % one revolution: over the equator, largest plane-turn rate
end

function [r, v] = orbit_rv(O, t)
    t = t(:); u = O.n*t; W = O.raan0 + O.raan_dot*t;
    ci = cos(O.inc); si = sin(O.inc);
    xp = O.a*cos(u); yp = O.a*sin(u)*ci; zp = O.a*sin(u)*si;
    r = [cos(W).*xp - sin(W).*yp, sin(W).*xp + cos(W).*yp, zp];
    dxp = -O.a*O.n*sin(u); dyp = O.a*O.n*cos(u)*ci; dzp = O.a*O.n*cos(u)*si;
    v = [cos(W).*dxp - sin(W).*dyp, sin(W).*dxp + cos(W).*dyp, dzp] + O.raan_dot*[-r(:, 2), r(:, 1), zeros(size(t))];
end

function w = true_nadir_rate(O, t)
    % Body rate of the nadir frame (+Z = -r, +X along the velocity, +Y = Z x X) by central differences of the
    % exact frame: wx = dY/dt . Z, wy = dZ/dt . X, wz = dX/dt . Y.
    d = 1e-2;
    w = zeros(numel(t), 3);
    for k = 1:numel(t)
        F = nadir_frame(O, t(k));
        dF = (nadir_frame(O, t(k) + d) - nadir_frame(O, t(k) - d))/(2*d);
        w(k, :) = [dF(:, 2)'*F(:, 3), dF(:, 3)'*F(:, 1), dF(:, 1)'*F(:, 2)];
    end
end

function F = nadir_frame(O, t)
    [r, v] = orbit_rv(O, t);
    z = -r'/norm(r); x = v' - (v*z)*z; x = x/norm(x); y = cross(z, x);
    F = [x y z];
end

function in = write_end001_inputs(work, O)
    % END-001 ephemeris (10 s, ECI km and km/s) and pass_selection.json with the imaging pass over the
    % sub-satellite point at O.t_peak (equator crossing).
    t = (0:10:O.hours*3600)';
    [r, v] = orbit_rv(O, t);
    in.eph = fullfile(work, 'satellite_01_ephemeris.csv');
    fid = fopen(in.eph, 'w');
    fprintf(fid, 'time_utc,x_eci_km,y_eci_km,z_eci_km,vx_eci_km_s,vy_eci_km_s,vz_eci_km_s\n');
    ts = string(O.epoch + seconds(t), 'yyyy-MM-dd''T''HH:mm:ss''Z''');
    for k = 1:numel(t)
        fprintf(fid, '%s,%.9f,%.9f,%.9f,%.12f,%.12f,%.12f\n', ts(k), r(k, :)/1e3, v(k, :)/1e3);
    end
    fclose(fid);
    rp = orbit_rv(O, O.t_peak);
    th = deg2rad(mod(280.46061837 + 360.98564736629*(juliandate(O.epoch + seconds(O.t_peak)) - 2451545.0), 360));
    re = [cos(th)*rp(1) + sin(th)*rp(2), -sin(th)*rp(1) + cos(th)*rp(2), rp(3)];
    site = struct('name', 'test site', 'lat_deg', asind(re(3)/norm(re)), 'lon_deg', atan2d(re(2), re(1)), 'alt_m', 0, 'index', 1);
    t0 = O.t_peak - 240; t1 = O.t_peak + 240;
    utc = @(s) char(string(O.epoch + seconds(s), 'yyyy-MM-dd''T''HH:mm:ss''Z'''));
    im = struct('found', true, 'pass_found', true, 'constraint_met', true, 'satellite_index', 1, 'satellite_label', 'SAT-01', ...
        'site', site, 'start_t_s', t0, 'end_t_s', t1, 'peak_t_s', O.t_peak, 'start_utc', utc(t0), 'end_utc', utc(t1), ...
        'peak_elevation_deg', 89, 'site_sun_elevation_at_peak_deg', 30, 'site_sun_elevation_min_deg', 30, ...
        'subsatellite_sun_elevation_min_deg', 30, 'satellite_sunlit_fraction', 1, ...
        'target', struct('description', 'test site', 'n_points', 1));
    cand = struct('satellite_index', 1, 'site', 'test site', 'aos_t_s', t0, 'los_t_s', t1, 'peak_t_s', O.t_peak, ...
        'peak_elevation_deg', 89, 'site_sun_elevation_at_peak_deg', 30, 'site_sun_elevation_min_deg', 30, ...
        'subsatellite_sun_elevation_min_deg', 30, 'satellite_sunlit_fraction', 1, 'sun_constraint_ok', true, ...
        'truncated_by_window', false, 'selected', true);
    obs = struct('name', 'observer', 'site_lat_deg', 40.6492, 'site_lon_deg', 16.7039, 'site_alt_m', 400);
    P = struct('settings', struct('img', struct('elev', 10, 'sun_enabled', false, 'sun_mode', 'day', 'sun_thr', 0)), ...
        'imaging_pass', im, 'imaging_candidates', {{cand}}, ...
        'lightcurve_pass', struct('found', false, 'enabled', false, 'rule', 'first useful pass', 'observer', obs));
    in.pass = fullfile(work, 'pass_selection.json');
    fid = fopen(in.pass, 'w'); fprintf(fid, '%s', jsonencode(P)); fclose(fid);
end

function out = run_end003(tc, name, mode, control, flags)
    out = fullfile(tc.TestData.work, name);
    sat = struct('attitude_mode', mode, 'm', 8.1, 'Ix', 0.125, 'Iy', 0.125, 'Iz', 0.0691, 'A_ref', 0.108, ...
        'Cr', 1.2, 'Cd', 2.2, 'r_cp', [0.002 0.002 0.005], 'control', control);
    cfg = struct('sat', sat, 'env', struct('flags', flags), 'target', struct('elev_threshold', 10), ...
        'end001_ephemeris', {{struct('satellite_index', 1, 'file', tc.TestData.input.eph)}}, ...
        'end001_pass_selection', tc.TestData.input.pass);
    f = fullfile(tc.TestData.work, [name '.json']);
    fid = fopen(f, 'w'); fprintf(fid, '%s', jsonencode(cfg)); fclose(fid);
    evalc('star_attitude_propagation_star(f, out)');
    close all force;
end

function [t, w] = read_aem_rates(folder, key, epoch)
    d = dir(fullfile(folder, sprintf('AEM_END003_*_%s_*.xml', key)));
    txt = fileread(fullfile(folder, d(1).name));
    ep = string(cellfun(@(c) c{1}, regexp(txt, '<EPOCH>([^<]+)</EPOCH>', 'tokens'), 'UniformOutput', false))';
    t = seconds(datetime(ep, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS') - epoch);
    num = @(tag) str2double(string(cellfun(@(c) c{1}, regexp(txt, ['<' tag '>([^<]+)</' tag '>'], 'tokens'), 'UniformOutput', false)))';
    w = [num('ANGVEL_X'), num('ANGVEL_Y'), num('ANGVEL_Z')];
end

function verify_figures(tc, out, present, absent)
    res = fullfile(out, 'results_attitude_propagator');
    for f = present, verifyTrue(tc, isfile(fullfile(res, [f{1} '.png'])), [f{1} '.png expected']); end
    for f = absent, verifyFalse(tc, isfile(fullfile(res, [f{1} '.png'])), [f{1} '.png not expected']); end
end

function s = read_summary(out)
    s = jsondecode(fileread(fullfile(out, 'results_attitude_propagator', 'attitude_summary.json')));
end

function K = read_kpis(out)
    s = read_summary(out);
    k = s.kpis;
    if iscell(k), k = [k{:}]; end
    K = containers.Map();
    for i = 1:numel(k)
        v = k(i).value;
        if isempty(v), v = NaN; end
        K(k(i).id) = double(v);
    end
end

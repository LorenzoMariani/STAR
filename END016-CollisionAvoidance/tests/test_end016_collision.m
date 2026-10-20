function tests = test_end016_collision
%TEST_END016_COLLISION  Checks of END-016 (collision probability, close approaches, orbital lifetime) (2026-10-20).
%
%   From END016-CollisionAvoidance:   results = runtests('tests/test_end016_collision.m')
%
%   chan_pc (Chan, NASA CA Handbook Appendix N), against closed forms:
%     zero miss, isotropic sigma: Pc = 1 - exp(-R^2 / (2 sigma^2)) for any R;
%     R -> 0: Pc -> R^2 / (2 sigma_x sigma_y) exp(-m^2/2) (m: Mahalanobis miss), and the circumscribing square of
%     pc_upper_bound_square holds 4/pi times as much probability; invariant under a rotation of the encounter plane.
%   conjunction_plane_2d: right-handed orthonormal frame with z along the relative velocity; the miss and the Pc do not
%     change when the relative position moves along the relative velocity (straight-line encounter).
%   CARA test conjunctions (CARA_Analysis_Tools/DataFiles/PcTestCaseCDMs, 53 CDMs): chan_pc with the CDM states and
%     covariances (RTN -> ECI with rot_eci2rtc) against CARA's Pc2D column; Pc2D is the reference of the 2-D methods
%     only (Nc2D and Nc3D are those of Pc2D_Hall and Pc3D_Hall: testChan.m compared them with Pc2D).
%   star_collision_main on a synthetic constellation of exact circular two-body orbits (two satellites crossing at the
%     ascending node 0.3 km apart in radius, a third one far away): every close approach found by a 1 s scan of the
%     exact orbits and refined, with its time, miss, RTN components, relative speed and Pc (CARA PcCircle on the same
%     covariances); KPIs, pair matrix and output files.
%   star_orbit_lifetime: decay rates proportional to B = Cd A / m, so the lifetime scales as 1/B; it grows with the
%     altitude and falls with the solar activity; the disposal burn is the vis-viva difference to the lowered perigee.
    tests = functiontests(localfunctions);
end

function setupOnce(tc)
    root = fileparts(fileparts(mfilename('fullpath')));
    poc = fullfile(root, 'CARA_Analysis_Tools', 'DistributedMatlab', 'ProbabilityOfCollision');
    tc.TestData.paths = [{fullfile(root, 'lib')}, strsplit(genpath(poc), pathsep), ...
        strsplit(genpath(fullfile(root, 'CARA_Analysis_Tools', 'DistributedMatlab', 'Utils')), pathsep)];
    tc.TestData.paths = tc.TestData.paths(~cellfun(@isempty, tc.TestData.paths));
    addpath(tc.TestData.paths{:});
    tc.TestData.cdm_dir = fullfile(root, 'CARA_Analysis_Tools', 'DataFiles', 'PcTestCaseCDMs');
    tc.TestData.work = tempname;
    mkdir(tc.TestData.work);
    % synthetic constellation, run once through star_collision_main
    C = synthetic_constellation();
    base = fullfile(tc.TestData.work, 'constellation');
    write_constellation(fullfile(base, 'star_input'), C);
    cfg = struct('star_input_dir', './star_input', 'output_dir', './output', ...
        'spacecraft', struct('mass_kg', 4, 'drag_area_m2', 0.03, 'cd', 2.2), 'hard_body_radius_m', 5, ...
        'position_sigma_rtn_m', [50 200 50], 'screening_km', 10, 'pc_threshold', 1e-6, ...
        'mission_lifetime_years', 3, 'disposal_rules_years', [5 25], 'solar_f107', 140, 'reentry_km', 120);
    f = fullfile(base, 'input_collision_avoidance.json');
    write_json(f, cfg);
    S = [];
    evalc('S = star_collision_main(f);');
    tc.TestData.C = C;
    tc.TestData.cfg = cfg;
    tc.TestData.S = S;
    tc.TestData.out = fullfile(base, 'output');
end

function teardownOnce(tc)
    rmpath(tc.TestData.paths{:});
    if isfolder(tc.TestData.work), rmdir(tc.TestData.work, 's'); end
end

%% =========================================================================
function test_chan_pc_closed_forms(tc)
    sigma = 1.0;
    for R = [0.01 0.5 1 2]                                                        % zero miss, isotropic: exact for any R
        verifyEqual(tc, chan_pc([0; 0], sigma^2*eye(2), R), 1 - exp(-R^2/(2*sigma^2)), 'RelTol', 1e-8, sprintf('R = %g', R));
    end
    C = diag([0.5^2, 0.1^2]); r = [0.3; 0.05]; R = 1e-4;                         % small hard body: density x area
    m2 = r'/C*r;
    small = pi*R^2/(2*pi*sqrt(det(C)))*exp(-m2/2);
    verifyEqual(tc, chan_pc(r, C, R), small, 'RelTol', 1e-5);
    verifyEqual(tc, pc_upper_bound_square(r, C, R), 4/pi*small, 'RelTol', 1e-5);  % square of side 2R around the disc
    verifyLessThan(tc, chan_pc([2.5; 0], C, 0.01), 1e-4);                        % 5 sigma away
    verifyGreaterThan(tc, chan_pc([0; 0], 0.001^2*eye(2), 0.1), 0.99);          % hard body of 100 sigma
    verifyEqual(tc, chan_pc(r, C, 0), 0);
end

function test_chan_pc_rotation_invariance_and_upper_bound(tc)
    rng(16);
    for k = 1:20
        A = randn(2); C = A*A' + 0.01*eye(2); r = randn(2, 1); R = 0.05 + 0.5*rand;
        th = 2*pi*rand; Q = [cos(th) -sin(th); sin(th) cos(th)];
        pc = chan_pc(r, C, R);
        verifyEqual(tc, chan_pc(Q*r, Q*C*Q', R), pc, 'RelTol', 1e-8, sprintf('case %d', k));
        verifyGreaterThanOrEqual(tc, pc_upper_bound_square(r, C, R), pc*(1 - 1e-10), sprintf('case %d', k));
    end
end

function test_conjunction_plane(tc)
    rng(17);
    for k = 1:10
        r = randn(3, 1); v = randn(3, 1); A = randn(3); P = A*A';
        [r2, C2, Rm] = conjunction_plane_2d(r, v, P);
        id = sprintf('case %d', k);
        verifyEqual(tc, Rm*Rm', eye(3), 'AbsTol', 1e-12, id);
        verifyEqual(tc, det(Rm), 1, 'AbsTol', 1e-12, id);
        verifyEqual(tc, Rm(3, :)', v/norm(v), 'AbsTol', 1e-12, id);
        verifyEqual(tc, norm(r2), norm(r - (r'*v)/(v'*v)*v), 'RelTol', 1e-12, id);    % miss across the relative velocity
        Pc3 = Rm*P*Rm';
        verifyEqual(tc, C2, Pc3(1:2, 1:2), 'AbsTol', 1e-12, id);
        [r2s, C2s] = conjunction_plane_2d(r + 0.7*v, v, P);                       % same straight line, other instant
        verifyEqual(tc, chan_pc(r2s, C2s, 0.3), chan_pc(r2, C2, 0.3), 'RelTol', 1e-10, id);
    end
    M = rot_eci2rtc([7000; 0; 0], [0; 7.5; 0.1]);                                 % radial, in-track, cross-track
    verifyEqual(tc, M*M', eye(3), 'AbsTol', 1e-15);
    verifyEqual(tc, M(1, :), [1 0 0], 'AbsTol', 1e-15);
    verifyEqual(tc, M(3, :), cross([7000 0 0], [0 7.5 0.1])/norm(cross([7000 0 0], [0 7.5 0.1])), 'AbsTol', 1e-15);
end

function test_chan_pc_on_the_cara_test_conjunctions(tc)
    T = readtable(fullfile(tc.TestData.cdm_dir, 'CARA_PcMethod_Test_Conjunctions.xlsx'));
    verifyEqual(tc, height(T), 53);
    pc = nan(height(T), 1);
    for k = 1:height(T)
        cdm = parseCDMcara(fullfile(tc.TestData.cdm_dir, [T.Conjunction_ID{k} '.cdm']));
        [r1, v1, P1] = cdm_object(cdm.Objects(1));
        [r2, v2, P2] = cdm_object(cdm.Objects(2));
        [r2d, C2d] = conjunction_plane_2d(r2 - r1, v2 - v1, P1(1:3, 1:3) + P2(1:3, 1:3));
        pc(k) = chan_pc(r2d, C2d, cdm.Header.CommentFields.HBR.Value);
    end
    % from 3.9e-168 to 2.1e-2; Pc2D is computed at the TCA adjusted to the states, the encounter plane makes chan_pc
    % independent of it
    verifyEqual(tc, pc, T.Pc2D, 'RelTol', 1e-6);
end

function test_close_approaches_of_the_synthetic_constellation(tc)
    C = tc.TestData.C; S = tc.TestData.S; cfg = tc.TestData.cfg;
    expected = scan_pair(C(1), C(2), C(1).t, cfg.screening_km);
    ev = events_of(S);
    verifyEqual(tc, numel(ev), numel(expected), 'every close approach below the screening distance');
    verifyGreaterThanOrEqual(tc, numel(expected), 3);
    sig = cfg.position_sigma_rtn_m/1e3; hbr = cfg.hard_body_radius_m/1e3;
    for k = 1:min(numel(ev), numel(expected))
        e = ev(k); x = expected(k);
        id = sprintf('event %d', k);
        verifyEqual(tc, e.pair, 'SAT-01 - SAT-02', id);
        tca = seconds(datetime(e.tca_utc, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss.SSS''Z''', 'TimeZone', 'UTC') - C(1).t0);
        verifyEqual(tc, tca, x.t, 'AbsTol', 2e-3, id);                         % TCA written to the millisecond
        verifyEqual(tc, e.miss_km, x.miss, 'AbsTol', 1e-7, id);
        M = rot_eci2rtc(x.r1', x.v1');
        verifyEqual(tc, [e.radial_km e.intrack_km e.crosstrack_km], (M*(x.r2 - x.r1)')', 'AbsTol', 1e-4, id);
        verifyEqual(tc, e.rel_speed_km_s, norm(x.v2 - x.v1), 'RelTol', 1e-6, id);
        P1 = M'*diag(sig.^2)*M; M2 = rot_eci2rtc(x.r2', x.v2'); P2 = M2'*diag(sig.^2)*M2;
        verifyEqual(tc, e.pc, PcCircle(x.r1, x.v1, P1, x.r2, x.v2, P2, hbr), 'RelTol', 1e-4, id);
        verifyGreaterThanOrEqual(tc, e.pc_upper_bound, e.pc, id);
        % at the TCA the miss is across the relative velocity: it is the miss in the encounter plane
        verifyEqual(tc, e.pc_max, pc_max_grid(x.miss, hbr), 'RelTol', 1e-6, id);
        verifyGreaterThanOrEqual(tc, e.pc_max, e.pc, id);
        verifyEqual(tc, e.alt_km, norm(x.r1) - 6378.137, 'AbsTol', 1e-3, id);
    end
    verifyEqual(tc, ev(1).lat_deg, 0, 'AbsTol', 1e-3);                            % the first one is at the ascending node
    verifyEqual(tc, ev(1).miss_km, 0.3, 'AbsTol', 1e-3);
end

function test_kpis_pair_matrix_and_files(tc)
    C = tc.TestData.C; S = tc.TestData.S; out = tc.TestData.out;
    ev = events_of(S);
    kp = S.kpis;
    verifyEqual(tc, [kp.n_satellites kp.n_pairs], [3 3]);
    verifyEqual(tc, kp.min_separation_km, min([ev.miss_km]), 'AbsTol', 1e-12);
    verifyEqual(tc, kp.min_separation_pair, 'SAT-01 - SAT-02');
    verifyEqual(tc, kp.n_events_below_screening, numel(ev));
    verifyEqual(tc, kp.n_events_below_1km, nnz([ev.miss_km] < 1));
    verifyEqual(tc, kp.max_pc, max([ev.pc]));
    verifyEqual(tc, kp.n_events_above_pc_threshold, nnz([ev.pc] > tc.TestData.cfg.pc_threshold));
    D = S.pair_min_distance_km;
    verifyEqual(tc, D, D');
    verifyTrue(tc, all(isnan(diag(D))));
    for p = [1 3; 2 3]'
        x = scan_pair(C(p(1)), C(p(2)), C(1).t, Inf);
        verifyEqual(tc, D(p(1), p(2)), min([x.miss]), 'AbsTol', 1e-4, sprintf('SAT-%02d - SAT-%02d', p));
        verifyGreaterThan(tc, D(p(1), p(2)), 10);
    end
    for f = {'intra_pair_min_distance.csv', 'intra_close_approaches.csv', 'disposal_lifetime.csv', 'space_safety_summary.json'}
        verifyTrue(tc, isfile(fullfile(out, f{1})), f{1});
    end
    E = readtable(fullfile(out, 'intra_close_approaches.csv'), 'TextType', 'string');
    verifyEqual(tc, height(E), numel(ev));
    verifyEqual(tc, E.miss_km, [ev.miss_km]', 'AbsTol', 1e-6);
    L = readtable(fullfile(out, 'disposal_lifetime.csv'));
    verifyEqual(tc, height(L), 3);                                                % three shells, one solar level
    J = jsondecode(fileread(fullfile(out, 'space_safety_summary.json')));
    verifyEqual(tc, J.kpis.n_events_below_screening, numel(ev));
end

function test_orbital_lifetime(tc)
    B = 2.2*0.03/4;
    base = star_orbit_lifetime(450, 97.6, B, 140, struct());
    double_B = star_orbit_lifetime(450, 97.6, 2*B, 140, struct());
    verifyEqual(tc, base.passive_years/double_B.passive_years, 2, 'RelTol', 1e-4);   % rates proportional to B
    verifyEqual(tc, double_B.drag_dv_m_s_per_year, 2*base.drag_dv_m_s_per_year, 'RelTol', 1e-12);
    verifyGreaterThan(tc, star_orbit_lifetime(450, 97.6, B, 70, struct()).passive_years, base.passive_years);
    verifyLessThan(tc, star_orbit_lifetime(450, 97.6, B, 220, struct()).passive_years, base.passive_years);
    verifyGreaterThan(tc, star_orbit_lifetime(500, 97.6, B, 140, struct()).passive_years, base.passive_years);
    verifyEqual(tc, base.curve_alt_km(1), 450, 'AbsTol', 1e-9);
    verifyLessThanOrEqual(tc, base.curve_alt_km(end), 120 + 1);                  % the decay ends at the re-entry
    verifyTrue(tc, all(diff(base.curve_alt_km) <= 0));
    % disposal: none where the passive lifetime complies; otherwise a perigee-lowering burn at 450 km
    rule = base.passive_years/2;
    L = star_orbit_lifetime(450, 97.6, B, 140, struct('rules_years', [rule 2*base.passive_years]));
    verifyEqual(tc, [L.disposal_dv_m_s(2) L.disposal_perigee_km(2)], [0 450]);
    mu = 398600.4418e9; Re = 6378137; r0 = Re + 450e3; a = (r0 + Re + L.disposal_perigee_km(1)*1e3)/2;
    verifyGreaterThan(tc, L.disposal_perigee_km(1), 120);
    verifyLessThan(tc, L.disposal_perigee_km(1), 450);
    verifyEqual(tc, L.disposal_dv_m_s(1), sqrt(mu/r0) - sqrt(mu*(2/r0 - 1/a)), 'RelTol', 1e-12);
end

function test_invalid_inputs(tc)
    verifyError(tc, @() star_collision_main(fullfile(tc.TestData.work, 'missing.json')), 'star_collision_main:config');
    base = fullfile(tc.TestData.work, 'no_ephemeris');
    C = synthetic_constellation();
    write_constellation(fullfile(base, 'star_input'), C(1:2));
    delete(fullfile(base, 'star_input', 'satellite_02_ephemeris.csv'));
    f = fullfile(base, 'input.json');
    write_json(f, struct('star_input_dir', './star_input', 'output_dir', './output'));
    verifyError(tc, @() run_quiet(f), 'star_collision_main:input');
    empty = fullfile(tc.TestData.work, 'empty');
    mkdir(empty);
    f = fullfile(empty, 'input.json');
    write_json(f, struct('star_input_dir', '.', 'output_dir', './output'));
    verifyError(tc, @() run_quiet(f), 'star_collision_main:input');
end

%% =========================================================================
%  HELPERS
%  =========================================================================
function C = synthetic_constellation()
    % exact circular two-body orbits on a 10 s grid over 3 h; SAT-01 and SAT-02 pass their common ascending node
    % (RAAN 0, inclinations 97.6 and 97.0 deg) together at t = 1800 s, 0.3 km apart in radius; SAT-03 is far away
    mu = 398600.4418; Re = 6378.137;
    t0 = datetime(2026, 5, 21, 12, 0, 0, 'TimeZone', 'UTC');
    t = (0:10:3*3600)';
    def = [550 97.6 0; 550.3 97.0 0; 800 53 90];                                % alt km, incl deg, RAAN deg
    for k = 1:3
        a = Re + def(k, 1); n = sqrt(mu/a^3);
        C(k).alt = def(k, 1); C(k).incl = def(k, 2); C(k).raan = def(k, 3);
        C(k).a = a; C(k).n = n; C(k).u0 = -n*1800;
        if k == 3, C(k).u0 = 2.0; end
        C(k).t0 = t0; C(k).t = t;
        [C(k).r, C(k).v] = circular_state(C(k), t);
    end
end

function [r, v] = circular_state(o, t)
    u = o.u0 + o.n*t(:); cO = cosd(o.raan); sO = sind(o.raan); ci = cosd(o.incl); si = sind(o.incl);
    r = o.a*[cO*cos(u) - sO*sin(u)*ci, sO*cos(u) + cO*sin(u)*ci, sin(u)*si];
    v = o.a*o.n*[-cO*sin(u) - sO*cos(u)*ci, -sO*sin(u) + cO*cos(u)*ci, cos(u)*si];
end

function write_constellation(folder, C)
    % satellite_NN.json and satellite_NN_ephemeris.csv as END-001 writes them
    if ~isfolder(folder), mkdir(folder); end
    for k = 1:numel(C)
        o = C(k);
        write_json(fullfile(folder, sprintf('satellite_%02d.json', k)), struct('orbit', struct( ...
            'alt_perigee_m', o.alt*1e3, 'alt_apogee_m', o.alt*1e3, 'inclination_deg', o.incl, 'raan_deg', o.raan, ...
            'omega_deg', 0, 'nu_deg', mod(rad2deg(o.u0), 360))));
        fid = fopen(fullfile(folder, sprintf('satellite_%02d_ephemeris.csv', k)), 'w');
        fprintf(fid, 'time_utc,x_eci_km,y_eci_km,z_eci_km,vx_eci_km_s,vy_eci_km_s,vz_eci_km_s\n');
        ts = string(o.t0 + seconds(o.t), 'yyyy-MM-dd''T''HH:mm:ss''Z''');
        for j = 1:numel(o.t)
            fprintf(fid, '%s,%.9f,%.9f,%.9f,%.12f,%.12f,%.12f\n', ts(j), o.r(j, :), o.v(j, :));
        end
        fclose(fid);
    end
end

function x = scan_pair(a, b, t, scr_km)
    % local minima of the exact distance on a 1 s scan, refined; those below scr_km and inside the window
    d = @(tq) norm(circular_state(b, tq) - circular_state(a, tq));
    ts = (t(1):1:t(end))';
    dd = vecnorm(circular_state(b, ts) - circular_state(a, ts), 2, 2);
    k = find(dd(2:end-1) <= dd(1:end-2) & dd(2:end-1) <= dd(3:end)) + 1;
    x = struct('t', {}, 'miss', {}, 'r1', {}, 'v1', {}, 'r2', {}, 'v2', {});
    for c = k(:)'
        [tm, dm] = fminbnd(d, ts(c - 1), ts(c + 1), optimset('TolX', 1e-7));
        if dm < scr_km && tm > t(1) + 10 && tm < t(end) - 10
            [r1, v1] = circular_state(a, tm); [r2, v2] = circular_state(b, tm);
            x(end + 1) = struct('t', tm, 'miss', dm, 'r1', r1, 'v1', v1, 'r2', r2, 'v2', v2); %#ok<AGROW>
        end
    end
    if ~isempty(x)
        [~, o] = sort([x.miss]); x = x(o);
    end
end

function ev = events_of(S)
    ev = S.events;
    if iscell(ev), ev = [ev{:}]; end
end

function pm = pc_max_grid(d, R)
    % largest P(|d + sigma xi| <= R) over a dense grid of sigma
    s = d*logspace(-3, 2, 200001);
    pm = max(0.5*erfc(-(R - d)./(s*sqrt(2))) - 0.5*erfc(-(-R - d)./(s*sqrt(2))));
end

function [r, v, P] = cdm_object(o)
    % ECI state [m, m/s] and 6x6 covariance of one CDM object (CDM covariance in RTN)
    r = [o.X.Value; o.Y.Value; o.Z.Value]*1e3;
    v = [o.X_DOT.Value; o.Y_DOT.Value; o.Z_DOT.Value]*1e3;
    f = @(n) o.(n).Value;
    C = [f('CR_R')    f('CT_R')    f('CN_R')    f('CRDOT_R')    f('CTDOT_R')    f('CNDOT_R');
         f('CT_R')    f('CT_T')    f('CN_T')    f('CRDOT_T')    f('CTDOT_T')    f('CNDOT_T');
         f('CN_R')    f('CN_T')    f('CN_N')    f('CRDOT_N')    f('CTDOT_N')    f('CNDOT_N');
         f('CRDOT_R') f('CRDOT_T') f('CRDOT_N') f('CRDOT_RDOT') f('CTDOT_RDOT') f('CNDOT_RDOT');
         f('CTDOT_R') f('CTDOT_T') f('CTDOT_N') f('CTDOT_RDOT') f('CTDOT_TDOT') f('CNDOT_TDOT');
         f('CNDOT_R') f('CNDOT_T') f('CNDOT_N') f('CNDOT_RDOT') f('CNDOT_TDOT') f('CNDOT_NDOT')];
    M = rot_eci2rtc(r, v);
    P = blkdiag(M', M')*C*blkdiag(M, M);
end

function run_quiet(f)
    evalc('star_collision_main(f);');
end

function write_json(f, s)
    folder = fileparts(f);
    if ~isfolder(folder), mkdir(folder); end
    fid = fopen(f, 'w'); fprintf(fid, '%s', jsonencode(s)); fclose(fid);
end

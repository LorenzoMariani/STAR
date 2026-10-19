function tests = test_end004_power_budget
%TEST_END004_POWER_BUDGET  Checks of END-004 (STAR_END004_POWER_BUDGET) against hand-computed cases (2026-10-19).
%
%   From END004-PowerBudget:   results = runtests('tests/test_end004_power_budget.m')
%
%   Per orbit and mode, for each subsystem of power P with duty fractions d_sun, d_ecl:
%     E_sun = sum P d_sun t_sun / 60, E_ecl = sum P d_ecl t_ecl / 60 [Wh], margin m on both,
%     saved = E_gen - (1 + m)(E_sun + E_ecl), daily balance = saved x orbits of the mode,
%     depth of discharge = E_ecl / C when E_gen > E_sun, else ((1 + m)(E_sun + E_ecl) - E_gen) / C,
%     orbits to recharge a deficit = deficit / saved per idle orbit;
%   generation from the solar power: E_gen = P_solar t_sun / 60; orbital period from the END-003 CSV radius,
%   2 pi sqrt(a^3 / mu); default split of the day without operations: 8 payload orbits, the rest idle.
    tests = functiontests(localfunctions);
end

function setupOnce(tc)
    tc.TestData.root = fileparts(fileparts(mfilename('fullpath')));
    addpath(tc.TestData.root);
    tc.TestData.work = tempname;
    mkdir(tc.TestData.work);
end

function teardownOnce(tc)
    rmpath(tc.TestData.root);
    if isfolder(tc.TestData.work), rmdir(tc.TestData.work, 's'); end
end

%% =========================================================================
function test_energy_balance_of_one_subsystem(tc)
    % 10 W, always on in sunlight and half of the eclipse in idle; 60 min of sun and 30 of eclipse; 20 Wh generated
    cfg = base_cfg();
    cfg.subsystems = subsystem('LOAD', 10, [1 0.5], [0 0], [0 0], [0 0]);
    S = run_end004(tc, 'one', cfg);
    m = mode_of(S, 'idle');
    verifyEqual(tc, m.sun_consumption_Wh, 10, 'AbsTol', 1e-12);
    verifyEqual(tc, m.eclipse_consumption_Wh, 2.5, 'AbsTol', 1e-12);
    verifyEqual(tc, m.total_consumption_margin_Wh, 1.1*12.5, 'AbsTol', 1e-12);
    verifyEqual(tc, m.power_saved_per_orbit_Wh, 20 - 1.1*12.5, 'AbsTol', 1e-12);
    verifyEqual(tc, m.peak_power_W, 10, 'AbsTol', 1e-12);
    verifyEqual(tc, m.orbital_DoD, 2.5/10, 'AbsTol', 1e-12);                    % generation covers the sunlit load
    verifyEqual(tc, m.daily_balance_Wh, (20 - 1.1*12.5)*15, 'AbsTol', 1e-9);
    verifyEqual(tc, S.analysis.daily_balance_Wh, (20 - 1.1*12.5)*15 + 20*0, 'AbsTol', 1e-9);
    p = mode_of(S, 'payload');                                                     % nothing on: all the generation is saved
    verifyEqual(tc, [p.total_consumption_Wh, p.power_saved_per_orbit_Wh, p.orbital_DoD], [0 20 0], 'AbsTol', 1e-12);
end

function test_deficit_mode_depth_of_discharge_and_recharge(tc)
    % payload mode draws 30 W in sunlight: 30 Wh > 20 Wh generated, the battery covers the deficit
    cfg = base_cfg();
    cfg.operations.mode_orbits_per_day = struct('idle', 7, 'tx_uhf', 0, 'tx_sband', 0, 'payload', 8);
    cfg.subsystems = subsystem('BUS', 2, [1 1], [1 1], [1 1], [1 1]);
    cfg.subsystems(2) = subsystem('PAYLOAD', 28, [0 0], [0 0], [0 0], [1 0]);
    S = run_end004(tc, 'deficit', cfg);
    idle = mode_of(S, 'idle'); pay = mode_of(S, 'payload');
    idle_saved = 20 - 1.1*(2 + 1);                                             % 2 Wh sun + 1 Wh eclipse
    pay_load = 1.1*(30 + 1);
    verifyEqual(tc, idle.power_saved_per_orbit_Wh, idle_saved, 'AbsTol', 1e-12);
    verifyEqual(tc, pay.power_saved_per_orbit_Wh, 20 - pay_load, 'AbsTol', 1e-12);
    verifyEqual(tc, pay.orbital_DoD, (pay_load - 20)/10, 'AbsTol', 1e-12);       % generation below the sunlit load
    verifyEqual(tc, pay.idle_orbits_to_recharge, (pay_load - 20)/idle_saved, 'AbsTol', 1e-12);
    verifyEqual(tc, idle.idle_orbits_to_recharge, 0, 'AbsTol', 1e-12);
    verifyEqual(tc, S.analysis.daily_balance_Wh, 7*idle_saved + 8*(20 - pay_load), 'AbsTol', 1e-9);
end

function test_solar_power_sets_the_generation(tc)
    cfg = base_cfg();
    cfg.generation.solar_power_W = 12;
    cfg.subsystems = subsystem('LOAD', 1, [1 1], [1 1], [1 1], [1 1]);
    S = run_end004(tc, 'solar', cfg);
    verifyEqual(tc, mode_of(S, 'idle').power_generated_per_orbit_Wh, 12*60/60, 'AbsTol', 1e-12);
end

function test_orbital_period_from_the_end003_csv(tc)
    % circular orbit of radius 7000 km in the END-003 CSV and no period in the input: T = 2 pi sqrt(a^3/mu)
    a = 7000; mu = 398600.4418;
    t = (0:10:600)';
    th = 2*pi*t/(2*pi*sqrt(a^3/mu));
    csv = fullfile(tc.TestData.work, 'attitude.csv');
    fid = fopen(csv, 'w');
    fprintf(fid, 'timestamp_utc,eci_x_km,eci_y_km,eci_z_km,q_w,q_x,q_y,q_z,nadir_offset_deg\n');
    ts = string(datetime(2026, 5, 21, 12, 0, 0) + seconds(t), 'yyyy-MM-dd''T''HH:mm:ss''Z''');
    for k = 1:numel(t)
        fprintf(fid, '%s,%.6f,%.6f,%.6f,1,0,0,0,0\n', ts(k), a*cos(th(k)), a*sin(th(k)), 0);
    end
    fclose(fid);
    cfg = base_cfg();
    cfg.orbit = struct('eclipse_min', 30);                                     % period and sunlight from the CSV
    cfg.paths.attitudeCsv = csv;
    cfg.subsystems = subsystem('LOAD', 1, [1 1], [1 1], [1 1], [1 1]);
    S = run_end004(tc, 'period', cfg);
    T = 2*pi*sqrt(a^3/mu)/60;
    verifyEqual(tc, S.orbit.periodMin, T, 'RelTol', 1e-9);
    verifyEqual(tc, S.orbit.sunlightMin, T - 30, 'RelTol', 1e-9);
    verifyEqual(tc, S.orbit.passDurationMin, 10, 'AbsTol', 1e-9);
    verifyEqual(tc, S.orbit.dailyOrbits, floor(1440/T));
    verifyEqual(tc, S.orbit.csvSamples, numel(t));
end

function test_default_split_of_the_day(tc)
    % no operations in the input: 8 payload orbits a day, the others idle
    cfg = base_cfg();
    cfg = rmfield(cfg, 'operations');
    cfg.subsystems = subsystem('LOAD', 1, [1 1], [1 1], [1 1], [1 1]);
    S = run_end004(tc, 'split', cfg);
    verifyEqual(tc, [mode_of(S, 'idle').orbits_per_day, mode_of(S, 'payload').orbits_per_day, ...
        mode_of(S, 'tx_uhf').orbits_per_day, mode_of(S, 'tx_sband').orbits_per_day], [15 - 8, 8, 0, 0]);
end

function test_products_are_written(tc)
    cfg = base_cfg();
    cfg.subsystems = subsystem('LOAD', 1, [1 1], [1 1], [1 1], [1 1]);
    out = fullfile(tc.TestData.work, 'products');
    run_end004(tc, 'products', cfg);
    prod = fullfile(out, 'output_power_budget'); res = fullfile(out, 'results_power_budget');
    for f = {fullfile(prod, 'power_budget_summary.csv'), fullfile(prod, 'power_budget_subsystems.csv'), ...
            fullfile(prod, 'power_budget_summary.json'), fullfile(prod, 'power_budget_status.json'), ...
            fullfile(res, 'power_budget_tables.js'), fullfile(res, '01_power_balance.png'), ...
            fullfile(res, '02_mode_consumption.png'), fullfile(res, '03_orbital_dod.png')}
        verifyTrue(tc, isfile(f{1}), f{1});
    end
    status = jsondecode(fileread(fullfile(prod, 'power_budget_status.json')));
    verifyEqual(tc, status.status, 'completed');
end

%% =========================================================================
%  HELPERS
%  =========================================================================
function cfg = base_cfg()
    % 90 min orbit, 60 min of sun, 15 orbits a day, 20 Wh generated per orbit, 10 Wh battery, 10% margin;
    % 15 idle orbits a day, no other mode
    cfg = struct();
    cfg.paths = struct('attitudeCsv', '', 'attitudeConfigJson', '');
    cfg.orbit = struct('daily_orbits', 15, 'period_min', 90, 'sunlight_min', 60, 'eclipse_min', 30);
    cfg.generation = struct('power_generated_per_orbit_Wh', 20, 'solar_power_W', []);
    cfg.battery = struct('capacity_Wh', 10);
    cfg.margin_fraction = 0.10;
    cfg.operations = struct('mode_orbits_per_day', struct('idle', 15, 'tx_uhf', 0, 'tx_sband', 0, 'payload', 0));
end

function s = subsystem(name, P, idle, tx_uhf, tx_sband, payload)
    % duty fractions [sun eclipse] per mode
    d = @(v) struct('sun', v(1), 'eclipse', v(2));
    s = struct('name', name, 'powerW', P, 'duty', struct('idle', d(idle), 'tx_uhf', d(tx_uhf), 'tx_sband', d(tx_sband), ...
        'payload', d(payload)));
end

function S = run_end004(tc, name, cfg)
    % writes the input JSON, runs END-004 into <work>/<name> and returns power_budget_summary.json
    out = fullfile(tc.TestData.work, name);
    f = fullfile(tc.TestData.work, [name '.json']);
    fid = fopen(f, 'w'); fprintf(fid, '%s', jsonencode(cfg)); fclose(fid);
    evalc('STAR_END004_POWER_BUDGET(f, out)');
    close all force;
    S = jsondecode(fileread(fullfile(out, 'output_power_budget', 'power_budget_summary.json')));
end

function m = mode_of(S, key)
    ms = S.mode_summaries;
    if iscell(ms), ms = [ms{:}]; end
    m = ms(strcmp({ms.mode_key}, key));
end

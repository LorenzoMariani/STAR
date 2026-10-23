function tests = test_end019_heater_cases
%TEST_END019_HEATER_CASES  Battery heater of the END-019 cold case (BackEnd/runners/matlab/end019_heater_cases.m, phase F4, 2026-10-23).
%
%   From the STAR folder:   results = runtests('tests/test_end019_heater_cases.m')     (run_all_tests.py: suite HEATER)
%
%   end019_heater_cases lives outside END019-ComponentsThermalAnalysis (black box) and only calls its functions. Checks:
%   the ideal thermostat holds the battery at the setpoint; the bang-bang thermostat with 1.25 x the needed peak keeps the
%   battery above the lower limit (cold case and mission window); no lower limit -> not applicable; the module's own
%   results do not change when the configuration carries a heater (star_thermal_main ignores it).
%   Input: satellite_01 of the END-019 examples (esempi_io_star), 12U body panels, central body and battery, idle 1.5 W.
    tests = functiontests(localfunctions);
end

function setupOnce(tc)
    star = fileparts(fileparts(mfilename('fullpath')));
    mod = fullfile(star, 'END019-ComponentsThermalAnalysis');
    tc.TestData.paths = {fullfile(mod, 'src'), fullfile(star, 'BackEnd', 'runners', 'matlab')};
    addpath(tc.TestData.paths{:});
    work = tempname; mkdir(work);
    tc.TestData.work = work;
    ex = fullfile(mod, 'examples', 'esempi_io_star');
    in = fullfile(work, 'star_input');
    mkdir(fullfile(in, 'output_constellation_optimizer'));
    copyfile(fullfile(ex, 'output_constellation_optimizer', 'satellite_01.json'), fullfile(in, 'output_constellation_optimizer'));
    copyfile(fullfile(ex, 'output_attitude_propagation'), fullfile(in, 'output_attitude_propagation'));
    % a battery limit of 30 degC (setpoint 35 degC) makes sure the battery needs a heater at the beta of the example
    tc.TestData.base = struct('star_input_dir', in, 'form_factor', '12U', 'panels', 'body', 'n_internal_nodes', 2, ...
        'P_internal_W', 2.0, 'bat_min_C', 30, 'bat_max_C', 60, 'cases', struct('name', 'cold', 'P_internal_W', 1.5));
    tc.TestData.sizing = run_cases(tc, 'sizing', struct());
end

function teardownOnce(tc)
    rmpath(tc.TestData.paths{:});
    if isfolder(tc.TestData.work), rmdir(tc.TestData.work, 's'); end
end

%% =========================================================================
function test_ideal_thermostat_holds_the_setpoint(tc)
    H = tc.TestData.sizing;
    verifyEqual(tc, H.status, 'completed');
    verifyEqual(tc, H.setpoint_C, 35);                                   % lower limit + 5 K
    c = H.satellites.cold;
    verifyGreaterThan(tc, c.needed_peak_W, 0);
    verifyGreaterThanOrEqual(tc, c.needed_peak_W, c.needed_mean_W);
    verifyEqual(tc, c.ideal_battery_min_C, 35, 'AbsTol', 0.01);          % exact: the step is linear in the heater power
    verifyEqual(tc, H.worst.needed_peak_W, c.needed_peak_W);
    verifyEmpty(tc, fieldnames(c.verify));                               % no heater in the design: sizing only
end

function test_bang_bang_with_the_heater_of_the_design(tc)
    p = 1.25*tc.TestData.sizing.worst.needed_peak_W;
    H = run_cases(tc, 'design', struct('power_w', p));
    s = H.satellites;
    verifyEqual(tc, s.cold.verify.power_W, p, 'RelTol', 1e-12);
    verifyGreaterThanOrEqual(tc, s.cold.verify.battery_min_C, 30);       % >= the lower limit (setpoint 35 - hysteresis 1 K)
    verifyLessThan(tc, abs(s.cold.verify.battery_min_C - 34), 1.5);
    verifyGreaterThanOrEqual(tc, s.window.battery_min_C, 30);
    verifyGreaterThan(tc, s.cold.verify.duty_pct, 0);
    verifyLessThanOrEqual(tc, s.cold.verify.duty_pct, 100);
    verifyEqual(tc, s.cold.verify.mean_W, p*s.cold.verify.duty_pct/100, 'RelTol', 1e-3);
    verifyEqual(tc, H.worst.battery_min_with_heater_C, min(s.cold.verify.battery_min_C, s.window.battery_min_C), 'AbsTol', 0.01);
    % the sizing does not depend on the heater of the design
    verifyEqual(tc, H.worst.needed_peak_W, tc.TestData.sizing.worst.needed_peak_W);
end

function test_without_a_lower_limit_not_applicable(tc)
    cfg = rmfield(tc.TestData.base, 'bat_min_C');
    H = run_cases(tc, 'nolimit', struct(), cfg);
    verifyEqual(tc, H.status, 'not_applicable');
end

function test_module_results_do_not_change_with_a_heater_in_the_configuration(tc)
    a = module_run(tc, 'mod_a', tc.TestData.base);
    cfg = tc.TestData.base; cfg.battery_heater = struct('power_w', 5);
    b = module_run(tc, 'mod_b', cfg);
    verifyEqual(tc, b, a);
end

%% =========================================================================
function H = run_cases(tc, name, heater, cfg)
    if nargin < 4, cfg = tc.TestData.base; end
    cfg.output_dir = fullfile(tc.TestData.work, name);
    if ~isempty(fieldnames(heater)), cfg.battery_heater = heater; end
    f = fullfile(tc.TestData.work, [name '.json']);
    write_json(f, cfg);
    evalc('end019_heater_cases(f);');
    H = jsondecode(fileread(fullfile(cfg.output_dir, 'heater_cases.json')));
end

function T = module_run(tc, name, cfg)
    cfg.output_dir = fullfile(tc.TestData.work, name);
    f = fullfile(tc.TestData.work, [name '.json']);
    write_json(f, cfg);
    evalc('star_thermal_main(f);');
    T = readtable(fullfile(cfg.output_dir, 'thermal_constellation_output.csv'), 'TextType', 'string');
end

function write_json(f, s)
    fid = fopen(f, 'w'); fprintf(fid, '%s', jsonencode(s)); fclose(fid);
end

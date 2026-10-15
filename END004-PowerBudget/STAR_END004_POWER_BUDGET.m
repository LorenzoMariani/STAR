function status = STAR_END004_POWER_BUDGET(configFile, outputFolder)
%STAR_END004_POWER_BUDGET Compute an EPS/power-budget assessment.
%
%   status = STAR_END004_POWER_BUDGET(configFile, outputFolder)
%
% The module reproduces the calculation logic of the reference Excel workbook
% used in STAR for power-budget sizing.  It consumes a JSON configuration and,
% when available, the END-003 attitude propagation CSV in order to derive
% orbit-dependent timing quantities.  The outputs are written to the STAR
% standard layout:
%
%   output_power_budget/   product CSV/JSON/XLSX files
%   results_power_budget/  tables.js and diagnostic figures

    if ~isfile(configFile)
        error('STAR_END004_POWER_BUDGET:ConfigNotFound', 'Input JSON file not found: %s', configFile);
    end

    cfg = readJsonStruct(configFile);
    outputFolder = char(string(outputFolder));
    moduleRoot = outputFolder;
    moduleRootString = string(moduleRoot);
    if endsWith(moduleRootString, "\\output_power_budget") || endsWith(moduleRootString, "/output_power_budget")
        moduleRoot = char(string(fileparts(moduleRoot)));
    end

    productDir = getRuntimePath(cfg, 'module_product_output_dir', fullfile(moduleRoot, 'output_power_budget'));
    resultsDir = getRuntimePath(cfg, 'module_results_dir', fullfile(moduleRoot, 'results_power_budget'));
    if isfield(cfg, 'star_runtime')
        productDir = getRuntimePath(cfg.star_runtime, 'module_product_output_dir', productDir);
        resultsDir = getRuntimePath(cfg.star_runtime, 'module_results_dir', resultsDir);
    end
    ensureDir(productDir);
    ensureDir(resultsDir);

    orbit = deriveOrbitInputs(cfg);
    modes = defaultModes();
    subsystems = readSubsystems(cfg);
    modeOrbitCounts = readModeOrbitCounts(cfg, modes, orbit.dailyOrbits);
    marginFraction = getNestedNumber(cfg, {'margin_fraction'}, 0.10);
    if isfield(cfg, 'analysis')
        marginFraction = getNestedNumber(cfg.analysis, {'margin_fraction'}, marginFraction);
    end

    % Per-mode and daily calculations.
    modeSummaries = struct([]);
    perSubsystemRows = struct([]);
    rowIndex = 0;
    for m = 1:numel(modes)
        mode = modes(m);
        sunNoMargin = 0.0;
        eclipseNoMargin = 0.0;
        peakPower = 0.0;
        for s = 1:numel(subsystems)
            subsystem = subsystems(s);
            dutySun = getDutyValue(subsystem, mode.key, 'sun');
            dutyEclipse = getDutyValue(subsystem, mode.key, 'eclipse');
            dutySunMin = dutySun * orbit.sunlightMin;
            dutyEclipseMin = dutyEclipse * orbit.eclipseMin;
            consSunWh = subsystem.powerW * dutySunMin / 60.0;
            consEclipseWh = subsystem.powerW * dutyEclipseMin / 60.0;
            sunNoMargin = sunNoMargin + consSunWh;
            eclipseNoMargin = eclipseNoMargin + consEclipseWh;
            peakPower = peakPower + subsystem.powerW * max(dutySun, dutyEclipse);
            rowIndex = rowIndex + 1;
            perSubsystemRows(rowIndex).mode = mode.name; %#ok<AGROW>
            perSubsystemRows(rowIndex).subsystem = subsystem.name;
            perSubsystemRows(rowIndex).power_W = subsystem.powerW;
            perSubsystemRows(rowIndex).duty_sun_fraction = dutySun;
            perSubsystemRows(rowIndex).duty_eclipse_fraction = dutyEclipse;
            perSubsystemRows(rowIndex).duty_sun_min = dutySunMin;
            perSubsystemRows(rowIndex).duty_eclipse_min = dutyEclipseMin;
            perSubsystemRows(rowIndex).consumption_sun_Wh = consSunWh;
            perSubsystemRows(rowIndex).consumption_eclipse_Wh = consEclipseWh;
        end
        sunMargin = sunNoMargin * (1.0 + marginFraction);
        eclipseMargin = eclipseNoMargin * (1.0 + marginFraction);
        overallMargin = sunMargin + eclipseMargin;
        powerSaved = orbit.powerGeneratedPerOrbitWh - overallMargin;
        if orbit.powerGeneratedPerOrbitWh > sunNoMargin
            orbitalDoD = eclipseNoMargin / orbit.batteryCapacityWh;
        else
            orbitalDoD = (overallMargin - orbit.powerGeneratedPerOrbitWh) / orbit.batteryCapacityWh;
        end
        orbitalDoD = max(0.0, orbitalDoD);

        modeSummaries(m).mode = mode.name; %#ok<AGROW>
        modeSummaries(m).mode_key = mode.key;
        modeSummaries(m).orbits_per_day = modeOrbitCounts(m);
        modeSummaries(m).sun_consumption_Wh = sunNoMargin;
        modeSummaries(m).eclipse_consumption_Wh = eclipseNoMargin;
        modeSummaries(m).total_consumption_Wh = sunNoMargin + eclipseNoMargin;
        modeSummaries(m).sun_consumption_margin_Wh = sunMargin;
        modeSummaries(m).eclipse_consumption_margin_Wh = eclipseMargin;
        modeSummaries(m).total_consumption_margin_Wh = overallMargin;
        modeSummaries(m).power_generated_per_orbit_Wh = orbit.powerGeneratedPerOrbitWh;
        modeSummaries(m).power_saved_per_orbit_Wh = powerSaved;
        modeSummaries(m).peak_power_W = peakPower;
        modeSummaries(m).orbital_DoD = orbitalDoD;
        modeSummaries(m).daily_balance_Wh = powerSaved * modeOrbitCounts(m);
    end

    idleBalance = getModeBalance(modeSummaries, 'idle');
    txSbandBalance = getModeBalance(modeSummaries, 'tx_sband');
    for m = 1:numel(modeSummaries)
        deficit = max(0.0, -modeSummaries(m).power_saved_per_orbit_Wh);
        if idleBalance > 0
            modeSummaries(m).idle_orbits_to_recharge = deficit / idleBalance;
        else
            modeSummaries(m).idle_orbits_to_recharge = NaN;
        end
        if txSbandBalance > 0
            modeSummaries(m).tx_sband_orbits_to_recharge = deficit / txSbandBalance;
        else
            modeSummaries(m).tx_sband_orbits_to_recharge = NaN;
        end
    end

    dailyBalanceWh = sum([modeSummaries.daily_balance_Wh]);
    summary = buildSummary(cfg, orbit, modeSummaries, dailyBalanceWh, marginFraction);

    % Product outputs.
    summaryTable = struct2table(modeSummaries);
    subsystemTable = struct2table(perSubsystemRows);
    writetable(summaryTable, fullfile(productDir, 'power_budget_summary.csv'));
    writetable(subsystemTable, fullfile(productDir, 'power_budget_subsystems.csv'));

    sheet1Cell = buildSheet1Cell(subsystems, modes, modeSummaries, orbit, marginFraction);
    foglio1Cell = buildFoglio1Cell(subsystems, modes, modeSummaries, orbit, modeOrbitCounts, dailyBalanceWh, marginFraction);
    writeCellCsv(fullfile(productDir, 'power_budget_sheet1.csv'), sheet1Cell);
    writeCellCsv(fullfile(productDir, 'power_budget_foglio1.csv'), foglio1Cell);
    try
        writecell(sheet1Cell, fullfile(productDir, 'power_budget_tables.xlsx'), 'Sheet', 'Sheet1');
        writecell(foglio1Cell, fullfile(productDir, 'power_budget_tables.xlsx'), 'Sheet', 'Foglio1');
    catch writeXlsxError
        warning('STAR:END004:XLSXWriteFailed', 'Could not write XLSX workbook: %s', writeXlsxError.message);
    end

    summaryJsonPath = fullfile(productDir, 'power_budget_summary.json');
    writeText(summaryJsonPath, prettyJson(summary));

    jsPath = fullfile(resultsDir, 'power_budget_tables.js');
    jsPayload = jsonencode(summary);
    writeText(jsPath, ['window.powerBudgetData = ', jsPayload, ';']);

    createFigures(summaryTable, productDir, resultsDir, summary);

    statusPath = fullfile(productDir, 'power_budget_status.json');
    statusPayload = struct();
    statusPayload.status = 'completed';
    statusPayload.generated_at = char(datetime('now','Format','yyyy-MM-dd''T''HH:mm:ss'));
    statusPayload.product_dir = productDir;
    statusPayload.results_dir = resultsDir;
    statusPayload.daily_balance_Wh = dailyBalanceWh;
    writeText(statusPath, prettyJson(statusPayload));

    status = 'completed';
end

function cfg = readJsonStruct(path)
    raw = fileread(path);
    cfg = jsondecode(raw);
end

function ensureDir(path)
    if ~exist(path, 'dir')
        mkdir(path);
    end
end

function value = getRuntimePath(s, fieldName, defaultValue)
    value = defaultValue;
    if isstruct(s) && isfield(s, fieldName)
        raw = s.(fieldName);
        if ~(isstring(raw) && strlength(raw) == 0) && ~isempty(raw)
            value = char(string(raw));
        end
    end
end

function value = getNestedNumber(s, pathParts, defaultValue)
    value = defaultValue;
    try
        current = s;
        for i = 1:numel(pathParts)
            if isstruct(current) && isfield(current, pathParts{i})
                current = current.(pathParts{i});
            else
                return;
            end
        end
        value = scalarNumber(current, defaultValue);
    catch
        value = defaultValue;
    end
end

function value = scalarNumber(raw, fallback)
    value = fallback;
    try
        if nargin < 2
            fallback = NaN;
        end
        if isempty(raw)
            return;
        end
        if isnumeric(raw) || islogical(raw)
            if ~isscalar(raw)
                return;
            end
            candidate = double(raw);
        elseif ischar(raw) || isstring(raw)
            rawText = strtrim(char(string(raw)));
            if isempty(rawText)
                return;
            end
            candidate = str2double(rawText);
        else
            return;
        end
        if isscalar(candidate) && isfinite(candidate)
            value = candidate;
        end
    catch
        value = fallback;
    end
end

function txt = getNestedText(s, pathParts, defaultValue)
    txt = defaultValue;
    try
        current = s;
        for i = 1:numel(pathParts)
            if isfield(current, pathParts{i})
                current = current.(pathParts{i});
            else
                return;
            end
        end
        txt = char(string(current));
    catch
        txt = defaultValue;
    end
end

function orbit = deriveOrbitInputs(cfg)
    orbit = struct();
    orbit.attitudeCsv = '';
    orbit.attitudeConfigJson = '';
    if isfield(cfg, 'paths')
        orbit.attitudeCsv = getNestedText(cfg.paths, {'attitudeCsv'}, '');
        if isempty(orbit.attitudeCsv)
            orbit.attitudeCsv = getNestedText(cfg.paths, {'attitude_csv'}, '');
        end
        orbit.attitudeConfigJson = getNestedText(cfg.paths, {'attitudeConfigJson'}, '');
    end
    if isempty(orbit.attitudeCsv)
        orbit.attitudeCsv = getenv('STAR_END003_OUTPUT_CSV');
    end
    if isempty(orbit.attitudeConfigJson)
        orbit.attitudeConfigJson = getenv('STAR_END003_RUNTIME_INPUT_JSON');
    end

    cfgEnd003 = struct();
    if ~isempty(orbit.attitudeConfigJson) && isfile(orbit.attitudeConfigJson)
        cfgEnd003 = readJsonStruct(orbit.attitudeConfigJson);
    end

    orbit.periodMin = NaN;
    orbit.sunlightMin = NaN;
    orbit.eclipseMin = NaN;
    orbit.passDurationMin = NaN;
    orbit.csvSamples = 0;
    orbit.attitudeMode = getNestedText(cfgEnd003, {'sat','attitude_mode'}, 'nadir');
    orbit.simulationHours = getNestedNumber(cfgEnd003, {'sim_hours'}, getNestedNumber(cfg, {'orbit','simulation_hours'}, 48.0));
    orbit.startUtc = getNestedText(cfgEnd003, {'sim_start_date'}, '');

    if ~isempty(orbit.attitudeCsv) && isfile(orbit.attitudeCsv)
        T = readtable(orbit.attitudeCsv, 'VariableNamingRule', 'preserve');
        orbit.csvSamples = height(T);
        orbit.periodMin = inferPeriodFromCsv(T, cfgEnd003);
        orbit.passDurationMin = inferPassDurationMinutes(T);
    end

    orbit.periodMin = overrideNumber(cfg, {'orbit','period_min'}, orbit.periodMin);
    if isnan(orbit.periodMin) || orbit.periodMin <= 0
        orbit.periodMin = 94.4691;
    end

    orbit.eclipseMin = overrideNumber(cfg, {'orbit','eclipse_min'}, NaN);
    if isnan(orbit.eclipseMin) || orbit.eclipseMin < 0
        orbit.eclipseMin = 35.0;
    end
    orbit.sunlightMin = overrideNumber(cfg, {'orbit','sunlight_min'}, orbit.periodMin - orbit.eclipseMin);
    if isnan(orbit.sunlightMin) || orbit.sunlightMin <= 0
        orbit.sunlightMin = max(0.0, orbit.periodMin - orbit.eclipseMin);
    end
    orbit.eclipseMin = max(0.0, orbit.periodMin - orbit.sunlightMin);

    orbit.dailyOrbits = overrideNumber(cfg, {'orbit','daily_orbits'}, floor(1440.0 / orbit.periodMin));
    if isnan(orbit.dailyOrbits) || orbit.dailyOrbits <= 0
        orbit.dailyOrbits = 15;
    end
    orbit.powerGeneratedPerOrbitWh = getNestedNumber(cfg, {'generation','power_generated_per_orbit_Wh'}, 3.0);
    solarPowerW = getNestedNumber(cfg, {'generation','solar_power_W'}, NaN);
    if isfinite(solarPowerW) && solarPowerW > 0
        orbit.powerGeneratedPerOrbitWh = solarPowerW * orbit.sunlightMin / 60.0;
    end
    orbit.batteryCapacityWh = getNestedNumber(cfg, {'battery','capacity_Wh'}, 19.0);
    if orbit.batteryCapacityWh <= 0
        orbit.batteryCapacityWh = 19.0;
    end
end

function value = overrideNumber(s, pathParts, fallback)
    value = fallback;
    try
        current = s;
        for i = 1:numel(pathParts)
            if isstruct(current) && isfield(current, pathParts{i})
                current = current.(pathParts{i});
            else
                return;
            end
        end
        value = scalarNumber(current, fallback);
    catch
        value = fallback;
    end
end

function periodMin = inferPeriodFromCsv(T, cfgEnd003)
    mu = 398600.4418; % km^3/s^2
    periodMin = NaN;
    try
        names = T.Properties.VariableNames;
        ix = find(strcmpi(names, 'eci_x_km'), 1);
        iy = find(strcmpi(names, 'eci_y_km'), 1);
        iz = find(strcmpi(names, 'eci_z_km'), 1);
        if ~isempty(ix) && ~isempty(iy) && ~isempty(iz)
            r = sqrt(T{:, ix}.^2 + T{:, iy}.^2 + T{:, iz}.^2);
            a = median(r, 'omitnan');
            if isfinite(a) && a > 6370
                periodMin = 2.0 * pi * sqrt(a^3 / mu) / 60.0;
            end
        end
    catch
        periodMin = NaN;
    end
    if isnan(periodMin)
        try
            Re = getNestedNumber(cfgEnd003, {'env','Re'}, 6371000.0) / 1000.0;
            altPer = getNestedNumber(cfgEnd003, {'orbit','alt_perigee_m'}, NaN) / 1000.0;
            altApo = getNestedNumber(cfgEnd003, {'orbit','alt_apogee_m'}, altPer*1000.0) / 1000.0;
            a = Re + mean([altPer, altApo], 'omitnan');
            periodMin = 2.0 * pi * sqrt(a^3 / mu) / 60.0;
        catch
            periodMin = NaN;
        end
    end
end

function passDurationMin = inferPassDurationMinutes(T)
    passDurationMin = NaN;
    try
        names = T.Properties.VariableNames;
        it = find(strcmpi(names, 'timestamp_utc'), 1);
        if isempty(it)
            return;
        end
        raw = string(T{:, it});
        dt = datetime(raw, 'InputFormat', "yyyy-MM-dd'T'HH:mm:ss'Z'", 'TimeZone', 'UTC');
        passDurationMin = minutes(max(dt) - min(dt));
    catch
        passDurationMin = NaN;
    end
end

function modes = defaultModes()
    modes = struct([]);
    modes(1).key = 'idle';      modes(1).name = 'Idle mode';
    modes(2).key = 'tx_uhf';    modes(2).name = 'TX mode UHF';
    modes(3).key = 'tx_sband';  modes(3).name = 'TX mode S BAND';
    modes(4).key = 'payload';   modes(4).name = 'Payload mode';
end

function subsystems = readSubsystems(cfg)
    if isfield(cfg, 'subsystems') && isstruct(cfg.subsystems) && numel(cfg.subsystems) > 0
        subsystems = cfg.subsystems;
        for i = 1:numel(subsystems)
            if ~isfield(subsystems(i), 'powerW') && isfield(subsystems(i), 'power_W')
                subsystems(i).powerW = subsystems(i).power_W;
            end
            if ~isfield(subsystems(i), 'duty')
                subsystems(i).duty = struct();
            end
        end
    else
        subsystems = defaultSubsystems();
    end
end

function subsystems = defaultSubsystems()
    subsystems = struct([]);
    subsystems(end+1) = makeSubsystem('OBDH', 0.3, [1 1 1 1 1 1 1 1]);
    subsystems(end+1) = makeSubsystem('EPS', 0.16, [1 1 1 1 1 1 1 1]);
    subsystems(end+1) = makeSubsystem('RX UHF', 0.18, [1 1 1 1 1 1 1 1]);
    subsystems(end+1) = makeSubsystem('TX UHF', 2.64, [0 0 0 0.2 0 0 0 0]);
    subsystems(end+1) = makeSubsystem('BEACON UHF', 2.64, [0.0067 0.0067 0.0067 0.0067 0.0067 0.0067 0.0067 0.0067]);
    subsystems(end+1) = makeSubsystem('RX S BAND', 0.5, [0 0 0 0 0 0.2 0 0]);
    subsystems(end+1) = makeSubsystem('TX S BAND', 3.0, [0 0 0 0 0 0.2 0 0.2]);
    subsystems(end+1) = makeSubsystem('ADCS', 0.432, [0.0105 0.0105 0.0105 0.0105 0.0105 0.0105 0.0105 0.0105]);
    subsystems(end+1) = makeSubsystem('THERMAL', 3.0, [0 0.1 0 0.1 0 0.1 0 0]);
    subsystems(end+1) = makeSubsystem('CAMERAS', 1.5, [0 0 0 0 0 0 0.017 0]);
    subsystems(end+1) = makeSubsystem('SDR', 5.0, [0 0 0 0 0 0 0.5 0]);
end

function s = makeSubsystem(name, powerW, dutyVector)
    s = struct();
    s.name = name;
    s.powerW = powerW;
    s.duty = struct();
    keys = {'idle','tx_uhf','tx_sband','payload'};
    idx = 1;
    for k = 1:numel(keys)
        s.duty.(keys{k}).sun = dutyVector(idx); idx = idx + 1;
        s.duty.(keys{k}).eclipse = dutyVector(idx); idx = idx + 1;
    end
end

function value = getDutyValue(subsystem, modeKey, phase)
    value = 0.0;
    try
        if isfield(subsystem, 'duty') && isfield(subsystem.duty, modeKey) && isfield(subsystem.duty.(modeKey), phase)
            value = scalarNumber(subsystem.duty.(modeKey).(phase), 0.0);
        end
    catch
        value = 0.0;
    end
end

function counts = readModeOrbitCounts(cfg, modes, dailyOrbits)
    counts = zeros(1, numel(modes));
    if numel(modes) >= 1, counts(1) = dailyOrbits; end
    if numel(modes) >= 4
        counts(4) = 0;
        counts(1) = dailyOrbits;
    end
    if isfield(cfg, 'operations') && isfield(cfg.operations, 'mode_orbits_per_day')
        ops = cfg.operations.mode_orbits_per_day;
        for i = 1:numel(modes)
            if isfield(ops, modes(i).key)
                counts(i) = scalarNumber(ops.(modes(i).key), counts(i));
            end
        end
    else
        % Excel Foglio1 reference assumption: 8 payload orbits and the
        % remaining daily orbits in idle mode, unless the JSON overrides it.
        payloadDefault = min(8, dailyOrbits);
        counts = zeros(1, numel(modes));
        counts(4) = payloadDefault;
        counts(1) = max(0, dailyOrbits - payloadDefault);
    end
end

function balance = getModeBalance(modeSummaries, key)
    balance = NaN;
    for i = 1:numel(modeSummaries)
        if strcmp(modeSummaries(i).mode_key, key)
            balance = modeSummaries(i).power_saved_per_orbit_Wh;
            return;
        end
    end
end

function summary = buildSummary(cfg, orbit, modeSummaries, dailyBalanceWh, marginFraction)
    summary = struct();
    summary.module_id = 'END-004';
    summary.module_name = 'Power Budget';
    summary.generated_at = char(datetime('now','Format','yyyy-MM-dd''T''HH:mm:ss'));
    summary.source = 'STAR_END004_POWER_BUDGET';
    summary.input_config = cfg;
    summary.orbit = orbit;
    summary.analysis = struct();
    summary.analysis.margin_fraction = marginFraction;
    summary.analysis.daily_balance_Wh = dailyBalanceWh;
    summary.mode_summaries = modeSummaries;
end

function sheet = buildSheet1Cell(subsystems, modes, modeSummaries, orbit, marginFraction)
    nSubsystems = numel(subsystems);
    cols = 1 + 2*nSubsystems + 8;
    sheet = cell(3 + numel(modes)*4 + 10, cols);
    sheet(3,1) = {'Subsystem'};
    sheet(5,1) = {'Power [W]'};
    for s = 1:nSubsystems
        c = 2 + (s-1)*2;
        sheet(3,c) = {subsystems(s).name};
        sheet(5,c) = {subsystems(s).powerW};
    end
    r0 = 7;
    for m = 1:numel(modes)
        r = r0 + (m-1)*4;
        sheet(r,1) = {upper(modes(m).name)};
        sheet(r+1,1) = {'Duty cycle - Sun/Eclipse'};
        sheet(r+2,1) = {'Duty cycle [min]'};
        sheet(r+3,1) = {'Consumption [Wh]'};
        for s = 1:nSubsystems
            c = 2 + (s-1)*2;
            dSun = getDutyValue(subsystems(s), modes(m).key, 'sun');
            dEcl = getDutyValue(subsystems(s), modes(m).key, 'eclipse');
            sheet(r+1,c) = {dSun}; sheet(r+1,c+1) = {dEcl};
            sheet(r+2,c) = {dSun*orbit.sunlightMin}; sheet(r+2,c+1) = {dEcl*orbit.eclipseMin};
            sheet(r+3,c) = {subsystems(s).powerW*dSun*orbit.sunlightMin/60.0};
            sheet(r+3,c+1) = {subsystems(s).powerW*dEcl*orbit.eclipseMin/60.0};
        end
        csum = 2 + 2*nSubsystems;
        sheet(r+1,csum) = {'Power consumption [Wh]'};
        sheet(r+2,csum) = {'Per orbit'};
        sheet(r+2,csum+1) = {'Sun'};
        sheet(r+2,csum+2) = {'Eclipse'};
        sheet(r+2,csum+3) = {'Power saved [Wh]'};
        sheet(r+2,csum+4) = {'DoD'};
        sheet(r+3,csum) = {modeSummaries(m).total_consumption_Wh};
        sheet(r+3,csum+1) = {modeSummaries(m).sun_consumption_Wh};
        sheet(r+3,csum+2) = {modeSummaries(m).eclipse_consumption_Wh};
        sheet(r+3,csum+3) = {modeSummaries(m).power_saved_per_orbit_Wh};
        sheet(r+3,csum+4) = {modeSummaries(m).orbital_DoD};
    end
    infoCol = cols - 1;
    sheet(3,infoCol) = {'Orbit'};
    sheet(4,infoCol) = {'Daily orbits'}; sheet(4,infoCol+1) = {orbit.dailyOrbits};
    sheet(5,infoCol) = {'Period [min]'}; sheet(5,infoCol+1) = {orbit.periodMin};
    sheet(6,infoCol) = {'Sunlight [min]'}; sheet(6,infoCol+1) = {orbit.sunlightMin};
    sheet(7,infoCol) = {'Eclipse [min]'}; sheet(7,infoCol+1) = {orbit.eclipseMin};
    sheet(8,infoCol) = {'Power generated per orbit [Wh]'}; sheet(8,infoCol+1) = {orbit.powerGeneratedPerOrbitWh};
    sheet(10,infoCol) = {'Battery capacity [Wh]'}; sheet(10,infoCol+1) = {orbit.batteryCapacityWh};
    sheet(11,infoCol) = {'Margin'}; sheet(11,infoCol+1) = {marginFraction};
end

function sheet = buildFoglio1Cell(subsystems, modes, modeSummaries, orbit, modeOrbitCounts, dailyBalanceWh, marginFraction)
    cols = 20;
    rows = 62;
    sheet = cell(rows, cols);
    sheet(2,2) = {'Subsystem'};
    sheet(2,3) = {'Power [W]'};
    for m = 1:numel(modes)
        c = 5 + (m-1)*2;
        sheet(2,c) = {modes(m).name};
    end
    sheet(2,19) = {'Orbit'};
    sheet(3,19) = {'Daily orbits'}; sheet(3,20) = {orbit.dailyOrbits};
    sheet(4,19) = {'Period [min]'}; sheet(4,20) = {orbit.periodMin};
    sheet(5,19) = {'Sunlight [min]'}; sheet(5,20) = {orbit.sunlightMin};
    sheet(6,19) = {'Eclipse [min]'}; sheet(6,20) = {orbit.eclipseMin};
    sheet(7,19) = {'Power generated per orbit [Wh]'}; sheet(7,20) = {orbit.powerGeneratedPerOrbitWh};
    sheet(9,19) = {'Battery capacity [Wh]'}; sheet(9,20) = {orbit.batteryCapacityWh};

    r = 3;
    for s = 1:numel(subsystems)
        sheet(r,2) = {subsystems(s).name};
        sheet(r,3) = {subsystems(s).powerW};
        sheet(r,4) = {'Duty cycle - Sun/Eclipse'};
        sheet(r+1,4) = {'Duty cycle [min]'};
        sheet(r+2,4) = {'Consumption [Wh]'};
        for m = 1:numel(modes)
            c = 5 + (m-1)*2;
            dSun = getDutyValue(subsystems(s), modes(m).key, 'sun');
            dEcl = getDutyValue(subsystems(s), modes(m).key, 'eclipse');
            sheet(r,c) = {dSun}; sheet(r,c+1) = {dEcl};
            sheet(r+1,c) = {dSun*orbit.sunlightMin}; sheet(r+1,c+1) = {dEcl*orbit.eclipseMin};
            sheet(r+2,c) = {subsystems(s).powerW*dSun*orbit.sunlightMin/60.0};
            sheet(r+2,c+1) = {subsystems(s).powerW*dEcl*orbit.eclipseMin/60.0};
        end
        r = r + 3;
    end

    base = 35;
    for m = 1:numel(modes)
        c = 5 + (m-1)*2;
        sheet(base+2,c) = {'Sun'}; sheet(base+2,c+1) = {'Eclipse'};
        sheet(base+4,4) = {'Without margin'};
        sheet(base+4,c) = {modeSummaries(m).sun_consumption_Wh};
        sheet(base+4,c+1) = {modeSummaries(m).eclipse_consumption_Wh};
        sheet(base+5,4) = {[num2str(marginFraction*100, '%.0f') '% margin']};
        sheet(base+5,c) = {modeSummaries(m).sun_consumption_margin_Wh};
        sheet(base+5,c+1) = {modeSummaries(m).eclipse_consumption_margin_Wh};
        sheet(base+6,4) = {'Overall'};
        sheet(base+6,c) = {modeSummaries(m).total_consumption_margin_Wh};
        sheet(base+7,4) = {'Power saved [Wh]'};
        sheet(base+7,c) = {modeSummaries(m).power_saved_per_orbit_Wh};
        sheet(base+8,4) = {'Peak power consumption [W]'};
        sheet(base+8,c) = {modeSummaries(m).peak_power_W};
        sheet(base+9,4) = {'Orbital DoD'};
        sheet(base+9,c) = {modeSummaries(m).orbital_DoD};
        sheet(base+12,4) = {'# of IDLE mode orbits to recharge batteries'};
        sheet(base+12,c) = {modeSummaries(m).idle_orbits_to_recharge};
        sheet(base+14,4) = {'# of TX S-band mode orbits to recharge batteries'};
        sheet(base+14,c) = {modeSummaries(m).tx_sband_orbits_to_recharge};
    end
    sheet(36,16) = {'Number of orbits'};
    sheet(35,16) = {'Payload mode'}; sheet(35,17) = {'TX mode S band'}; sheet(35,18) = {'Idle mode'};
    sheet(36,17) = {modeOrbitCounts(4)}; sheet(36,18) = {modeOrbitCounts(3)}; sheet(36,19) = {modeOrbitCounts(1)};
    sheet(37,16) = {'Consumption/Generation [Wh]'};
    sheet(37,17) = {getModeBalance(modeSummaries, 'payload') * modeOrbitCounts(4)};
    sheet(37,18) = {getModeBalance(modeSummaries, 'tx_sband') * modeOrbitCounts(3)};
    sheet(37,19) = {getModeBalance(modeSummaries, 'idle') * modeOrbitCounts(1)};
    sheet(39,16) = {'Daily margin [Wh]'}; sheet(39,17) = {dailyBalanceWh};
end

function writeCellCsv(path, C)
    fid = fopen(path, 'w');
    if fid < 0
        error('STAR_END004_POWER_BUDGET:CsvWriteFailed', 'Cannot open %s for writing.', path);
    end
    cleaner = onCleanup(@() fclose(fid));
    for i = 1:size(C,1)
        items = cell(1, size(C,2));
        for j = 1:size(C,2)
            items{j} = csvEscape(C{i,j});
        end
        fprintf(fid, '%s\n', strjoin(items, ','));
    end
end

function s = csvEscape(v)
    if isempty(v)
        s = '';
    elseif isnumeric(v)
        if isnan(v)
            s = '';
        else
            s = num2str(v, '%.12g');
        end
    elseif islogical(v)
        s = string(v);
    else
        s = char(string(v));
    end
    if contains(s, ',') || contains(s, '"') || contains(s, newline)
        s = ['"' strrep(s, '"', '""') '"'];
    end
end

function writeText(path, text)
    fid = fopen(path, 'w');
    if fid < 0
        error('STAR_END004_POWER_BUDGET:TextWriteFailed', 'Cannot open %s for writing.', path);
    end
    cleaner = onCleanup(@() fclose(fid));
    fprintf(fid, '%s', text);
end

function txt = prettyJson(payload)
    try
        txt = jsonencode(payload, 'PrettyPrint', true);
    catch
        txt = jsonencode(payload);
    end
end

function createFigures(summaryTable, productDir, resultsDir, summary)
    try
        f1 = figure('Visible','off');
        bar(categorical(summaryTable.mode), summaryTable.power_saved_per_orbit_Wh);
        grid on;
        ylabel('Power balance [Wh/orbit]');
        title('Power Balance per Operational Mode');
        exportgraphics(f1, fullfile(resultsDir, '01_power_balance.png'), 'Resolution', 200);
        close(f1);
    catch figureError
        warning('STAR:END004:FigureFailed', 'Could not generate power balance figure: %s', figureError.message);
    end
    try
        f2 = figure('Visible','off');
        data = [summaryTable.sun_consumption_margin_Wh, summaryTable.eclipse_consumption_margin_Wh];
        bar(categorical(summaryTable.mode), data, 'stacked');
        grid on;
        ylabel('Consumption with margin [Wh/orbit]');
        legend({'Sunlight','Eclipse'}, 'Location','best');
        title('Mode Consumption Split');
        exportgraphics(f2, fullfile(resultsDir, '02_mode_consumption.png'), 'Resolution', 200);
        close(f2);
    catch figureError
        warning('STAR:END004:FigureFailed', 'Could not generate consumption figure: %s', figureError.message);
    end
    try
        f3 = figure('Visible','off');
        labels = categorical(summaryTable.mode);
        plot(labels, summaryTable.orbital_DoD * 100, '-o', 'LineWidth', 1.5);
        grid on;
        ylabel('Depth of discharge [%]');
        title(sprintf('Orbital DoD — daily balance %.3f Wh', summary.analysis.daily_balance_Wh));
        exportgraphics(f3, fullfile(resultsDir, '03_orbital_dod.png'), 'Resolution', 200);
        close(f3);
    catch figureError
        warning('STAR:END004:FigureFailed', 'Could not generate DoD figure: %s', figureError.message);
    end
    try
        copyfile(fullfile(productDir, 'power_budget_summary.json'), fullfile(resultsDir, 'power_budget_summary_copy.json'));
    catch
    end
end

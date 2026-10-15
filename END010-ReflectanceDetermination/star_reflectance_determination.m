%% STAR END-016: REFLECTANCE DETERMINATION ================================
% Esegue la generazione del CSV e la simulazione Unity.
%
% Input:
%   file_input  - Percorso del file JSON di configurazione (es. 'config.json')
%   path_output - Cartella in cui salvare tutti gli output (es. 'C:\Utenti\...\Output')


clear; clc; close all;
set(0, 'DefaultFigureVisible', 'off');

% I/O folders: di default si auto-localizzano rispetto alla cartella dello
% script (esecuzione standalone). STAR sovrascrive sempre file_input e
% path_output tramite le env var sotto, quindi questo fallback serve solo
% all'uso manuale e non deve puntare a percorsi di una vecchia macchina.
script_folder = fileparts(mfilename('fullpath'));
star_root = fileparts(script_folder);
default_file_input = fullfile(star_root, 'Input', 'input_reflectance_determination.json');
default_path_output = fullfile(star_root, 'Output');

star_input_override = getenv('STAR_END010_INPUT_FILE');
star_output_override = getenv('STAR_END010_OUTPUT_DIR');

if ~isempty(star_input_override)
    file_input = star_input_override;
else
    file_input = default_file_input;
end

if ~isempty(star_output_override)
    path_output = star_output_override;
else
    path_output = default_path_output;
end

fprintf('[STAR END-010] Input JSON: %s\n', file_input);
fprintf('[STAR END-010] Output folder: %s\n', path_output);

% RUN
status = STAR_END010_REFLECTANCE_DETERMINATION(file_input, path_output);


%% =======================================================================%
% == MAIN FUNCTION (API) =================================================%
%=========================================================================%
function [status] = STAR_END010_REFLECTANCE_DETERMINATION(configFile, output_folder)
    %% INITIALIZATION AND PATH SETUP
    
    main_folder_override = getenv('STAR_END010_MAIN_FOLDER');
    
    if ~isempty(main_folder_override)
        main_folder = string(main_folder_override);
    else
        main_folder = string(fileparts(mfilename('fullpath')));
    end
    
    fprintf('[STAR END-010] Main folder: %s\n', main_folder);

    addpath(fullfile(main_folder, "lib"))
    addpath(fullfile(main_folder, "lib", "data"))
    addpath(fullfile(main_folder, "lib", "sgp4"));
    addpath(fullfile(main_folder, "lib", "BuildAqua"));

    %% 1. Lettura e parsing del file JSON
    if ~exist(configFile, 'file')
        error('STAR_END010_REFLECTANCE_DETERMINATION: File JSON not found: %s', configFile);
    end
    
    fid = fopen(configFile, 'r');
    raw = fread(fid, inf, '*char')';
    fclose(fid);
    cfg = jsondecode(raw);

    %% 2. Setup Ambiente e Cartelle
    res_folder = output_folder + "\results_reflectance_determination";
    plots_folder = res_folder + "\Plots";
    frames_folder = res_folder + "\Frames";
    out_folder = output_folder + "\output_reflectance_determination";
    if ~exist(res_folder, 'dir')
        mkdir(res_folder);
    end
    if ~exist(plots_folder, 'dir')
        mkdir(plots_folder);
    end
    if ~exist(out_folder, 'dir')
        mkdir(out_folder);
    end
    parentDir = pwd;
    addpath(genpath(parentDir));

    % Caricamento file dati SGP4 e DE440
    if ~exist(cfg.paths.nutData, 'file'), error('File SGP4 not found: %s', cfg.paths.nutData); end
    if ~exist(cfg.paths.deData, 'file'), error('File DE440 not found: %s', cfg.paths.deData); end
    
    % Carica le variabili direttamente nel workspace della funzione
    load(cfg.paths.nutData, 'nut80');
    load(cfg.paths.deData, 'DE440Coeff');
    [iar80, rar80]  = iau80in(nut80);
    nutParams.iar80 = iar80;
    nutParams.rar80 = rar80;

    %% 3. Generazione/Caricamento Dati Ephemeris
    debug = cfg.simulation.debug;
    
    % Configurazione Stazione: se il config fornisce lat/lon espliciti (es.
    % l'orchestratore li allinea al target reale di END-003), usa quelli
    % invece del lookup per nome su stationsJson, altrimenti la stazione di
    % osservazione potrebbe non avere nulla a che fare col passaggio reale.
    if isfield(cfg.simulation, 'observatoryLat') && isfield(cfg.simulation, 'observatoryLon') ...
            && ~isempty(cfg.simulation.observatoryLat) && ~isempty(cfg.simulation.observatoryLon)
        lat = cfg.simulation.observatoryLat;
        lon = cfg.simulation.observatoryLon;
        if isfield(cfg.simulation, 'observatoryAlt') && ~isempty(cfg.simulation.observatoryAlt)
            alt = cfg.simulation.observatoryAlt;
        else
            alt = 0;
        end
        fprintf('[STAR END-010] Observation site: explicit lat=%.4f lon=%.4f alt=%.1f\n', lat, lon, alt);
    else
        [lat, lon, alt, ~] = readStationFile(cfg.paths.stationsJson, cfg.simulation.observatory);
    end
    lla = [lat*pi/180, lon*pi/180, alt*1e-3];

    % Controllo se leggere da CSV esterno o propagare internamente
    if isfield(cfg.flags, 'useInputCsv') && cfg.flags.useInputCsv
        fprintf('Load CSV with timestamped ECI orbit and attitude: %s\n', cfg.paths.inputCsv);
        if ~exist(cfg.paths.inputCsv, 'file')
            error('STAR_END010_REFLECTANCE_DETERMINATION: Input CSV file not found: %s', cfg.paths.inputCsv);
        end
        
        % Lettura del CSV tramite Tabella per gestire i timestamp stringa
        opts = detectImportOptions(cfg.paths.inputCsv);
        opts.VariableNamingRule = 'preserve';
        dataTab = readtable(cfg.paths.inputCsv, opts);
        
        % Parsing dei Timestamps
        timeStr = string(dataTab.timestamp_utc);
        timeStr = strrep(timeStr, 'Z', '');
        times = datetime(timeStr, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss');
        len = length(times);
        
        times_ = string(zeros(1, len));
        for i = 1:len
            times_(i) = datestr(times(i), 'yyyy-mm-ddTHH:MM:SS');
        end
        
        % Estrazione di Orbita (reci) e Assetto (quaternioni) dal CSV
        reci = [dataTab.eci_x_km, dataTab.eci_y_km, dataTab.eci_z_km];
        att  = [dataTab.q_w, dataTab.q_x, dataTab.q_y, dataTab.q_z];
        
        % Calcolo di rsun e rseci sincronizzati sui tempi del CSV
        inputStruct.getGeodetic     = true;
        inputStruct.getVisibility   = true;
        inputStruct.getAzEl         = true;
        inputStruct.getRaDec        = true;
        inputStruct.getRange        = true;
        inputStruct.getSunRange     = true;
        inputStruct.getEcef         = true;
        inputStruct.getSunGeodetic  = true;
        inputStruct.getSun          = true;
        inputStruct.getObs          = true;
        inputStruct.times           = times;
        inputStruct.tlefile         = cfg.paths.tleFile;
        inputStruct.eopfile         = cfg.paths.eopFile;
        inputStruct.mask            = cfg.simulation.mask;
        inputStruct.lla             = lla;
        inputStruct.DE440Coeff      = DE440Coeff;
        inputStruct.nutParams       = nutParams;
        inputStruct.reci            = reci;
        
        out = propagation_from_reci(inputStruct);
        rseci = out.rseci;
        rsun  = out.rsun;
        e     = out.El;
        r     = out.r;
        s     = out.s;
        
    else
        % Configurazione Tempo
        tsim  = 0:cfg.simulation.delta:cfg.simulation.duration-1;
        len   = length(tsim);
        times = NaT(1,len);
        times_ = string(zeros(1,len));
        for i = 1:len
            times(i) = datetime(cfg.simulation.start) + seconds(tsim(i));
            times_(i) = datestr(times(i),'yyyy-mm-ddTHH:MM:SS');
        end
        
        % Configurazione Propagatore
        inputStruct.getGeodetic     = true;
        inputStruct.getVisibility   = true;
        inputStruct.getAzEl         = true;
        inputStruct.getRaDec        = true;
        inputStruct.getRange        = true;
        inputStruct.getSunRange     = true;
        inputStruct.getEcef         = true;
        inputStruct.getSunGeodetic  = true;
        inputStruct.getSun          = true;
        inputStruct.getObs          = true;
        inputStruct.times           = times;
        inputStruct.tlefile         = cfg.paths.tleFile;
        inputStruct.eopfile         = cfg.paths.eopFile;
        inputStruct.mask            = cfg.simulation.mask;
        inputStruct.lla             = lla;
        inputStruct.DE440Coeff      = DE440Coeff;
        inputStruct.nutParams       = nutParams;
        
        % Propagazione Orbita/Sole/Osservatorio
        if cfg.flags.orbitEphemeris
            % Orbita da ephemeris esterna: si carica subito reci esterna e si
            % passa a propagation_from_reci, cosi' rseci/rsun/r/s/e restano
            % coerenti con la traiettoria reale invece di restare legati alla
            % propagazione SGP4 interna (qui inutilizzata e quindi scartata).
            filePath  = resolveOptionalPath(cfg.paths, 'orbitOemFile', 'Select object OEM');
            [~, reci] = readOEM(filePath, times);
            inputStruct.reci = reci;
            out = propagation_from_reci(inputStruct);
        else
            out  = propagation(inputStruct);
            reci = out.reci;
        end
        rseci = out.rseci;
        rsun  = out.rsun;
        r     = out.r;
        s     = out.s;
        e     = out.El;

        % Propagazione Assetto
        if ~cfg.flags.attEphemeris
            q0 = [1, 0.0, 0.0, 0.0];
            q0 = q0/norm(q0);
            w0 = [0.0, 0.1, 0.0];
            att0 = [q0 w0];
            att0 = att0(:);
            I = [41815, 0, 0; 0, 41815, 0; 0, 0, 6570];
            att = propAttitude(att0, tsim, I);
        end

        % Sostituzione con ephemeris esterne per Sole/Osservatorio: si
        % ricalcolano subito le distanze dipendenti (r, s) per restare
        % coerenti con i nuovi vettori, con le stesse formule di
        % propagation.m/propagation_from_reci.m
        if cfg.flags.sunEphemeris
            filePath  = resolveOptionalPath(cfg.paths, 'sunOemFile', 'Select Sun OEM');
            [~, rsun] = readOEM(filePath, times);
            s = vecnorm(reci - rsun, 2, 2);
        end
        if cfg.flags.obsEphemeris
            filePath   = resolveOptionalPath(cfg.paths, 'obsOemFile', 'Select observatory OEM');
            [~, rseci] = readOEM(filePath, times);
            r = vecnorm(reci - rseci, 2, 2);
            warning('STAR_END010_REFLECTANCE_DETERMINATION:staleElevation', ...
                ['obsEphemeris attivo: l''elevazione (e/El) resta calcolata rispetto alla ' ...
                 'stazione precedente, perche'' il suo ricalcolo richiederebbe l''intera ' ...
                 'catena EOP/nutazione (non esposta da propagation.m).']);
        end
        if cfg.flags.attEphemeris
            filePath = resolveOptionalPath(cfg.paths, 'attFile', 'Select attitude DBL, OEM or CSV');
            if endsWith(filePath,'.DBL')
                times = times + seconds(18);
                att   = readPROQUA(filePath, times);
            elseif endsWith(filePath,'.txt')
                [~, att]  = readOEM(filePath, times);
            elseif endsWith(filePath,'.csv')
                tmp  = readmatrix(filePath);
                att  = tmp(:,2:end);
            end
        end
    end

    % Salvataggio del CSV generato nella cartella di output per Unity
    csvPath = fullfile(res_folder, 'csvUnity.csv');
    csv_lines = [times_(:), reci, rseci, rsun, e(:), r(:), s(:), att(:,1:4)];
    writematrix(csv_lines, csvPath);

    %% 4. Configurazione ed Esecuzione Unity
    unityOpts = cfg.unityOpts;
    
    unityOpts.csvFile      = csvPath;
    unityOpts.outputFolder = frames_folder;
    unityOpts.lightCurveFilename = out_folder + "\flux.csv";
    unityOpts.logFile      = fullfile(out_folder, cfg.unityOpts.logFile);
    
    fprintf('Start simulation in Unity...\n');
    [status, ~] = runUnity(cfg.paths.unityExe, unityOpts);
    fprintf('Simulation completed with state: %d\n', status);

    %% 4b. KPI CATALOG EXPORT
    % Indicatori di performance per iterazione orchestrator-driven e per la
    % valutazione della curva di luce / rilevabilita' (inquinamento luminoso).
    fprintf('Computing KPI catalog...\n');

    unitySuccess = (status == 0);

    lumValid = []; nInvalid = NaN; fluxSamples = 0;
    if exist(unityOpts.lightCurveFilename, 'file')
        try
            fluxTab     = readtable(unityOpts.lightCurveFilename);
            lum         = fluxTab.lum;
            validMask   = isfinite(lum) & lum > 0;
            nInvalid    = sum(~validMask);
            lumValid    = lum(validMask);
            fluxSamples = numel(lum);
        catch readErr
            warning('STAR_END010_REFLECTANCE_DETERMINATION:fluxReadFailed', ...
                'Unable to parse flux.csv for KPI computation: %s', readErr.message);
        end
    end

    if numel(lumValid) >= 2
        meanFlux        = mean(lumValid);
        peakFlux        = max(lumValid);
        minFlux         = min(lumValid);
        % Ampiezza e variabilita' RMS della curva di luce in magnitudini:
        % sono differenze di magnitudine, quindi indipendenti da un eventuale
        % zero-point fotometrico (lum e' un'unita' di rendering Unity non
        % calibrata - vedi KPI-11/12, riportati invece in unita' grezze).
        lcAmplitudeMag = 2.5 * log10(peakFlux / minFlux);
        instMag        = -2.5 * log10(lumValid);
        lcRmsMag       = std(instMag);
    elseif isscalar(lumValid)
        meanFlux = lumValid; peakFlux = lumValid; minFlux = lumValid; %#ok<NASGU>
        lcAmplitudeMag = 0; lcRmsMag = 0;
    else
        meanFlux = NaN; peakFlux = NaN; minFlux = NaN; %#ok<NASGU>
        lcAmplitudeMag = NaN; lcRmsMag = NaN;
    end

    framesRendered = numel(dir(fullfile(frames_folder, '*.png')));

    % Geometria/osservabilita' (vettorizzata sull'intero passaggio)
    objSunDir = rsun - reci;  objSunDir = objSunDir ./ vecnorm(objSunDir, 2, 2);
    objObsDir = rseci - reci; objObsDir = objObsDir ./ vecnorm(objObsDir, 2, 2);
    cosPhase      = max(-1, min(1, sum(objSunDir .* objObsDir, 2)));
    phaseAngleRad = acos(cosPhase);
    phaseAngleDeg = phaseAngleRad * 180 / pi;

    maxElevationDeg     = max(e);
    visibleFractionPct  = 100 * mean(out.access);
    meanRangeKm         = mean(r);
    minRangeKm          = min(r);
    meanPhaseAngleDeg   = mean(phaseAngleDeg);
    passDurationS       = seconds(times(end) - times(1));

    % Magnitudine apparente stimata con il modello standard di sfera diffusa
    % (Lambertiana): m = m_sun - 2.5*log10(albedo * r_sfera^2 * phi(alpha) / d^2),
    % phi(alpha) = (sin(alpha) + (pi-alpha)*cos(alpha))/pi. Approssimazione
    % (forma sferica, riflettanza uniforme, nessuna componente speculare);
    % usa cfg.sat.A_ref/albedo se presenti, altrimenti valori standard di
    % default. A differenza dei KPI-11..14 (scala relativa/strumentale),
    % questa e' su scala fotometrica standard e quindi comparabile alla
    % magnitudine limite visuale del sito (KPI-16).
    if isfield(cfg, 'sat') && isfield(cfg.sat, 'A_ref') && ~isempty(cfg.sat.A_ref)
        satA_ref = cfg.sat.A_ref;
    else
        satA_ref = 0.03; % m^2, valore standard di default
    end
    if isfield(cfg, 'sat') && isfield(cfg.sat, 'albedo') && ~isempty(cfg.sat.albedo)
        satAlbedo = cfg.sat.albedo;
    else
        satAlbedo = 0.2; % valore standard di default
    end

    satRadiusM  = sqrt(satA_ref / pi);
    dObsM       = r(:) * 1000;
    phaseFunc   = max((sin(phaseAngleRad(:)) + (pi - phaseAngleRad(:)) .* cos(phaseAngleRad(:))) / pi, 1e-12);
    sunAppMag   = -26.74;
    appMagStd   = sunAppMag - 2.5 * log10(satAlbedo * satRadiusM^2 * phaseFunc ./ (dObsM.^2));
    peakAppMag  = min(appMagStd);
    limitingMag = 7; % magnitudine limite visuale del sito (default fisso)
    meetsVisibility = peakAppMag <= limitingMag;

    kpis = struct([]);
    kpis = [kpis, kpi_entry('KPI-01', 'Unity Simulation Completed', unitySuccess, 'bool', 'run_validity', unitySuccess, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-02', 'Flux Samples Generated', fluxSamples, '-', 'run_validity', fluxSamples > 0, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-03', 'Frames Rendered', framesRendered, '-', 'run_validity', NaN, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-04', 'Invalid Flux Samples', nInvalid, '-', 'run_validity', nInvalid == 0, NaN, NaN)];

    kpis = [kpis, kpi_entry('KPI-05', 'Pass Duration', passDurationS, 's', 'geometry_observability', NaN, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-06', 'Max Elevation', maxElevationDeg, 'deg', 'geometry_observability', NaN, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-07', 'Visible Fraction', visibleFractionPct, '%', 'geometry_observability', NaN, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-08', 'Mean Object-Station Range', meanRangeKm, 'km', 'geometry_observability', NaN, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-09', 'Min Object-Station Range', minRangeKm, 'km', 'geometry_observability', NaN, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-10', 'Mean Phase Angle', meanPhaseAngleDeg, 'deg', 'geometry_observability', NaN, NaN, NaN)];

    kpis = [kpis, kpi_entry('KPI-11', 'Mean Instrumental Flux', meanFlux, 'Unity units', 'light_curve_photometry', NaN, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-12', 'Peak Instrumental Flux', peakFlux, 'Unity units', 'light_curve_photometry', NaN, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-13', 'Light Curve Amplitude', lcAmplitudeMag, 'mag', 'light_curve_photometry', NaN, NaN, NaN)];
    kpis = [kpis, kpi_entry('KPI-14', 'Light Curve RMS Variability', lcRmsMag, 'mag', 'light_curve_photometry', NaN, NaN, NaN)];

    kpis = [kpis, kpi_entry('KPI-15', 'Peak Apparent Visual Magnitude (Est.)', peakAppMag, 'mag', 'light_pollution_detectability', meetsVisibility, limitingMag, NaN)];
    kpis = [kpis, kpi_entry('KPI-16', 'Site Limiting Visual Magnitude', limitingMag, 'mag', 'light_pollution_detectability', NaN, NaN, NaN)];

    kpi_catalog = struct();
    kpi_catalog.module_id    = 'END-010';
    kpi_catalog.observatory  = cfg.simulation.observatory;
    kpi_catalog.generated_at = datestr(datetime('now', 'TimeZone', 'UTC'), 'yyyy-mm-dd HH:MM:SS');
    kpi_catalog.kpis         = kpis;

    kpi_json_text = jsonencode(kpi_catalog, 'PrettyPrint', true);
    kpi_file = fullfile(res_folder, 'reflectance_summary.json');
    fid = fopen(kpi_file, 'w');
    if fid < 0
        error('Unable to open KPI catalog output file: %s', kpi_file);
    end
    fprintf(fid, '%s', kpi_json_text);
    fclose(fid);
    fprintf('KPI catalog saved: %s\n', kpi_file);

    %% 4c. TIME SERIES EXPORT (per i grafici geometria/fotometria nel frontend)
    timeSeries = struct();
    timeSeries.module_id         = 'END-010';
    timeSeries.generated_at      = kpi_catalog.generated_at;
    timeSeries.time_iso          = cellstr(times_(:));
    timeSeries.time_s            = seconds(times(:) - times(1));
    timeSeries.elevation_deg     = e(:);
    timeSeries.range_km          = r(:);
    timeSeries.phase_angle_deg   = phaseAngleDeg(:);
    timeSeries.apparent_magnitude_std = appMagStd(:);

    ts_json_text = jsonencode(timeSeries, 'PrettyPrint', true);
    ts_file = fullfile(res_folder, 'reflectance_timeseries.json');
    fid = fopen(ts_file, 'w');
    if fid < 0
        error('Unable to open time series output file: %s', ts_file);
    end
    fprintf(fid, '%s', ts_json_text);
    fclose(fid);
    fprintf('Time series data saved: %s\n', ts_file);

    %% 5. Debug & Plotting
    if debug
        close all; 
        reciUnity  = [reci(:,1), reci(:,3), reci(:,2)];
        rsunUnity  = [rsun(:,1), rsun(:,3), rsun(:,2)];
        
        lonSun  = out.lonSun;
        latSun  = out.latSun;
        lonObj  = out.lonObj;
        latObj  = out.latObj;
        
        phaseAngleEci   = zeros(size(reci,1),1);
        phaseAngleUnity = zeros(size(reci,1),1);
        camAng          = zeros(size(reci,1),1);
        camAngTrasl     = zeros(size(reci,1),1);
        camAngTraslNorm = zeros(size(reci,1),1);
        
        for i = 1:size(reci,1)
            objSun = rsun(i,:) - reci(i,:); objSun = objSun/norm(objSun);
            objObs = rseci(i,:) - reci(i,:); objObs = objObs/norm(objObs);
            phaseAngleEci(i) = acosd(dot(objSun,objObs));
            
            objSunU = rsunUnity(i,:) - reciUnity(i,:); objSunU = objSunU/norm(objSunU);
            objObsU = [rseci(i,1), rseci(i,3), rseci(i,2)] - reciUnity(i,:); objObsU = objObsU/norm(objObsU);
            phaseAngleUnity(i) = acosd(dot(objSunU,objObsU));
            
            camSun = (rsun(i,:) - rseci(i,:))/norm(rsun(i,:) - rseci(i,:));
            camObj = (reci(i,:) - rseci(i,:))/norm(reci(i,:) - rseci(i,:));
            camAng(i) = acosd(dot(camSun,camObj));
            
            reci_norm = (reci(i,:) - rseci(i,:))/norm(reci(i,:) - rseci(i,:));
            rsun_norm = (rsun(i,:) - rseci(i,:))/norm(rsun(i,:) - rseci(i,:));
            camAngTrasl(i) = acosd(dot(rsun_norm,reci_norm));
            % Bug corretto: il secondo termine veniva normalizzato con la
            % norma di rsun_norm invece che con la propria. Nota: essendo
            % rsun_norm/reci_norm gia' versori, il risultato resta comunque
            % identico a camAngTrasl (e a camAng) - se serve una metrica
            % davvero distinta la formula andrebbe ridefinita.
            camAngTraslNorm(i) = acosd(dot((rsun_norm/100)/norm(rsun_norm/100), (reci_norm/100)/norm(reci_norm/100)));
        end
        
        fprintf('Save plots...\n');
        
        f1 = figure(1); f1.Visible = 'off'; plot(phaseAngleUnity); title('Phase Angle Unity');
        ax = gca; ax.Color = 'w'; ax.XColor = 'k'; ax.YColor = 'k'; ax.Title.Color = 'k'; drawnow;
        exportgraphics(f1, fullfile(plots_folder, 'Phase_Angle_Unity.png'), 'BackgroundColor', 'white');
        
        f2 = figure(2); f2.Visible = 'off'; plot(phaseAngleEci); title('Phase Angle ECI');
        ax = gca; ax.Color = 'w'; ax.XColor = 'k'; ax.YColor = 'k'; ax.Title.Color = 'k'; drawnow;
        exportgraphics(f2, fullfile(plots_folder, 'Phase_Angle_ECI.png'), 'BackgroundColor', 'white');

        f3 = figure(3); f3.Visible = 'off'; geoshow('landareas.shp','FaceColor','white'); 
        ax = gca; ax.Color = 'w'; ax.XColor = 'k'; ax.YColor = 'k'; ax.Title.Color = 'k'; drawnow;
        hold on;
        plot(lonSun(1)*180/pi, latSun(1)*180/pi, 'o','MarkerfaceColor','r', 'MarkerSize',15);
        plot(lonObj*180/pi, latObj*180/pi, '*', 'MarkerSize',10);
        plot(lon, lat, 'o','MarkerfaceColor','b',  'MarkerSize',15);
        xlabel("Lon"); ylabel("Lat"); title('Ground Track');
        exportgraphics(f3, fullfile(plots_folder, 'Ground_Track.png'), 'BackgroundColor', 'white');
        
        f4 = figure(4); f4.Visible = 'off'; plot(camAng); title('Cam Ang');
        ax = gca; ax.Color = 'w'; ax.XColor = 'k'; ax.YColor = 'k'; ax.Title.Color = 'k'; drawnow;
        exportgraphics(f4, fullfile(plots_folder, 'Cam_Angle.png'), 'BackgroundColor', 'white');
        
        f5 = figure(5); f5.Visible = 'off'; plot(camAngTrasl); title('Cam Ang Trasl');
        ax = gca; ax.Color = 'w'; ax.XColor = 'k'; ax.YColor = 'k'; ax.Title.Color = 'k'; drawnow;
        exportgraphics(f5, fullfile(plots_folder, 'Cam_Angle_Trasl.png'), 'BackgroundColor', 'white');
        
        f6 = figure(6); f6.Visible = 'off'; plot(camAngTraslNorm); title('Cam Ang Trasl Norm');
        ax = gca; ax.Color = 'w'; ax.XColor = 'k'; ax.YColor = 'k'; ax.Title.Color = 'k'; drawnow;
        exportgraphics(f6, fullfile(plots_folder, 'Cam_Angle_Trasl_Norm.png'), 'BackgroundColor', 'white');
        
        fprintf('Plot saved successfully\n');
    end
end

%% =======================================================================%
% == HELPER: RISOLUZIONE PATH OPZIONALI DA CONFIG O DIALOGO ==============%
%=========================================================================%
function filePath = resolveOptionalPath(cfgPaths, fieldName, dialogTitle)
    % Usa il percorso da configurazione se presente (uso STAR/headless),
    % altrimenti lo richiede con una finestra di dialogo (uso standalone).
    if isfield(cfgPaths, fieldName) && ~isempty(cfgPaths.(fieldName))
        filePath = cfgPaths.(fieldName);
        if ~exist(filePath, 'file')
            error('STAR_END010_REFLECTANCE_DETERMINATION: file not found: %s', filePath);
        end
        return
    end
    [file, folder] = uigetfile(pwd, dialogTitle);
    if isequal(file, 0)
        error('STAR_END010_REFLECTANCE_DETERMINATION: %s not selected.', dialogTitle);
    end
    filePath = fullfile(folder, file);
end

%% =======================================================================%
% == HELPER: KPI ENTRY ====================================================%
%=========================================================================%
function k = kpi_entry(id, name, value, unit, category, meets_requirement, threshold_ok, threshold_bad)
    % KPI_ENTRY  Build one entry of the reflectance_summary.json KPI catalog.
    k.id = id;
    k.name = name;
    k.value = value;
    k.unit = unit;
    k.category = category;
    k.meets_requirement = meets_requirement;
    k.threshold_ok = threshold_ok;
    k.threshold_bad = threshold_bad;
end
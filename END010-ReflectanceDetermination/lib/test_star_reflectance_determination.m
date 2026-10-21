%% STAR END-016: REFLECTANCE DETERMINATION ================================
% Esegue la generazione del CSV e la simulazione Unity.
%
% Input:
%   file_input  - Percorso del file JSON di configurazione (es. 'config.json')
%   path_output - Cartella in cui salvare tutti gli output (es. 'C:\Utenti\...\Output')


clear; clc; close all;

% I/O folders: rispetto alla cartella dello script (lib/ di END-010)
star_root = fileparts(fileparts(fileparts(mfilename('fullpath'))));
file_input = fullfile(star_root, 'Input', 'input_reflectance_determination.json');
path_output = fullfile(star_root, 'Output');

% RUN
status = STAR_END010_REFLECTANCE_DETERMINATION(file_input, path_output);


%% =======================================================================%
% == MAIN FUNCTION (API) =================================================%
%=========================================================================%
function [status] = STAR_END010_REFLECTANCE_DETERMINATION(configFile, output_folder)
    %% INITIALIZATION AND PATH SETUP
    main_folder = string(fileparts(fileparts(mfilename('fullpath'))));     % END010-ReflectanceDetermination
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
    
    % Configurazione Stazione
    [lat, lon, alt, ~] = readStationFile(cfg.paths.stationsJson, cfg.simulation.observatory);
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
        if ~cfg.flags.orbitEphemeris || ~cfg.flags.sunEphemeris || ~cfg.flags.obsEphemeris || ~cfg.flags.attEphemeris
            out = propagation(inputStruct);
            reci  = out.reci;
            rseci = out.rseci;
            rsun  = out.rsun;
            r     = out.r;
            s     = out.s;
            e     = out.El;
        end
        
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
        
        % Gestione Ephemeris Esterne
        if cfg.flags.orbitEphemeris
            [file, path]  = uigetfile(pwd, 'Select object OEM');
            [~, reci] = readOEM(fullfile(path,file), times);
        end
        if cfg.flags.sunEphemeris
            [file, path]  = uigetfile(pwd, 'Select Sun OEM');
            [~, rsun] = readOEM(fullfile(path,file), times);
        end
        if cfg.flags.obsEphemeris
            [file, path]   = uigetfile(pwd, 'Select observatory OEM');
            [~, rseci] = readOEM(fullfile(path,file), times);
        end
        if cfg.flags.attEphemeris
            [file, path] = uigetfile(pwd, 'Select attitude DBL, OEM or CSV');
            filepath     = fullfile(path,file);
            if endsWith(filepath,'.DBL')
                times = times + seconds(18);
                att   = readPROQUA(filepath, times);
            elseif endsWith(filepath,'.txt')
                [~, att]  = readOEM(filepath, times);
            elseif endsWith(filepath,'.csv')
                tmp  = readmatrix(filepath);
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
            camAngTraslNorm(i) = acosd(dot((rsun_norm/100)/norm(rsun_norm/100), (reci_norm/100)/norm(rsun_norm/100)));
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
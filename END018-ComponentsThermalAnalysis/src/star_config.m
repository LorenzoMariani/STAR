function cfg = star_config(opts)
% STAR_CONFIG  Parametri e SCELTE di input del modulo termico STAR.
%   cfg = star_config()       usa i default (modificabili qui sotto)
%   cfg = star_config(opts)   sovrascrive le scelte con la struct 'opts'
%                             (usata dal file di config JSON e dagli argomenti)
%
%   Campi di 'opts' riconosciuti (tutti opzionali):
%     form_factor       '1U'|'3U'|'6U'|'12U'
%     panels            'body'|'deployable'|'both'
%     n_internal_nodes  1|2|3
%     sar_power_W        numero [W]
%     sar_source        'passes'|'duty'
%     sar_duty           0..1
%     star_input_dir     cartella con gli output STAR (orbite/pass/assetto)
%     output_dir         cartella dove scrivere i risultati
% ------------------------------------------------------------------------------
if nargin<1 || isempty(opts), opts = struct(); end
here = fileparts(mfilename('fullpath'));
examples = fullfile(fileparts(here), 'examples');    % END018-ComponentsThermalAnalysis/examples

%% ============ SCELTE DI INPUT (default; sovrascrivibili da 'opts') ============
cfg.sat.form     = getf(opts,'form_factor','3U');        % '1U'|'3U'|'6U'|'12U'
cfg.panels.mode  = getf(opts,'panels','both');           % 'body'|'deployable'|'both'
cfg.nodes.config = getf(opts,'n_internal_nodes',3);      % 1|2|3
cfg.sar.Ppeak    = getf(opts,'sar_power_W',200);         % [W]
cfg.sar.source   = getf(opts,'sar_source','passes');     % 'passes'|'duty'
cfg.sar.duty     = getf(opts,'sar_duty',0.10);           % 0..1

%% ============ I/O (percorsi STAR) ============
cfg.io.root     = getf(opts,'star_input_dir', fullfile(examples,'esempi_io_star'));
cfg.io.sat_dir  = fullfile(cfg.io.root, 'output_constellation_optimizer');
cfg.io.att_dir  = fullfile(cfg.io.root, 'output_attitude_propagation');
cfg.io.pass_csv = fullfile(cfg.io.att_dir, 'selected_pass_summary.csv');
% assetto del pass: END-003 scrive il quaternione body->ECI in
% output_attitude_propagation_ECI.csv (cartella risultati) e il coniugato
% (ECI->body, per Unreal/END-007) in output_attitude_propagation.csv: si usa
% il primo se c'e', altrimenti il secondo coniugato (star_process). Fino al
% 2026-10-15 il secondo era letto come body->ECI: +Z a ~58 deg dal nadir nel pass.
cfg.io.att_csv  = fullfile(cfg.io.att_dir, 'output_attitude_propagation_ECI.csv');   % body->ECI
cfg.io.att_csv_eci2body = fullfile(cfg.io.att_dir, 'output_attitude_propagation.csv'); % ECI->body
cfg.io.out_dir  = getf(opts,'output_dir', fullfile(examples,'output_thermal'));
cfg.io.sat_glob = 'satellite_*.json';
cfg.io.imaging_purpose = 'imaging';

%% ============ simulazione ============
cfg.sim.dt     = 10;      % [s] passo integrazione
cfg.sim.out_dt = 60;      % [s] passo campionamento CSV
cfg.sim.use_attitude_detail = true;
cfg.sim.spinup_orbits = 100;  % orbite max prima di t = 0 per il regime periodico (0 = partenza a cfg.T0)
cfg.sim.spinup_tol    = 0.01; % [K] convergenza: variazione massima su un'orbita

%% ============ geometria dal form factor ============
switch upper(cfg.sat.form)
    case '1U',  cfg.sat.dims = [0.10 0.10 0.10];
    case '3U',  cfg.sat.dims = [0.10 0.10 0.30];
    case '6U',  cfg.sat.dims = [0.10 0.20 0.30];
    case '12U', cfg.sat.dims = [0.20 0.20 0.30];
    otherwise, error('star_config:form','Form factor "%s" non previsto (1U/3U/6U/12U).',cfg.sat.form);
end
Lx=cfg.sat.dims(1); Ly=cfg.sat.dims(2); Lz=cfg.sat.dims(3);
cfg.sat.Aface = [Ly*Lz Ly*Lz Lx*Lz Lx*Lz Lx*Ly Lx*Ly];
cfg.sat.rhoA  = 4.0; cfg.sat.faceCp = 900;

%% ============ ottiche pannelli solari (DALLA CALIBRAZIONE SIMBA) ============
cfg.sat.alpha_solar = 0.95; cfg.sat.eps_solar = 0.83;
cfg.sat.alpha_z = 0.88; cfg.sat.eps_z = 0.85;
cfg.sat.alpha = [cfg.sat.alpha_solar*ones(1,4) cfg.sat.alpha_z cfg.sat.alpha_z];
cfg.sat.eps   = [cfg.sat.eps_solar*ones(1,4)   cfg.sat.eps_z   cfg.sat.eps_z];
cfg.sat.solar_faces = [1 2 3 4];

%% ============ pannelli dispiegabili (fronte = ottiche calibrate) ============
cfg.dep.enable = ismember(lower(cfg.panels.mode), {'deployable','both'});
cfg.dep.nwings = 2;
cfg.dep.A      = 0.09;
cfg.dep.alphaF = cfg.sat.alpha_solar; cfg.dep.epsF = cfg.sat.eps_solar;
cfg.dep.alphaB = 0.20; cfg.dep.epsB = 0.85;
cfg.dep.mass   = 0.20; cfg.dep.cp = 900;
cfg.dep.Ghinge = 0.10;

%% ============ NODI INTERNI (scalati sul form factor; SAR su tutti) ============
cfg.sat.Ucount = max(1, round(prod(cfg.sat.dims)/0.001));
mtot = 1.33*cfg.sat.Ucount;
switch cfg.nodes.config
    case 1
        cfg.nodes.names={'CTR'};             cfg.nodes.mass=0.60*mtot;             cfg.nodes.cp=900;           cfg.nodes.Pconst=7.0;
    case 2
        cfg.nodes.names={'CTR','BAT'};        cfg.nodes.mass=[0.40 0.20]*mtot;      cfg.nodes.cp=[900 900];     cfg.nodes.Pconst=[5 2];
    case 3
        cfg.nodes.names={'CTR','BAT','SAR'};  cfg.nodes.mass=[0.37 0.20 0.30]*mtot; cfg.nodes.cp=[900 900 800]; cfg.nodes.Pconst=[5 2 0];
    otherwise, error('star_config:nodes','n_internal_nodes deve essere 1, 2 o 3.');
end
cfg.sar.node = 'SAR';

%% ============ conduttanze [W/K] (scambi con le facce scalano con l'area) ============
kA = sum(cfg.sat.Aface)/0.14;
cfg.cond.Gw_ctr  = 0.35*kA;
cfg.cond.Gw_bat  = 0.13*kA;
cfg.cond.Gc_bc   = 0.06;
cfg.cond.G_sarbus= 2.0;
cfg.cond.G_sarrad= 3.0*kA;
cfg.cond.radFace = 1;

%% ============ ambiente e limiti ============
cfg.env = struct('Gs',1361,'albedo',0.30,'qIR',237,'Re',6371e3,'mu',3.986004415e14, ...
                 'sigma',5.670374419e-8,'Tspace',3);
% orbita come END-001 (propagate_orbit_j2): quota sopra il raggio equatoriale, J2 secolare
cfg.env.Req = 6378137; cfg.env.J2 = 0.0010826261738522227;
cfg.limits.BAT = 25; cfg.limits.SAR = 85; cfg.limits.CTR = 60;
cfg.T0 = 0;
end

function v = getf(s,f,d)
% legge s.f se presente e non vuoto, altrimenti il default d
if isfield(s,f) && ~isempty(s.(f)), v = s.(f); else, v = d; end
end

function cfg = config_analisi()
% CONFIG_ANALISI  Scelte per l'ANALISI DIRETTA (senza file STAR).
% ------------------------------------------------------------------------------
% Imposta QUI il satellite e l'orbita, poi lancia run_analisi.
% Riusa lo stesso motore calibrato della modalita' STAR (star_build_model).
% ------------------------------------------------------------------------------

%% ================= SCELTE SATELLITE =================
form    = '3U';     % '1U' | '3U' | '6U' | '12U'
panels  = 'both';   % 'body' | 'deployable' | 'both'
nnodes  = 3;        % 1 (solo centrale) | 2 (+batteria) | 3 (+payload SAR)

%% ================= PAYLOAD SAR (se nnodes = 3) =================
sarW    = 200;      % [W] potenza erogata dal SAR
sarDuty = 0.20;     % frazione di orbita con SAR acceso (0-1)

%% ================= ORBITA =================
alt_km    = 550;                      % quota [km]
incl      = 97.6;                     % inclinazione [deg]
raan      = 0;                        % RAAN [deg] (per il calcolo di beta)
startDate = datetime(2025,3,21);      % data (per il calcolo di beta)
beta_fix  = [];                       % [] = beta calcolato da orbita+data; oppure un valore [deg]
Norb      = 8;                        % numero di orbite da simulare
attitude  = 'nadir';                  % 'nadir' | 'sun'

%% ================= (fine scelte) =================
% costruisce la parte fisica (geometria, ottiche calibrate, nodi, conduttanze)
cfg = star_config(struct('form_factor',form,'panels',panels, ...
                         'n_internal_nodes',nnodes,'sar_power_W',sarW));
% SAR a duty cycle (per l'analisi diretta)
cfg.sar.source = 'duty';  cfg.sar.duty = sarDuty;
% orbita impostata direttamente
cfg.orbit.alt       = alt_km*1e3;
cfg.orbit.incl      = incl;
cfg.orbit.raan      = raan;
cfg.orbit.startDate = startDate;
cfg.orbit.beta      = beta_fix;
cfg.orbit.Norb      = Norb;
cfg.orbit.attitude  = attitude;
cfg.sim.dt          = 10;             % [s] passo di integrazione
end

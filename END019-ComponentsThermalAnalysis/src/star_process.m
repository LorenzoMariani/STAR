function rows = star_process(cfg)
% STAR_PROCESS  Esegue il modulo termico su tutti i satelliti e scrive gli output.
%   Nucleo condiviso da run_star_thermal (interattivo, con grafici) e da
%   star_thermal_main (black box, senza grafici). Restituisce la tabella riga
%   per satellite e scrive output_thermal/ (CSV + JSON + CSV di costellazione).

if ~exist(cfg.io.out_dir,'dir'), mkdir(cfg.io.out_dir); end
% assetto reale del pass: file body->ECI, altrimenti quello per Unreal (coniugato)
att_csv = cfg.io.att_csv; att_conv = 'body2eci';
if ~isfile(att_csv) && isfield(cfg.io,'att_csv_eci2body') && isfile(cfg.io.att_csv_eci2body)
    att_csv = cfg.io.att_csv_eci2body; att_conv = 'eci2body';
end
att_ok = cfg.sim.use_attitude_detail && isfile(att_csv);

sats = dir(fullfile(cfg.io.sat_dir, cfg.io.sat_glob));
if isempty(sats)
    error('star_process:noinput','Nessun satellite_*.json in: %s', cfg.io.sat_dir);
end
rows = table();
cache = containers.Map();
for k = 1:numel(sats)
    orb    = star_read_orbit(fullfile(sats(k).folder, sats(k).name));
    passes = star_read_passes(cfg.io.pass_csv, orb.index, cfg.io.imaging_purpose, orb.start);
    R = star_thermal_run(cfg, orb, passes);
    Rp = [];
    if att_ok && ~isempty(passes)
        att = star_read_attitude(att_csv, orb.start, att_conv);
        if any(att.tsec(1) >= passes(:,1) & att.tsec(1) < passes(:,2))
            Rp = star_pass_detail(cfg, orb, att, R);
        end
    end
    % hot and cold design cases of this satellite (phase D): beta of the satellite, else of the window
    % (the hot case searches the life beta range for the hottest battery, star_hot_case; satellites with the same
    % altitude, inclination, betas and dissipation share the result)
    Cs = {};
    for c = 1:numel(cfg.cases)
        cs = cfg.cases(c);
        if iscell(cs), cs = cs{1}; end      % jsondecode gives a cell array when the cases have different fields
        b = R.beta; range = [];
        j = [];
        if isfield(cs,'satellite_index'), j = find(cs.satellite_index(:) == orb.index, 1); end
        if ~isempty(j) && isfield(cs,'beta_min_deg') && isfield(cs,'beta_max_deg')
            range = [cs.beta_min_deg(j) cs.beta_max_deg(j)];
        elseif ~isempty(j) && isfield(cs,'beta_deg')
            b = cs.beta_deg(j);
        end
        key = sprintf('%s|%.0f|%.3f|%.2f|%s|%.4f', cs.name, orb.alt, orb.incl, b, mat2str(round(range, 1)), cs.P_internal_W);
        if isKey(cache, key)
            Cs{end+1} = cache(key); %#ok<AGROW>
            continue
        end
        if ~isempty(range)
            C = star_hot_case(cfg, orb, cs, range(1), range(2));
        else
            C = star_design_case(cfg, orb, struct('name',cs.name,'beta_deg',b,'P_internal_W',cs.P_internal_W));
        end
        cache(key) = C;
        Cs{end+1} = C; %#ok<AGROW>
    end
    row = star_write_output(cfg, orb, R, Rp, passes, Cs);
    rows = [rows; struct2table(row)]; %#ok<AGROW>
end
writetable(rows, fullfile(cfg.io.out_dir,'thermal_constellation_output.csv'));
end

function rows = star_process(cfg)
% STAR_PROCESS  Esegue il modulo termico su tutti i satelliti e scrive gli output.
%   Nucleo condiviso da run_star_thermal (interattivo, con grafici) e da
%   star_thermal_main (black box, senza grafici). Restituisce la tabella riga
%   per satellite e scrive output_thermal/ (CSV + JSON + CSV di costellazione).

if ~exist(cfg.io.out_dir,'dir'), mkdir(cfg.io.out_dir); end
att_ok = cfg.sim.use_attitude_detail && isfile(cfg.io.att_csv);

sats = dir(fullfile(cfg.io.sat_dir, cfg.io.sat_glob));
if isempty(sats)
    error('star_process:noinput','Nessun satellite_*.json in: %s', cfg.io.sat_dir);
end
rows = table();
for k = 1:numel(sats)
    orb    = star_read_orbit(fullfile(sats(k).folder, sats(k).name));
    passes = star_read_passes(cfg.io.pass_csv, orb.index, cfg.io.imaging_purpose, orb.start);
    R = star_thermal_run(cfg, orb, passes);
    Rp = [];
    if att_ok && ~isempty(passes)
        att = star_read_attitude(cfg.io.att_csv, orb.start);
        if any(att.tsec(1) >= passes(:,1) & att.tsec(1) < passes(:,2))
            Rp = star_pass_detail(cfg, orb, att, R);
        end
    end
    row = star_write_output(cfg, orb, R, Rp, passes);
    rows = [rows; struct2table(row)]; %#ok<AGROW>
end
writetable(rows, fullfile(cfg.io.out_dir,'thermal_constellation_output.csv'));
end

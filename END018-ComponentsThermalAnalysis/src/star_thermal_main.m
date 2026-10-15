function rows = star_thermal_main(cfg_json)
% STAR_THERMAL_MAIN  Modulo termico END-018 come lo lancia STAR (stesso ingresso della black box).
%   star_thermal_main('input_termico.json') legge le scelte dal file JSON
%   (stessi campi di star_config: form_factor, panels, n_internal_nodes,
%   sar_power_W, sar_source, sar_duty, star_input_dir, output_dir), esegue
%   star_process e scrive gli output in output_dir. I percorsi relativi nel
%   JSON sono relativi alla cartella del JSON (gli esempi in examples/).
%   Il runner STAR (BackEnd/runners/end018_runner.py) lo chiama con
%     matlab -batch "addpath('<END018>/src'); star_thermal_main('<input_termico.json>')"
%   blackbox_build/star_thermal.exe e' la compilazione della versione
%   consegnata il 2026-10-15 (prima delle correzioni annotate in README.md).
if nargin < 1 || isempty(cfg_json), cfg_json = 'input_termico.json'; end
cfg_json = char(cfg_json);
if ~isfile(cfg_json)
    error('star_thermal_main:config', 'File di configurazione non trovato: %s', cfg_json);
end
if ~is_absolute(cfg_json), cfg_json = fullfile(pwd, cfg_json); end
opts = jsondecode(fileread(cfg_json));
base = fileparts(cfg_json);
for f = {'star_input_dir', 'output_dir'}
    if isfield(opts, f{1}) && ~isempty(opts.(f{1})) && ~is_absolute(opts.(f{1}))
        opts.(f{1}) = fullfile(base, opts.(f{1}));
    end
end
cfg = star_config(opts);
fprintf('== STAR THERMAL ==\n');
sar = '';
if cfg.nodes.config == 3, sar = sprintf('  SAR=%gW (%s)', cfg.sar.Ppeak, cfg.sar.source); end
fprintf('form=%s  pannelli=%s  nodi=%d%s\n', cfg.sat.form, cfg.panels.mode, cfg.nodes.config, sar);
fprintf('input : %s\noutput: %s\n', cfg.io.root, cfg.io.out_dir);
rows = star_process(cfg);
fprintf('OK: %d satelliti elaborati. Risultati in %s\n', height(rows), cfg.io.out_dir);
end

function tf = is_absolute(p)
p = char(p);
tf = ~isempty(regexp(p, '^([A-Za-z]:[\\/]|[\\/])', 'once'));
end

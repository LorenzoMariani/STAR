%% ======================================================================
%  RUN_STAR_THERMAL  —  Modulo termico della pipeline STAR (3U con SAR)
%
%  Legge gli output di constellation_optimizer (orbite) e attitude_propagation
%  (pass + assetto), gira il modello LCM CALIBRATO su un 3U con pannelli
%  body-mounted + dispiegabili e 3 nodi interni (CTR, BAT, SAR), e scrive i
%  risultati in output_thermal/ (CSV + JSON per satellite + CSV di costellazione).
%
%  Non modifica il codice TAURUS: e' una copia adattata all'I/O di STAR.
%  Tutti i parametri sono in star_config.m
% ======================================================================
clear; close all; clc;
cfg = star_config();                 % scelte di input in star_config.m (o passa una struct opts)

% --- elaborazione (lettura input STAR -> termica -> scrittura output) ---
rows = star_process(cfg);            % stesso nucleo usato dalla black box
disp(rows);
fprintf('Output scritti in: %s\n', cfg.io.out_dir);

sats = dir(fullfile(cfg.io.sat_dir, cfg.io.sat_glob));

%% --- grafico (verifica): ogni faccia ESPLICITA + nodi interni ---
[~,kbest] = max(rows.n_imaging_passes); if isempty(kbest), kbest=1; end
orb = star_read_orbit(fullfile(sats(kbest).folder, sats(kbest).name));
passes = star_read_passes(cfg.io.pass_csv, orb.index, cfg.io.imaging_purpose, orb.start);
lbl = sprintf('SAT-%02d', orb.index);
R = star_thermal_run(cfg, orb, passes); th=R.t/3600;

% --- colore/stile per ogni nodo (una faccia = un colore, dispieg. tratteggiati, interni spessi) ---
faceCol = containers.Map({'+X','-X','+Y','-Y','+Z','-Z'}, ...
   {[0.85 0.10 0.10],[1.00 0.55 0.10],[0.20 0.65 0.20],[0.55 0.35 0.20],[0.55 0.30 0.75],[0.50 0.50 0.50]});
intCol  = containers.Map({'CTR','BAT','SAR'}, {[0 0.30 0.85],[0 0.70 0.70],[0 0 0]});
depPal  = {[0.90 0.30 0.70],[0.60 0.60 0.10],[0.10 0.45 0.75]};
Nn=numel(R.names); NC=zeros(Nn,3); NLS=cell(Nn,1); NLW=zeros(Nn,1); dc=0;
for j=1:Nn
    nm=R.names{j};
    if isKey(faceCol,nm),        NC(j,:)=faceCol(nm); NLS{j}='-';  NLW(j)=1.4;
    elseif startsWith(nm,'PANdep'), dc=dc+1; NC(j,:)=depPal{mod(dc-1,numel(depPal))+1}; NLS{j}='--'; NLW(j)=1.8;
    elseif isKey(intCol,nm),     NC(j,:)=intCol(nm);  NLS{j}='-';  NLW(j)=2.8;
    else,                        NC(j,:)=[0.3 0.3 0.3]; NLS{j}='-'; NLW(j)=1.2;
    end
end
plotNodes = @(idx) arrayfun(@(j) plot(th,R.T(:,j),NLS{j},'Color',NC(j,:),'LineWidth',NLW(j)), idx);
extIdx = find(R.isExt); intIdx = find(~R.isExt);

% --- Grafico 1: TUTTE le misure insieme ---
figure('Color','w','Name','STAR — tutte le misure','Position',[60 90 1050 560]); hold on; grid on;
plotNodes(1:Nn);
for p=1:size(passes,1), xline(passes(p,1)/3600,'k--'); end
yline(cfg.limits.BAT,'g:','lim BAT'); xlabel('t [h]'); ylabel('T [C]');
legend(R.names,'Location','eastoutside');
title(sprintf('%s %s (STAR) — tutte le misure — beta=%.0f°, quota=%.0f km', ...
    cfg.sat.form, lbl, R.beta, orb.alt/1e3));

% --- Grafico 2: due subplot ESTERNE | INTERNE ---
figure('Color','w','Name','STAR — esterne vs interne','Position',[90 90 1250 520]);
tl=tiledlayout(1,2);
nexttile; hold on; grid on; plotNodes(extIdx(:)');
for p=1:size(passes,1), xline(passes(p,1)/3600,'k--'); end
xlabel('t [h]'); ylabel('T [C]'); legend(R.names(extIdx),'Location','eastoutside');
title('parti esterne (facce + pannelli)');
nexttile; hold on; grid on; plotNodes(intIdx(:)');
for p=1:size(passes,1), xline(passes(p,1)/3600,'k--'); end
yline(cfg.limits.BAT,'g:','lim BAT'); xlabel('t [h]'); ylabel('T [C]');
legend(R.names(intIdx),'Location','eastoutside'); title('parti interne');
title(tl, sprintf('%s %s (STAR) — esterne vs interne — beta=%.0f°', cfg.sat.form, lbl, R.beta));

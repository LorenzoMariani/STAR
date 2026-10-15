%% ======================================================================
%  RUN_ANALISI  —  Analisi termica diretta di un CubeSat (sorgente aperto)
%
%  Imposta le scelte in config_analisi.m (taglia, pannelli, nodi, SAR, orbita)
%  ed esegui questo script: stampa il riepilogo, traccia i grafici e salva un
%  CSV con le temperature. NON richiede i file STAR.
%
%  (Per l'interfaccia con i moduli STAR usa invece run_star_thermal.m)
% ======================================================================
clear; close all; clc;
cfg = config_analisi();
R   = lcm_solve(cfg);
th  = R.t/3600;

%% --- riepilogo a schermo ---
fprintf('ANALISI TERMICA — %s | pannelli: %s | nodi interni: %d\n', cfg.sat.form, cfg.panels.mode, cfg.nodes.config);
if cfg.nodes.config==3
    fprintf('SAR: %g W, duty %.0f%%\n', cfg.sar.Ppeak, cfg.sar.duty*100);
end
fprintf('orbita: quota %g km, beta %.1f deg, Torb %.1f min, %d orbite\n', ...
    cfg.orbit.alt/1e3, R.beta, R.Torb/60, cfg.orbit.Norb);
last = R.t > R.t(end)-R.Torb;     % ultima orbita (regime)
fprintf('\n%-8s %8s %8s %8s   [C, ultima orbita]\n','nodo','min','max','media');
for j=1:numel(R.names)
    fprintf('  %-6s %8.1f %8.1f %8.1f\n', R.names{j}, min(R.T(last,j)), max(R.T(last,j)), mean(R.T(last,j)));
end

%% --- export CSV ---
Tt = table(round(th,4),'VariableNames',{'t_h'});
for j=1:numel(R.names), Tt.(matlab.lang.makeValidName(R.names{j})) = round(R.T(:,j),2); end
writetable(Tt,'risultati_analisi.csv');
fprintf('\nSalvato risultati_analisi.csv\n');

%% --- grafici: colore/etichetta per ogni nodo ---
faceCol = containers.Map({'+X','-X','+Y','-Y','+Z','-Z'}, ...
   {[0.85 0.10 0.10],[1.00 0.55 0.10],[0.20 0.65 0.20],[0.55 0.35 0.20],[0.55 0.30 0.75],[0.50 0.50 0.50]});
intCol  = containers.Map({'CTR','BAT','SAR'}, {[0 0.30 0.85],[0 0.70 0.70],[0 0 0]});
depPal  = {[0.90 0.30 0.70],[0.60 0.60 0.10],[0.10 0.45 0.75]};
Nn=numel(R.names); NC=zeros(Nn,3); NLS=cell(Nn,1); NLW=zeros(Nn,1); dc=0;
for j=1:Nn
    nm=R.names{j};
    if isKey(faceCol,nm),            NC(j,:)=faceCol(nm); NLS{j}='-';  NLW(j)=1.4;
    elseif startsWith(nm,'PANdep'),  dc=dc+1; NC(j,:)=depPal{mod(dc-1,numel(depPal))+1}; NLS{j}='--'; NLW(j)=1.8;
    elseif isKey(intCol,nm),         NC(j,:)=intCol(nm);  NLS{j}='-';  NLW(j)=2.8;
    else,                            NC(j,:)=[0.3 0.3 0.3]; NLS{j}='-'; NLW(j)=1.2;
    end
end
plotNodes = @(idx) arrayfun(@(j) plot(th,R.T(:,j),NLS{j},'Color',NC(j,:),'LineWidth',NLW(j)), idx);
extIdx=find(R.isExt); intIdx=find(~R.isExt);

% Grafico 1 — tutte le misure insieme
figure('Color','w','Name','Analisi termica — tutte le misure','Position',[60 90 1050 560]); hold on; grid on;
plotNodes(1:Nn); yline(cfg.limits.BAT,'g:','lim BAT');
xlabel('Tempo [h]'); ylabel('T [°C]'); legend(R.names,'Location','eastoutside');
title(sprintf('%s — pannelli %s — beta=%.0f°, quota=%.0f km', cfg.sat.form, cfg.panels.mode, R.beta, cfg.orbit.alt/1e3));

% Grafico 2 — esterne | interne
figure('Color','w','Name','Analisi termica — esterne vs interne','Position',[90 90 1250 520]);
tl=tiledlayout(1,2);
nexttile; hold on; grid on; plotNodes(extIdx(:)');
xlabel('Tempo [h]'); ylabel('T [°C]'); legend(R.names(extIdx),'Location','eastoutside');
title('parti esterne (facce + pannelli)');
nexttile; hold on; grid on; plotNodes(intIdx(:)');
yline(cfg.limits.BAT,'g:','lim BAT'); xlabel('Tempo [h]'); ylabel('T [°C]');
legend(R.names(intIdx),'Location','eastoutside'); title('parti interne');
title(tl, sprintf('%s — esterne vs interne — beta=%.0f°', cfg.sat.form, R.beta));

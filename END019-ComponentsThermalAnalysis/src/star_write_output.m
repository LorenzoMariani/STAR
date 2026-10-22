function row = star_write_output(cfg, orb, R, Rp, passes, Cs)
% STAR_WRITE_OUTPUT  Scrive output termici in formato STAR + riga di costellazione.
%   Robusto al numero di nodi interni (1/2/3). Include esplicitamente le
%   temperature dei PANNELLI SOLARI (facce laterali calibrate + dispiegabili).

if nargin < 6, Cs = {}; end
label = sprintf('SAT-%02d', orb.index);
outd = cfg.io.out_dir; if ~exist(outd,'dir'), mkdir(outd); end
gi = @(n) find(strcmp(R.names,n),1);
getmax = @(n) local_stat(R,gi,n,@max);

%% --- CSV serie temporale (sottocampionato) — TUTTI i nodi, pannelli compresi ---
step = max(1, round(cfg.sim.out_dt/cfg.sim.dt));
idx  = 1:step:size(R.T,1);
ts   = string(R.tutc(idx), 'yyyy-MM-dd''T''HH:mm:ss''Z''');
Tt = table(ts, 'VariableNames', {'timestamp_utc'});
for j=1:numel(R.names)
    Tt.(local_name(['T_' R.names{j}])) = round(R.T(idx,j),2);
end
Tt.sar_on  = double(R.sar_on(idx));
Tt.eclipse = double(~R.lit(idx));
writetable(Tt, fullfile(outd, sprintf('output_thermal_%s.csv', label)));

%% --- statistiche per nodo ---
mn=min(R.T,[],1); mx=max(R.T,[],1); av=mean(R.T,1);
Tbat=getmax('BAT'); Tctr=getmax('CTR'); Tsar_orb=getmax('SAR'); Tbat_min=local_stat(R,gi,'BAT',@min);
Tsar_pass = NaN; if ~isempty(Rp) && ~isempty(gi('SAR')), Tsar_pass = max(Rp.T(:,gi('SAR'))); end
% pannelli solari (dalla calibrazione): facce laterali + dispiegabili
solIdx = find(R.M.isSolar);
solMin = min(min(R.T(:,solIdx))); solMax = max(max(R.T(:,solIdx))); solMean = mean(R.T(:,solIdx),'all');

%% --- JSON riassunto ---
S.module_id='THERMAL-LCM'; S.satellite_label=label; S.source_json=orb.source;
S.generated_at=char(datetime('now','Format','yyyy-MM-dd HH:mm:ss'));
S.config=struct('form_factor',cfg.sat.form,'panels',cfg.panels.mode, ...
                'n_internal_nodes',cfg.nodes.config,'sar_source',cfg.sar.source);
S.orbit=struct('alt_m',orb.alt,'inclination_deg',orb.incl,'raan_deg',orb.raan, ...
               'sim_start',char(orb.start),'sim_hours',orb.sim_hours);
S.thermal=struct('beta_deg',round(R.beta,2),'orbital_period_min',round(R.Torb/60,2), ...
                 'n_imaging_passes',size(passes,1),'spinup_orbits',R.spinup_orbits);
if cfg.nodes.config==3
    S.thermal.sar_peak_W=cfg.sar.Ppeak; S.thermal.sar_source=cfg.sar.source;
    if strcmpi(cfg.sar.source,'duty'), S.thermal.sar_duty=cfg.sar.duty; end
end
S.nodes=struct();
for j=1:numel(R.names)
    S.nodes.(local_name(R.names{j}))=struct('min_C',round(mn(j),2),'max_C',round(mx(j),2),'mean_C',round(av(j),2));
end
S.solar_panels=struct('min_C',round(solMin,2),'max_C',round(solMax,2),'mean_C',round(solMean,2), ...
                      'note','ottiche dalla calibrazione SIMBA');
S.peaks=struct('CTR_max_C',round(Tctr,2));
if ~isnan(Tbat),     S.peaks.BAT_max_C=round(Tbat,2); end
if ~isnan(Tsar_orb), S.peaks.SAR_max_C_orbit=round(Tsar_orb,2); S.peaks.SAR_max_C_pass_realattitude=round(Tsar_pass,2); end
S.limits=rmfield(cfg.limits,'BAT_min'); S.limits.BAT_min=cfg.limits.BAT_min;
if ~isnan(Tbat_min), S.peaks.BAT_min_C=round(Tbat_min,2); end
% design cases (phase D): hot = max |beta| of the life + max dissipation, cold = longest eclipse + min dissipation
caseT = struct('hot',struct('BAT_max_C',NaN,'CTR_max_C',NaN,'beta_deg',NaN,'P_internal_W',NaN), ...
               'cold',struct('BAT_min_C',NaN,'CTR_min_C',NaN,'beta_deg',NaN,'P_internal_W',NaN));
for c = 1:numel(Cs)
    C = Cs{c}; k = @(n) find(strcmp(C.names,n),1);
    S.design_cases.(C.name) = struct('beta_deg',round(C.beta_deg,3),'P_internal_W',round(C.P_internal_W,3), ...
        'eclipse_min',round(C.eclipse_min,2),'periodic_orbits',C.orbits, 'rule',case_rule(C), 'beta_scan',case_scan(C), ...
        'nodes',cell2struct(arrayfun(@(j) struct('min_C',round(C.Tmin(j),2),'max_C',round(C.Tmax(j),2)), ...
                1:numel(C.names),'UniformOutput',false), cellfun(@local_name,C.names,'UniformOutput',false), 2));
    if strcmp(C.name,'hot')
        caseT.hot = struct('BAT_max_C',pick(C.Tmax,k('BAT')),'CTR_max_C',pick(C.Tmax,k('CTR')),'beta_deg',C.beta_deg,'P_internal_W',C.P_internal_W);
    elseif strcmp(C.name,'cold')
        caseT.cold = struct('BAT_min_C',pick(C.Tmin,k('BAT')),'CTR_min_C',pick(C.Tmin,k('CTR')),'beta_deg',C.beta_deg,'P_internal_W',C.P_internal_W);
    end
end
S.violations=struct('CTR_over',Tctr>cfg.limits.CTR);
if ~isnan(Tbat),     S.violations.BAT_over=Tbat>cfg.limits.BAT; end
if ~isnan(Tbat_min) && ~isnan(cfg.limits.BAT_min), S.violations.BAT_under=Tbat_min<cfg.limits.BAT_min; end
if ~isnan(caseT.hot.BAT_max_C),  S.violations.BAT_over_hot=caseT.hot.BAT_max_C>cfg.limits.BAT; end
if ~isnan(caseT.cold.BAT_min_C) && ~isnan(cfg.limits.BAT_min), S.violations.BAT_under_cold=caseT.cold.BAT_min_C<cfg.limits.BAT_min; end
if ~isnan(Tsar_orb), S.violations.SAR_over=max([Tsar_orb Tsar_pass],[],'omitnan')>cfg.limits.SAR; end
fid=fopen(fullfile(outd,sprintf('thermal_summary_%s.json',label)),'w');
fwrite(fid, jsonencode(S,'PrettyPrint',true)); fclose(fid);

%% --- riga per il CSV di costellazione ---
row.satellite_index=orb.index; row.satellite_label=string(label);
row.form_factor=string(cfg.sat.form); row.n_nodes=cfg.nodes.config;
row.beta_deg=round(R.beta,2); row.n_imaging_passes=size(passes,1);
row.SAR_max_C=round(max([Tsar_orb Tsar_pass],[],'omitnan'),2);
row.BAT_max_C=round(Tbat,2); row.CTR_max_C=round(Tctr,2);
row.solarpanel_max_C=round(solMax,2);
row.BAT_over_limit=(~isnan(Tbat) && Tbat>cfg.limits.BAT);
row.BAT_min_C=round(Tbat_min,2);
row.BAT_under_limit=(~isnan(Tbat_min) && Tbat_min<cfg.limits.BAT_min);
row.hot_beta_deg=round(caseT.hot.beta_deg,2); row.hot_P_internal_W=round(caseT.hot.P_internal_W,3);
row.hot_BAT_max_C=round(caseT.hot.BAT_max_C,2); row.hot_CTR_max_C=round(caseT.hot.CTR_max_C,2);
row.cold_beta_deg=round(caseT.cold.beta_deg,2); row.cold_P_internal_W=round(caseT.cold.P_internal_W,3);
row.cold_BAT_min_C=round(caseT.cold.BAT_min_C,2); row.cold_CTR_min_C=round(caseT.cold.CTR_min_C,2);
row.BAT_hot_over_limit=(~isnan(caseT.hot.BAT_max_C) && caseT.hot.BAT_max_C>cfg.limits.BAT);
row.BAT_cold_under_limit=(~isnan(caseT.cold.BAT_min_C) && caseT.cold.BAT_min_C<cfg.limits.BAT_min);
row.BAT_min_limit_C=cfg.limits.BAT_min; row.BAT_max_limit_C=cfg.limits.BAT;
row.csv=string(sprintf('output_thermal_%s.csv',label));
end

function r = case_rule(C)
if isfield(C,'rule'), r = C.rule; elseif strcmp(C.name,'cold'), r = 'longest eclipse over the mission life, idle dissipation'; else, r = 'fixed beta'; end
end

function s = case_scan(C)
% |beta| searched by star_hot_case and the node maximum at each ([] for a fixed-beta case)
s = [];
if isfield(C,'scan'), s = struct('beta_deg',num2cell(C.scan(:,1)'),'max_C',num2cell(round(C.scan(:,2)',2))); end
end

function v = pick(x,k)
if isempty(k), v = NaN; else, v = x(k); end
end

function v = local_stat(R,gi,n,fun)
k=gi(n); if isempty(k), v=NaN; else, v=fun(R.T(:,k)); end
end

function s = local_name(s)
% '+X' and '-X' would both become '_X' with makeValidName: spell the sign (pX, mX)
s = matlab.lang.makeValidName(regexprep(regexprep(s,'\+','p'),'-','m'));
end

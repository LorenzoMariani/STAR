function R = star_thermal_run(cfg, orb, passes)
% STAR_THERMAL_RUN  Propagazione termica sull'intera missione (orbita STAR).
%   Orbita circolare a quota orb.alt, assetto NADIR analitico, beta da orbita+data.
%   Il SAR eroga cfg.sar.Ppeak nelle finestre 'passes' [t_on t_off] (s dal sim start).
%   Integrazione Backward-Euler con radiazione linearizzata (stabile).
%
%   Orbita e fase (star_orbit_phase): raggio Re_eq + quota e moto con i
%   termini J2 come END-001, satellite a t = 0 nella sua posizione reale
%   rispetto al Sole, cosi' le eclissi sono allineate ai pass di END-003.
%   Condizione iniziale: regime periodico (cfg.sim.spinup_orbits orbite
%   prima di t = 0, SAR spento nei pass / a duty cycle come nella missione),
%   non piu' tutti i nodi a cfg.T0 = 0 degC a t = 0 (prima del 2026-10-15
%   minimi e picchi del primo giorno risentivano della partenza a freddo).
%
%   R: .t [Nt x1] s, .tutc datetime, .T [Nt x Nn] degC, .names, .isExt,
%      .sar_on [Nt], .lit [Nt], .Torb, .beta, .M (modello), .spinup_orbits

M = star_build_model(cfg);
[r, uDot, phi0] = star_orbit_phase(cfg, orb);
Torb = 2*pi/uDot;
beta = star_beta(orb); s = [cosd(beta);0;sind(beta)];
% il tempo di analisi si PLASMA sulla durata fornita dalla propagazione orbitale
dt = cfg.sim.dt; N = round(orb.sim_hours*3600/dt);
P = struct('M',M,'e',cfg.env,'r',r,'uDot',uDot,'phi0',phi0,'s',s,'Cdt',M.C/dt, ...
           'cfg',cfg,'passes',passes,'Torb',Torb,'hasSAR',~isempty(M.iSAR));

% regime periodico: ripete l'orbita che precede t = 0 fino a convergenza
T = (273.15+cfg.T0)*ones(M.Nn,1);
nO = round(Torb/dt); nspin = 0;
for o = 1:cfg.sim.spinup_orbits
    T1 = T;
    for n = 1:nO
        T = star_thermal_step(P, T, (n-1-nO)*dt);
    end
    nspin = o;
    if max(abs(T - T1)) < cfg.sim.spinup_tol, break; end
end

Tsave=zeros(N,M.Nn); sar_on=false(N,1); lit=zeros(N,1);
for n=1:N
    [T, lit(n), sar_on(n)] = star_thermal_step(P, T, (n-1)*dt);
    Tsave(n,:)=T'-273.15;
end
R.t=(0:N-1)'*dt; R.tutc=orb.start+seconds(R.t);
R.T=Tsave; R.names=M.names; R.isExt=M.isExt;
R.sar_on=sar_on; R.lit=lit; R.Torb=Torb; R.beta=beta; R.M=M; R.spinup_orbits=nspin;
end

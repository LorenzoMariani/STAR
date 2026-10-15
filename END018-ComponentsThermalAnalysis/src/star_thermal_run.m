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
        T = thermal_step(P, T, (n-1-nO)*dt);
    end
    nspin = o;
    if max(abs(T - T1)) < cfg.sim.spinup_tol, break; end
end

Tsave=zeros(N,M.Nn); sar_on=false(N,1); lit=zeros(N,1);
for n=1:N
    [T, lit(n), sar_on(n)] = thermal_step(P, T, (n-1)*dt);
    Tsave(n,:)=T'-273.15;
end
R.t=(0:N-1)'*dt; R.tutc=orb.start+seconds(R.t);
R.T=Tsave; R.names=M.names; R.isExt=M.isExt;
R.sar_on=sar_on; R.lit=lit; R.Torb=Torb; R.beta=beta; R.M=M; R.spinup_orbits=nspin;
end

function [T, L, on] = thermal_step(P, T, ts)
% un passo Backward-Euler all'istante ts [s dal sim start]
M=P.M; e=P.e; cfg=P.cfg; sig=e.sigma; Tsp=e.Tspace; Re=e.Re; r=P.r; s=P.s;
phi=P.phi0+P.uDot*ts;
rhat=[cos(phi);sin(phi);0]; vel=[-sin(phi);cos(phi);0];
dotrs=rhat'*s; perp=r*sqrt(max(0,1-dotrs^2)); L=double(~(dotrs<0 && perp<Re));
zb=-rhat; xb=vel; yb=cross(zb,xb); Rb=[xb yb zb]; sunNad=max(0,s'*(-rhat));
Q=zeros(M.Nn,1);
for fi=1:6
    nin=Rb*M.normals(:,fi);
    cs=max(0,nin'*s); cn=max(0,nin'*(-rhat)); Fv=(Re/r)^2*cn;
    Q(fi)=M.alpha(fi)*e.Gs*cs*L*M.Aface(fi) + M.eps(fi)*e.qIR*Fv*M.Aface(fi) ...
        + M.alpha(fi)*e.albedo*e.Gs*Fv*sunNad*L*M.Aface(fi);
end
for w=1:M.npan       % pannello dispiegabile sun-tracking: fronte al Sole
    Q(M.nf+w)=cfg.dep.alphaF*e.Gs*L*cfg.dep.A;
end
Q=Q+M.Pc;
% SAR: solo se il nodo esiste; acceso nei pass imaging oppure a duty cycle
on = false;
if P.hasSAR
    if strcmpi(cfg.sar.source,'duty')
        on = mod(ts,P.Torb) < cfg.sar.duty*P.Torb;
    else
        on = any(ts>=P.passes(:,1) & ts<P.passes(:,2));
    end
    if on, Q(M.iSAR)=Q(M.iSAR)+cfg.sar.Ppeak; end
end
gsp=4*sig*M.epsA.*T.^3; src=sig*M.epsA.*(3*T.^4+Tsp^4);
A=M.Lc+diag(P.Cdt+gsp); b=P.Cdt.*T+Q+src;
T=A\b;
end

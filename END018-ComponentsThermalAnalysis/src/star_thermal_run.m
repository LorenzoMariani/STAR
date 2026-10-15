function R = star_thermal_run(cfg, orb, passes)
% STAR_THERMAL_RUN  Propagazione termica sull'intera missione (orbita STAR).
%   Orbita circolare a quota orb.alt, assetto NADIR analitico, beta da orbita+data.
%   Il SAR eroga cfg.sar.Ppeak nelle finestre 'passes' [t_on t_off] (s dal sim start).
%   Integrazione Backward-Euler con radiazione linearizzata (stabile).
%
%   R: .t [Nt x1] s, .tutc datetime, .T [Nt x Nn] degC, .names, .isExt,
%      .sar_on [Nt], .lit [Nt], .Torb, .beta, .M (modello)

M = star_build_model(cfg); e = cfg.env; sig=e.sigma; Tsp=e.Tspace; Re=e.Re;
r = Re+orb.alt; Torb = 2*pi*sqrt(r^3/e.mu);
beta = star_beta(orb); s = [cosd(beta);0;sind(beta)];
% il tempo di analisi si PLASMA sulla durata fornita dalla propagazione orbitale
dt = cfg.sim.dt; N = round(orb.sim_hours*3600/dt);
hasSAR = ~isempty(M.iSAR);

T = (273.15+cfg.T0)*ones(M.Nn,1); Tsave=zeros(N,M.Nn); sar_on=false(N,1); lit=zeros(N,1);
Cdt = M.C/dt;
for n=1:N
    ts=(n-1)*dt; phi=2*pi*ts/Torb;
    rhat=[cos(phi);sin(phi);0]; vel=[-sin(phi);cos(phi);0];
    dotrs=rhat'*s; perp=r*sqrt(max(0,1-dotrs^2)); L=double(~(dotrs<0 && perp<Re)); lit(n)=L;
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
    if hasSAR
        if strcmpi(cfg.sar.source,'duty')
            on = mod(ts,Torb) < cfg.sar.duty*Torb;
        else
            on = any(ts>=passes(:,1) & ts<passes(:,2));
        end
        if on, Q(M.iSAR)=Q(M.iSAR)+cfg.sar.Ppeak; end
    end
    sar_on(n)=on;
    gsp=4*sig*M.epsA.*T.^3; src=sig*M.epsA.*(3*T.^4+Tsp^4);
    A=M.Lc+diag(Cdt+gsp); b=Cdt.*T+Q+src;
    T=A\b; Tsave(n,:)=T'-273.15;
end
R.t=(0:N-1)'*dt; R.tutc=orb.start+seconds(R.t);
R.T=Tsave; R.names=M.names; R.isExt=M.isExt;
R.sar_on=sar_on; R.lit=lit; R.Torb=Torb; R.beta=beta; R.M=M;
end

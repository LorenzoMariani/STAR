function R = lcm_solve(cfg)
% LCM_SOLVE  Propagazione termica per l'ANALISI DIRETTA (orbita da cfg.orbit).
%   Orbita circolare, assetto nadir o sun, beta fisso o calcolato da orbita+data,
%   SAR a duty cycle. Integrazione Backward-Euler con radiazione linearizzata.
%   Usa lo stesso modello calibrato della modalita' STAR (star_build_model).
%
%   R: .t [s], .T [Nt x Nn] (degC), .names, .isExt, .M, .sar_on, .lit, .Torb, .beta

M = star_build_model(cfg);
e = cfg.env; sig=e.sigma; Tsp=e.Tspace; Re=e.Re;
r = Re+cfg.orbit.alt; Torb = 2*pi*sqrt(r^3/e.mu);

% beta: valore fisso oppure calcolato da orbita + data
if isempty(cfg.orbit.beta)
    beta = star_beta(struct('incl',cfg.orbit.incl,'raan',cfg.orbit.raan,'start',cfg.orbit.startDate));
else
    beta = cfg.orbit.beta;
end
s = [cosd(beta);0;sind(beta)];
mode = lower(cfg.orbit.attitude);
dt = cfg.sim.dt; N = round(cfg.orbit.Norb*Torb/dt);
hasSAR = ~isempty(M.iSAR);

T=(273.15+cfg.T0)*ones(M.Nn,1); Tsave=zeros(N,M.Nn); sar_on=false(N,1); lit=zeros(N,1); Cdt=M.C/dt;
for n=1:N
    ts=(n-1)*dt; phi=2*pi*ts/Torb;
    rhat=[cos(phi);sin(phi);0]; vel=[-sin(phi);cos(phi);0];
    dotrs=rhat'*s; perp=r*sqrt(max(0,1-dotrs^2)); L=double(~(dotrs<0 && perp<Re)); lit(n)=L;
    % assetto: nadir (default) oppure sun-pointing
    switch mode
        case 'sun'
            zb=s; xb=vel-(vel'*s)*s;
            if norm(xb)<1e-6, xb=[1;0;0]-([1;0;0]'*s)*s; end
            xb=xb/norm(xb); yb=cross(zb,xb);
        otherwise
            zb=-rhat; xb=vel; yb=cross(zb,xb);
    end
    Rb=[xb yb zb]; sunNad=max(0,s'*(-rhat));
    Q=zeros(M.Nn,1);
    for fi=1:6
        nin=Rb*M.normals(:,fi);
        cs=max(0,nin'*s); cn=max(0,nin'*(-rhat)); Fv=(Re/r)^2*cn;
        Q(fi)=M.alpha(fi)*e.Gs*cs*L*M.Aface(fi) + M.eps(fi)*e.qIR*Fv*M.Aface(fi) ...
            + M.alpha(fi)*e.albedo*e.Gs*Fv*sunNad*L*M.Aface(fi);
    end
    for w=1:M.npan       % pannelli dispiegabili sun-tracking (fronte al Sole)
        Q(M.nf+w)=cfg.dep.alphaF*e.Gs*L*cfg.dep.A;
    end
    Q=Q+M.Pc;
    if hasSAR && mod(ts,Torb) < cfg.sar.duty*Torb
        Q(M.iSAR)=Q(M.iSAR)+cfg.sar.Ppeak; sar_on(n)=true;
    end
    gsp=4*sig*M.epsA.*T.^3; src=sig*M.epsA.*(3*T.^4+Tsp^4);
    A=M.Lc+diag(Cdt+gsp); b=Cdt.*T+Q+src;
    T=A\b; Tsave(n,:)=T'-273.15;
end
R.t=(0:N-1)'*dt; R.T=Tsave; R.names=M.names; R.isExt=M.isExt; R.M=M;
R.sar_on=sar_on; R.lit=lit; R.Torb=Torb; R.beta=beta;
end

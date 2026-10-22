function [T, L, on] = star_thermal_step(P, T, ts)
% STAR_THERMAL_STEP  One Backward-Euler step at time ts [s from the sim start] (nadir attitude, beta in P.s).
%   Shared by star_thermal_run (mission window) and star_design_case (hot and cold cases, 2026-10-21).
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

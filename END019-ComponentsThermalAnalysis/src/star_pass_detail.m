function Rp = star_pass_detail(cfg, orb, att, R)
% STAR_PASS_DETAIL  Rifinitura ad alta fedelta' del pass con l'ASSETTO REALE.
%   Usa posizione ECI e quaternioni di output_attitude_propagation.csv per
%   calcolare l'illuminazione esatta delle facce durante il pass, invece del
%   nadir analitico. Warm-start dalla temperatura del run orbitale all'inizio
%   pass. Il SAR e' acceso per tutta la finestra (pass di imaging).
%
%   Rp: .t, .tutc, .T [Nt x Nn] degC, .names, .lit

M = star_build_model(cfg); e=cfg.env; sig=e.sigma; Tsp=e.Tspace; Re=e.Re;

% griglia fine sul pass (interpolo pos ed assetto ai passi cfg.sim.dt)
t0=att.tsec(1); t1=att.tsec(end); dt=cfg.sim.dt;
tg=(t0:dt:t1)';
eci = interp1(att.tsec, att.eci, tg, 'linear');          % [N x3] m
qq  = interp1(att.tsec, att.quat, tg, 'linear');         % [N x4]
qq  = qq ./ vecnorm(qq,2,2);                             % rinormalizza i quaternioni
sun = star_sun_eci(orb.start + seconds(mean([t0 t1])));  % ~costante nel pass

% warm-start dal run orbitale
[~,k0] = min(abs(R.t - t0)); T = R.T(k0,:)' + 273.15;

N=numel(tg); Tsave=zeros(N,M.Nn); lit=zeros(N,1); Cdt=M.C/dt;
for n=1:N
    pos=eci(n,:)'; rn=norm(pos); rhat=pos/rn;
    dotrs=rhat'*sun; perp=rn*sqrt(max(0,1-dotrs^2)); L=double(~(dotrs<0 && perp<Re)); lit(n)=L;
    Rb=quat2rotm_wxyz(qq(n,:));    % body -> ECI
    sunNad=max(0,sun'*(-rhat));
    Q=zeros(M.Nn,1);
    for fi=1:6
        nin=Rb*M.normals(:,fi);
        cs=max(0,nin'*sun); cn=max(0,nin'*(-rhat)); Fv=(Re/rn)^2*cn;
        Q(fi)=M.alpha(fi)*e.Gs*cs*L*M.Aface(fi) + M.eps(fi)*e.qIR*Fv*M.Aface(fi) ...
            + M.alpha(fi)*e.albedo*e.Gs*Fv*sunNad*L*M.Aface(fi);
    end
    for w=1:M.npan, Q(M.nf+w)=cfg.dep.alphaF*e.Gs*L*cfg.dep.A; end
    Q=Q+M.Pc;
    if ~isempty(M.iSAR), Q(M.iSAR)=Q(M.iSAR)+cfg.sar.Ppeak; end   % SAR ON nel pass

    gsp=4*sig*M.epsA.*T.^3; src=sig*M.epsA.*(3*T.^4+Tsp^4);
    A=M.Lc+diag(Cdt+gsp); b=Cdt.*T+Q+src;
    T=A\b; Tsave(n,:)=T'-273.15;
end
Rp.t=tg; Rp.tutc=orb.start+seconds(tg); Rp.T=Tsave; Rp.names=M.names; Rp.lit=lit;
end

function Rm = quat2rotm_wxyz(q)
% matrice di rotazione body->ECI da quaternione [w x y z] (senza toolbox)
w=q(1); x=q(2); y=q(3); z=q(4);
Rm=[1-2*(y^2+z^2),  2*(x*y-z*w),   2*(x*z+y*w);
    2*(x*y+z*w),    1-2*(x^2+z^2), 2*(y*z-x*w);
    2*(x*z-y*w),    2*(y*z+x*w),   1-2*(x^2+y^2)];
end

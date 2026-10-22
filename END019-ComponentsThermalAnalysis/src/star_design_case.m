function C = star_design_case(cfg, orb, cs)
% STAR_DESIGN_CASE  Hot or cold design case of a satellite (STAR phase D, 2026-10-21).
%   C = star_design_case(cfg, orb, cs) runs the orbit of orb with the beta angle fixed at
%   cs.beta_deg and the internal dissipation cs.P_internal_W (split as cfg.nodes.Pdefault),
%   nadir attitude, SAR off (its average power is in the dissipation END-004 gives), until
%   the periodic regime (orbit-to-orbit change below cfg.sim.spinup_tol, at most
%   max(cfg.sim.spinup_orbits, 200) orbits), and returns min / max temperatures of every
%   node over the last orbit.
%     hot   maximum |beta| over the mission life (shortest eclipse), maximum dissipation;
%     cold  longest eclipse over the mission life, minimum dissipation (idle).
%   C: .name .beta_deg .P_internal_W .eclipse_min .Tmin .Tmax (1 x Nn degC) .names .orbits

c2 = cfg;
c2.nodes.Pconst = cs.P_internal_W*cfg.nodes.Pdefault/sum(cfg.nodes.Pdefault);
M = star_build_model(c2);
[r, uDot] = star_orbit_phase(c2, orb);
Torb = 2*pi/uDot;
beta = cs.beta_deg; s = [cosd(beta);0;sind(beta)];
dt = c2.sim.dt;
P = struct('M',M,'e',c2.env,'r',r,'uDot',uDot,'phi0',0,'s',s,'Cdt',M.C/dt, ...
           'cfg',c2,'passes',zeros(0,2),'Torb',Torb,'hasSAR',false);
nO = round(Torb/dt);
T = (273.15+c2.T0)*ones(M.Nn,1);
Tl = zeros(nO, M.Nn); lit = zeros(nO,1);
for o = 1:max(c2.sim.spinup_orbits, 200)
    T1 = T;
    for n = 1:nO
        [T, lit(n)] = star_thermal_step(P, T, (n-1)*dt);
        Tl(n,:) = T' - 273.15;
    end
    if max(abs(T - T1)) < c2.sim.spinup_tol, break; end
end
C.name = cs.name; C.beta_deg = beta; C.P_internal_W = cs.P_internal_W;
C.eclipse_min = (1 - mean(lit))*Torb/60;
C.Tmin = min(Tl,[],1); C.Tmax = max(Tl,[],1);
C.names = M.names; C.orbits = o;
end

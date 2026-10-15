function [Pc, out] = collision_probability(cdmInfo, pathtle1, pathtle2, patheop, nut80)
%COLLISION_PROBABILITY Chan-method Pc from a CDM + per-object TLE history.
%   [Pc, out] = collision_probability(cdmInfo, pathtle1, pathtle2, patheop, nut80)
%   builds per-object 3x3 position covariances at TCA via TLE pairwise
%   differencing + analytical two-body STM propagation, forms the combined
%   covariance in ECI, projects miss and covariance into the encounter plane,
%   and integrates Chan's 1-D formula (NASA Appendix N Eq. N-2).
%
%   out struct exposes diagnostics used by the plot helpers.

R_km = cdmInfo.R1 + cdmInfo.R2;

% Time of closest approach
datetca = datetime(cdmInfo.tca, 'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS');

% Per-object state and covariance at TCA
[r1, v1, P1, diag1] = get_state_covariance_tca(pathtle1, patheop, nut80, datetca);
[r2, v2, P2, diag2] = get_state_covariance_tca(pathtle2, patheop, nut80, datetca);

% Symmetrize (guard against numerical drift)
P1 = (P1 + P1.')/2;
P2 = (P2 + P2.')/2;

r1_eci  = r1(:);  
v1_eci  = v1(:);
r2_eci  = r2(:);  
v2_eci  = v2(:);
r_rel   = r1_eci - r2_eci;
v_rel   = v1_eci - v2_eci;
miss_km = norm(r_rel);

% Combined covariance (independence assumption)
P_comb = P1 + P2;
P_comb = (P_comb + P_comb.')/2;

% Encounter-plane projection
[r_miss_2d, C_2d, R_eci2conj] = conjunction_plane_2d(r_rel, v_rel, P_comb);
C_2d = (C_2d + C_2d.')/2;

% Chan 1-D integral
Pc = chan_pc(r_miss_2d, C_2d, R_km);

out = struct();
out.tca         = cdmInfo.tca;
out.obj1        = cdmInfo.obj1;
out.obj2        = cdmInfo.obj2;
out.miss_km     = miss_km;
out.v_rel_kmps  = norm(v_rel);
out.r_miss_2d   = r_miss_2d;
out.C_2d        = C_2d;
out.R_km        = R_km;
out.R_eci2conj  = R_eci2conj;
out.r1_eci      = r1_eci;
out.v1_eci      = v1_eci;
out.r2_eci      = r2_eci;
out.v2_eci      = v2_eci;
out.P1_eci      = P1;
out.P2_eci      = P2;
out.P_comb_eci  = P_comb;
out.residuals1  = diag1.residuals_ric_all;
out.residuals2  = diag2.residuals_ric_all;
out.lags1       = diag1.lag_days_all;
out.lags2       = diag2.lag_days_all;
out.ind1        = diag1.used_ind;
out.ind2        = diag2.used_ind;
out.mean_res1   = diag1.mean_residual_ric;
out.mean_res2   = diag2.mean_residual_ric;
out.P1_ric      = diag1.P_ric_3x3;
out.P2_ric      = diag2.P_ric_3x3;
end

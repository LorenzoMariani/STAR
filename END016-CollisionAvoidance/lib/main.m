%% Compute the collision probability given a CDM

clear, clc, close all, fclose all;

addpath(genpath(pwd));

if ~isfolder('data')
    mkdir('data')
end

load nut80.dat
[iar80, rar80]  = iau80in(nut80);
nutParams.iar80 = iar80;
nutParams.rar80 = rar80;

%% Configuration
tlePath1     = fullfile("data","TLE1.txt");
tlePath2     = fullfile("data","TLE2.txt");
tlePath1mod  = fullfile("data","TLE1MOD.txt");
tlePath2mod  = fullfile("data","TLE2MOD.txt");
filenameCDM  = fullfile("data","CDM.txt");
patheop      = fullfile(pwd, 'data', 'EOP.txt');

daysInterval = 15;

loginSpaceTrack;

%geteop(patheop)

% Read CDM
[obj1, obj2, tca, R1_km, R2_km] = read_cdm(filenameCDM);

cdmInfo.tca  = tca;
cdmInfo.R1   = R1_km;
cdmInfo.R2   = R2_km;
cdmInfo.obj1 = obj1;
cdmInfo.obj2 = obj2;

endDate   = datestr(datetime(tca),   'yyyy-mm-dd');
startDate = datestr(datetime(tca)-days(daysInterval), 'yyyy-mm-dd');

% Get TLE object 1

getTle(startDate, endDate, obj1, tlePath1);
delduplicatedate(tlePath1,tlePath1mod)
fprintf("TLEs object 1 downloaded\n");

% Get TLE object 2
getTle(startDate, endDate, obj2, tlePath2);
delduplicatedate(tlePath2,tlePath2mod)
fprintf("TLEs object 2 downloaded\n");


%% Collision probability (Chan conjunction-plane method)
[Pc, out] = collision_probability(cdmInfo, tlePath1mod, tlePath2mod, patheop, nutParams);

%% Display results
fprintf('--- Collision probability ---\n')
fprintf('TCA: %s\n', out.tca)
fprintf('Primary (SAT_1): %s  |  Secondary (SAT_2): %s\n', out.obj1, out.obj2)
fprintf('Miss distance: %.4f km\n', out.miss_km)
fprintf('Relative velocity: %.4f km/s\n', out.v_rel_kmps)
fprintf('Hard-body radius (combined): %.6f km\n', out.R_km)
fprintf('Pc (Chan):   %.6e\n', Pc)

% Encounter-plane diagnostics: principal sigmas paired with miss components
% in the SAME order (larger sigma first). Bug-free pairing matters here:
% MATLAB's eig returns eigenvalues in ascending order, so the k-th miss
% component is along the k-th eigenvalue's axis, not along max/min.
[Vd, Dd]    = eig((out.C_2d + out.C_2d.')/2);
sig_axes    = sqrt(max(0, diag(Dd)));
miss_axes   = abs(Vd.' * out.r_miss_2d(:));
[sig_sorted, ord] = sort(sig_axes, 'descend');
miss_sorted = miss_axes(ord);
sig_x       = sig_sorted(1);
sig_y       = sig_sorted(2);
miss_x      = miss_sorted(1);
miss_y      = miss_sorted(2);
fprintf('Encounter-plane principal axes (larger sigma first):\n');
fprintf('  sigma_x = %.4e km   miss along that axis = %.4e km   ratio = %.2f\n', ...
    sig_x, miss_x, miss_x/max(sig_x, eps));
fprintf('  sigma_y = %.4e km   miss along that axis = %.4e km   ratio = %.2f\n', ...
    sig_y, miss_y, miss_y/max(sig_y, eps));

%% Plots
plot_residuals_ric([out.residuals1; out.lags1], out.ind1, out.obj1, 1);
plot_residuals_ric([out.residuals2; out.lags2], out.ind2, out.obj2, 3);

figure(5); clf; ax5 = axes; hold(ax5,'on'); axis(ax5,'equal'); grid(ax5,'on');
plot_covariance_ellipsoid_3d(out.r1_eci, out.P1_eci, [0 0.4 1], 3, ax5);
plot_covariance_ellipsoid_3d(out.r2_eci, out.P2_eci, [1 0.2 0.2], 3, ax5);
plot3(ax5, [out.r1_eci(1) out.r2_eci(1)], ...
           [out.r1_eci(2) out.r2_eci(2)], ...
           [out.r1_eci(3) out.r2_eci(3)], 'k--', 'LineWidth', 1.2);
title(ax5, sprintf('Per-object 3\\sigma covariance ellipsoids at TCA (ECI) — %s vs %s', ...
    out.obj1, out.obj2));
xlabel(ax5,'X_{ECI} [km]'); ylabel(ax5,'Y_{ECI} [km]'); zlabel(ax5,'Z_{ECI} [km]');
view(ax5,3);

figure(6); clf; ax6 = axes; hold(ax6,'on'); axis(ax6,'equal'); grid(ax6,'on');
plot_combined_ellipsoid_3d(out.r1_eci - out.r2_eci, out.P_comb_eci, out.R_km, ax6);
title(ax6, 'Combined error ellipsoid (3\sigma) and hard-body sphere');
view(ax6,3);

figure(7); clf;
plot_encounter_plane(out.r_miss_2d, out.C_2d, out.R_km, Pc, ...
    out.miss_km, out.v_rel_kmps);

function plot_encounter_plane(r_miss_2d, C_2d, R_km, Pc, miss_km, v_rel_kmps)
%PLOT_ENCOUNTER_PLANE 2-D conjunction-plane visualization.
%
%   plot_encounter_plane(r_miss_2d, C_2d, R_km, Pc, miss_km, v_rel_kmps)
%   draws the 1/2/3-sigma Gaussian contours of the combined uncertainty in
%   the encounter plane, the hard-body disk of radius R_km centered at the
%   origin (secondary's location in this frame), and the miss point.

ax = gca; cla(ax); hold(ax,'on'); axis(ax,'equal'); grid(ax,'on');

C_2d = (C_2d + C_2d.')/2;

% Hard-body disk at origin
theta = linspace(0, 2*pi, 200);
fill(R_km*cos(theta), R_km*sin(theta), [0.95 0.6 0.6], ...
    'FaceAlpha', 0.6, 'EdgeColor', [0.6 0.1 0.1], 'LineWidth', 1.2, ...
    'DisplayName', sprintf('Hard-body disk (R=%.4f km)', R_km));

% 1-, 2-, 3-sigma contours of C_2d centered on origin (uncertainty of r_rel)
colors = {[0 0.45 0.74], [0 0.6 0.3], [0.6 0 0.7]};
labels = {'1\sigma','2\sigma','3\sigma'};
[V, D]   = eig(C_2d);
sig_axes = sqrt(max(0, diag(D)));
tt = linspace(0, 2*pi, 200);
for k = 1:3
    ell = V * diag(sig_axes*k) * [cos(tt); sin(tt)] + r_miss_2d(:);
    plot(ax, ell(1,:), ell(2,:), '-', 'Color', colors{k}, 'LineWidth', 1.3, ...
        'DisplayName', labels{k});
end

% Miss point and miss vector from origin
plot(ax, 0, 0, 'kx', 'MarkerSize', 10, 'LineWidth', 1.5, ...
    'DisplayName', 'Secondary (origin)');
plot(ax, r_miss_2d(1), r_miss_2d(2), 'b.', 'MarkerSize', 22, ...
    'DisplayName', 'Miss point (\Deltar projected)');
plot(ax, [0 r_miss_2d(1)], [0 r_miss_2d(2)], 'b--', 'LineWidth', 1, ...
    'HandleVisibility','off');

xlabel(ax, '\xi [km]   (in-plane axis 1)');
ylabel(ax, '\zeta [km]  (in-plane axis 2)');
title(ax, sprintf(['Encounter plane — Pc (Chan) = %.3e\n', ...
    'miss = %.4f km   |v_{rel}| = %.4f km/s   R_{HB} = %.4f km'], ...
    Pc, miss_km, v_rel_kmps, R_km));
legend(ax, 'Location','bestoutside');
end

function plot_combined_ellipsoid_3d(r_rel, P_comb, R_km, ax)
%PLOT_COMBINED_ELLIPSOID_3D Combined 3-D error ellipsoid at the relative
% position, with the hard-body sphere of radius R_km drawn at the origin.
% Collision = relative position penetrates the sphere.

if nargin < 4 || isempty(ax), ax = gca; end
hold(ax,'on'); grid(ax,'on'); axis(ax,'equal');

% Combined 3-sigma ellipsoid at r_rel
P_comb = (P_comb + P_comb.')/2;
h_ell = plot_gaussian_ellipsoid(r_rel(:), P_comb, 3, 30, ax);
if isgraphics(h_ell,'surface')
    set(h_ell, 'FaceColor', [0.2 0.6 0.9], 'FaceAlpha', 0.35, 'EdgeColor', 'none');
end

% Hard-body sphere at origin
[xs, ys, zs] = sphere(40);
h_hb = surf(ax, R_km*xs, R_km*ys, R_km*zs);
set(h_hb, 'FaceColor', [0.9 0.2 0.2], 'FaceAlpha', 0.55, 'EdgeColor', 'none');

% Relative-position vector
plot3(ax, [0 r_rel(1)], [0 r_rel(2)], [0 r_rel(3)], 'k-', 'LineWidth', 1.5);
plot3(ax, 0,0,0, 'k.', 'MarkerSize', 18);
plot3(ax, r_rel(1), r_rel(2), r_rel(3), 'b.', 'MarkerSize', 18);

xlabel(ax,'X_{ECI} [km]'); ylabel(ax,'Y_{ECI} [km]'); zlabel(ax,'Z_{ECI} [km]');
legend(ax, {'3\sigma combined cov.','Hard-body sphere','Miss vector'}, ...
    'Location','best');
end

function h = plot_covariance_ellipsoid_3d(r_center, P_3x3, color, nsigma, ax)
%PLOT_COVARIANCE_ELLIPSOID_3D 3-D Gaussian covariance ellipsoid at r_center.
%
%   h = plot_covariance_ellipsoid_3d(r_center, P_3x3, color, nsigma, ax)
%
%   r_center : 3x1 center (km)
%   P_3x3    : 3x3 positive-semidefinite covariance (km^2)
%   color    : RGB triplet or color spec
%   nsigma   : scalar, ellipsoid radius in sigmas (default 3)
%   ax       : axes handle (default gca)

if nargin < 4 || isempty(nsigma), nsigma = 3; end
if nargin < 5 || isempty(ax),     ax     = gca; end

P_3x3 = (P_3x3 + P_3x3.')/2;
h = plot_gaussian_ellipsoid(r_center(:), P_3x3, nsigma, 20, ax);
if isgraphics(h, 'surface')
    set(h, 'FaceColor', color, 'FaceAlpha', 0.35, 'EdgeColor', 'none');
end
plot3(ax, r_center(1), r_center(2), r_center(3), '.', 'Color', color, ...
    'MarkerSize', 18);
end

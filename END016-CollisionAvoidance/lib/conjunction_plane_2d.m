function [r_miss_2d, C_2d, R_eci2conj] = conjunction_plane_2d(r_rel, v_rel, P_combined_3x3)
%CONJUNCTION_PLANE_2D Project relative position and combined 3x3 covariance
% into the 2-D encounter plane orthogonal to the relative velocity at TCA.
%
% Frame convention (B-plane variant):
%   z = v_rel / |v_rel|                       (out-of-plane, along motion)
%   x = (r_rel - (r_rel.z)z) / |...|          (in-plane projection of r_rel)
%   y = cross(z, x)                            (completes right-handed frame)
% The encounter plane is span{x, y}. Pc depends only on the 2x2 cov block
% in this plane and is invariant under in-plane rotation, so the specific
% choice of x-axis above (radial component of the miss) is fine even though
% the "standard" B-plane uses x along cross(v_rel, h). Numerical Pc is the
% same to within roundoff.

r_rel = r_rel(:);
v_rel = v_rel(:);

% z-axis of conjunction frame
u = v_rel / norm(v_rel);  

% in-plane component of r_rel
r_in_plane = r_rel - dot(r_rel, u) * u;

nrm = norm(r_in_plane);

% x-axis: along projection of r_rel onto plane
if nrm > 1e-12
    x_axis = r_in_plane / nrm;
else
    % Arbitrary unit vector perpendicular to u
    if abs(u(1)) < 0.9
        x_axis = cross(u, [1;0;0]);
    else
        x_axis = cross(u, [0;1;0]);
    end
    x_axis = x_axis / norm(x_axis);
end

% y-axis: completes right-handed frame (z = u, x = x_axis, y = cross(z,x))
y_axis = cross(u, x_axis);
y_axis = y_axis / norm(y_axis);

% Rotation from ECI to conjunction frame
R_eci2conj = [x_axis'; y_axis'; u'];

% Miss vector in conjunction plane (2D = first two components)
r_conj_3d  = R_eci2conj * r_rel;
r_miss_2d  = r_conj_3d(1:2);

% Covariance in conjunction frame, then 2x2 block
P_conj     = R_eci2conj * P_combined_3x3 * R_eci2conj';
C_2d       = P_conj(1:2, 1:2);

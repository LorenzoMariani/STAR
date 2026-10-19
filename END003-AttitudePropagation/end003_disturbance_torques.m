function [M, Mmax] = end003_disturbance_torques(r, v, A, Sun, rho, S)
%END003_DISTURBANCE_TORQUES  Environmental torques on the satellite and their worst case over all attitudes.
%
%   [M, Mmax] = end003_disturbance_torques(r, v, A, Sun, rho, S)
%
%   r, v   position [m] and velocity [m/s] (3 x 1) in the STAR inertial frame (ECEF = R3(GMST) x inertial)
%   A      rotation body -> inertial (3 x 3)
%   Sun    unit vector towards the Sun (3 x 1, inertial)
%   rho    atmospheric density [kg/m^3]
%   S      settings of star_attitude_propagation_star: mu, Re, I, Ivec, P_sun, A_ref, Cr, Cd, r_cp, flags.gg/srp/drag
%
%   M      torques in the body frame [N m], 3 x 6: gravity gradient, SRP, (magnetic: not modelled), drag, 0, 0;
%          a model switched off in S.flags gives a zero column
%   Mmax   worst case over all attitudes [N m], 1 x 3 (gravity gradient, SRP, drag), whatever the flags (sizing):
%            GG    3 mu / (2 r^3) (Imax - Imin)      principal axes at 45 deg from the local vertical
%            SRP   P_sun A_ref Cr |r_cp|             sunlit, force normal to r_cp
%            drag  rho |v_rel|^2 Cd A_ref |r_cp| / 2  v_rel = v - wE x r
%
%   In ideal nadir pointing with the principal axes on the orbital frame the gravity gradient is an equilibrium (zero
%   torque): what the formula gives there is the rounding of the attitude (~1e-22 N m) and is set to zero (2026-10-19).

    M = zeros(3, 6);
    Mmax = zeros(1, 3);
    rm = norm(r);
    rh = r/rm;
    rb = A'*rh;                                        % local vertical in the body frame
    gg_scale = 3*S.mu/rm^3;
    Mmax(1) = 0.5*gg_scale*(max(S.Ivec) - min(S.Ivec));
    if S.flags.gg
        M(:, 1) = gg_scale*cross(rb, S.I*rb);
        if norm(M(:, 1)) < 1e-12*Mmax(1)
            M(:, 1) = 0;
        end
    end
    lever = norm(S.r_cp);
    if dot(Sun, rh) >= -sqrt(1 - (S.Re/rm)^2)          % cylindrical Earth shadow
        F_srp = S.P_sun*S.A_ref*S.Cr;
        Mmax(2) = F_srp*lever;
        if S.flags.srp
            M(:, 2) = cross(S.r_cp, -F_srp*(A'*Sun));
        end
    end
    if rho > 0
        v_rel = v - cross([0; 0; 7.2921150e-5], r);
        q_dyn = 0.5*rho*S.Cd*S.A_ref;
        Mmax(3) = q_dyn*dot(v_rel, v_rel)*lever;
        if S.flags.drag
            vb = A'*v_rel;
            M(:, 4) = cross(S.r_cp, -q_dyn*norm(vb)*vb);
        end
    end
end

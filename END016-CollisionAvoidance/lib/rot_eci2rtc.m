function M = rot_eci2rtc(reci,veci)
%ROT_ECI2RTC Rotation matrix that maps ECI vectors into the RIC frame.
%   M * v_eci = v_ric, where the RIC rows are:
%       row 1 = R (radial,  along  r_eci)
%       row 2 = I (in-track, cross(C, R), in the orbit plane)
%       row 3 = C (cross-track, along the angular-momentum direction)
%   For a covariance: P_RIC = M * P_ECI * M.'   /   P_ECI = M.' * P_RIC * M.

r = reci/norm(reci);
c = cross(reci,veci)/(norm(cross(reci,veci)));
t = cross(c,r);

M = [r,t,c]';
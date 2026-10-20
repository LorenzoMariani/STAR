function P_sq = pc_upper_bound_square(r_miss_2d, C_2d, R)
%PC_UPPER_BOUND_SQUARE Circumscribing-square upper bound for Pc (NASA Appendix N Eq. N-3, N-4).
%   P_sq = pc_upper_bound_square(r_miss_2d, C_2d, R)
%   No numerical integration; useful for quick checks.

% Principal-axis frame: diagonalize C_2d, place miss in first quadrant
[V, D] = eig(C_2d);
sig = sqrt(diag(D));
% Order so sigma_x >= sigma_y (or arbitrary)
[~, ix] = max(sig);
iy = 3 - ix;
sigma_x = sig(ix);
sigma_y = sig(iy);
r_principal = V' * r_miss_2d(:);
x_miss = abs(r_principal(ix));
y_miss = abs(r_principal(iy));

if sigma_x <= 0 || sigma_y <= 0
    P_sq = 0;
    return
end

% Eq. (N-4): X± = (x_miss ± R)/(sqrt(2)*sigma_x), Y± = (y_miss ± R)/(sqrt(2)*sigma_y)
sqrt2 = sqrt(2);
X_plus  = (x_miss + R) / (sqrt2 * sigma_x);
X_minus = (x_miss - R) / (sqrt2 * sigma_x);
Y_plus  = (y_miss + R) / (sqrt2 * sigma_y);
Y_minus = (y_miss - R) / (sqrt2 * sigma_y);

% Eq. (N-3): P_sq = [erf(X+)-erf(X-)][erf(Y+)-erf(Y-)]/4
% 2026-10-20: erfc when both limits are positive (as chan_pc): erf(X+) - erf(X-) cancelled to 0 below Pc ~ 1e-17,
% giving an upper bound smaller than Pc
dX = erf_diff(X_minus, X_plus);
dY = erf_diff(Y_minus, Y_plus);
P_sq = (dX * dY) / 4;
P_sq = max(0, min(1, P_sq));
end

function d = erf_diff(lo, hi)
% erf(hi) - erf(lo) for lo <= hi
if lo >= 0
    d = erfc(lo) - erfc(hi);
else
    d = erf(hi) - erf(lo);
end
end

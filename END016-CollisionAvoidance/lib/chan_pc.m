function Pc = chan_pc(r_miss_2d, C_2d, R)
%CHAN_PC Collision probability via conjunction-plane 1D integral (Chan 2008 / NASA Appendix N Eq. N-2).
%   Uses principal-axis frame and erf/erfc for numerical stability.
%   Pc = chan_pc(r_miss_2d, C_2d, R)

% Principal-axis frame: C_2d = V*D*V', diagonal D
% NASA Appendix N convention: order so sigma_x >= sigma_y.
[V, D] = eig((C_2d + C_2d')/2);
sig = sqrt(max(0, diag(D)));
[~, ix] = max(sig);
iy = 3 - ix;
sigma_x = sig(ix);
sigma_y = sig(iy);
r_principal = V' * r_miss_2d(:);
% Place miss in first quadrant (x_miss >= 0, y_miss >= 0) per Appendix N
x_miss = abs(r_principal(ix));
y_miss = abs(r_principal(iy));

if R <= 0
    Pc = 0;
    return
end
if sigma_x <= 0 || sigma_y <= 0
    % Degenerate covariance: certain collision iff miss <= R.
    if norm(r_miss_2d) <= R
        Pc = 1;
    else
        Pc = 0;
    end
    return
end

% Eq. (N-2): 1D integral. Use erfc for small Pc (Elrod 2019 recommendation).
% y_plus = (y_miss + sqrt(R^2 - u^2))/(sqrt(2)*sigma_y), y_minus = (y_miss - sqrt(R^2 - u^2))/(sqrt(2)*sigma_y)
% Integrand: (erfc(y_minus) - erfc(y_plus)) * exp(-(u+x_miss)^2/(2*sigma_x^2))
sqrt2 = sqrt(2);

integrand = @(u) chan_integrand(u, y_miss, sigma_y, x_miss, sigma_x, R);

try
    Pc = (1/sqrt(8*pi*sigma_x^2)) * integral(integrand, -R, R, ...
        'AbsTol', 1e-14, 'RelTol', 1e-10);
catch ME
    warning('chan_pc:integralFailed', ...
        'integral() failed (%s); returning NaN.', ME.message);
    Pc = NaN;
    return
end

Pc = max(0, min(1, Pc));
end

function y = chan_integrand(u, y_miss, sigma_y, x_miss, sigma_x, R)
% u can be scalar or array. Eq. (N-2): integrand = (erf(y+)-erf(y-))*exp(-(u+x_miss)^2/(2*sigma_x^2))
% erf(y+)-erf(y-) = erfc(y_minus)-erfc(y_plus) for stability when Pc is small
r2 = R^2 - u.^2;
r2(r2 < 0) = 0;
sqrt_R2_u2 = sqrt(r2);
y_plus  = (y_miss + sqrt_R2_u2) / (sqrt(2) * sigma_y);
y_minus = (y_miss - sqrt_R2_u2) / (sqrt(2) * sigma_y);
d_erf = erfc(y_minus) - erfc(y_plus);  % = erf(y_plus)-erf(y_minus)
y = d_erf .* exp(-(u + x_miss).^2 / (2*sigma_x^2));
end

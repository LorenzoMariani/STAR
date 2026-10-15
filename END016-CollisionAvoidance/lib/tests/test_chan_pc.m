%% test_chan_pc - sanity checks for chan_pc against analytical limits.
%
% Limit 1 (zero miss, isotropic small R): Pc -> 1 - exp(-R^2/(2*sigma^2))
%                                            ~ R^2 / (2*sigma^2)  for R<<sigma.
% Limit 2 (large miss / many sigmas):     Pc << 1.
% Limit 3 (huge R w.r.t. cov):            Pc -> 1.

clear; clc;

%% Case 1: zero miss, isotropic 1 km sigma, 10 m hard body
sigma = 1.0;                     % km
R     = 0.010;                   % 10 m
C     = sigma^2 * eye(2);
r     = [0; 0];
Pc    = chan_pc(r, C, R);
Pc_an = 1 - exp(-R^2/(2*sigma^2));
fprintf('Case 1: Pc = %.6e, analytical = %.6e, |rel err| = %.3e\n', ...
    Pc, Pc_an, abs(Pc - Pc_an)/Pc_an);
assert(abs(Pc - Pc_an)/Pc_an < 1e-3, 'Case 1 failed');

%% Case 2: 5-sigma miss, anisotropic cov
C = diag([0.5^2, 0.1^2]);        % km^2
r = [2.5; 0];                    % 5 sigma along x
R = 0.01;
Pc = chan_pc(r, C, R);
fprintf('Case 2: Pc = %.6e (should be << 1e-4)\n', Pc);
assert(Pc < 1e-4, 'Case 2 failed');

%% Case 3: hard-body sphere larger than 3-sigma -> certain collision
C = 0.001^2 * eye(2);            % km^2 (sigma = 1 m)
r = [0; 0];
R = 0.1;                          % 100 m
Pc = chan_pc(r, C, R);
fprintf('Case 3: Pc = %.6e (should be ~ 1)\n', Pc);
assert(Pc > 0.99, 'Case 3 failed');

%% Case 4: Rotation invariance of Pc
C0 = diag([0.4^2, 0.1^2]);
r0 = [0.3; 0.05];
R  = 0.005;
theta = pi/7;
Q = [cos(theta) -sin(theta); sin(theta) cos(theta)];
Pc_a = chan_pc(r0, C0, R);
Pc_b = chan_pc(Q*r0, Q*C0*Q', R);
fprintf('Case 4 invariance: |Pc_a - Pc_b| / Pc_a = %.3e\n', abs(Pc_a-Pc_b)/Pc_a);
assert(abs(Pc_a-Pc_b)/Pc_a < 1e-6, 'Case 4 failed');

fprintf('\nAll chan_pc sanity checks passed.\n');

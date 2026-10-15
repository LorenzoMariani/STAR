function plot_residuals_ric(residuals, ind, obj_id, fig_id)
%PLOT_RESIDUALS_RIC Plot R, I, C position residuals from TLE pairwise
% differencing as a function of propagation lag.
%
% residuals : 7 x K matrix; rows 1-3 = radial/in-track/cross-track residual
%             [km], row 7 = lag [days]. (Rows 4-6 are velocity residuals
%             and ignored here.) Accepts 6 x K too (no lag axis).
% obj_id    : char/string for title
% fig_id    : figure handle / number

if size(residuals,1) >= 7
    dt = residuals(7,:);
else
    dt = 1:size(residuals,2);
end
r  = residuals(1,:);
it = residuals(2,:);
ct = residuals(3,:);

u = max(max(abs(residuals(1:3,:))));

% 1-sigma per-component (data-driven)
sig_r  = std(r,  0, 2);
sig_it = std(it, 0, 2);
sig_ct = std(ct, 0, 2);

figure(fig_id); clf;
tl = tiledlayout(3, 1, 'TileSpacing','compact','Padding','compact');
title(tl, sprintf('Pairwise residuals (RIC) — object %s', char(obj_id)));

nexttile; hold on; grid on; grid minor;
plot(dt, r, 'r+');
plot(dt(ind), r(ind), 'g*');
yline( sig_r, 'k--'); yline(-sig_r, 'k--');
legend("All residuals", "Used residuals", "1\sigma")
ylabel('Radial [km]');
ylim([-u u])

nexttile; hold on; grid on; grid minor;
plot(dt, it, 'b+');
plot(dt(ind), it(ind), 'g*');
yline( sig_it, 'k--'); yline(-sig_it, 'k--');
legend("All residuals", "Used residuals", "1\sigma")
ylabel('In-track [km]');
ylim([-u u])

nexttile; hold on; grid on; grid minor;
plot(dt, ct, 'k+');
plot(dt(ind), it(ind), 'g*');
yline( sig_ct, 'k--'); yline(-sig_ct, 'k--');
ylabel('Cross-track [km]');
legend("All residuals", "Used residuals", "1\sigma")
ylim([-u u])
xlabel('Propagation lag \Delta t [days]');
end

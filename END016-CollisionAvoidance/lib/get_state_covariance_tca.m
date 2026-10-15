function [r_eci, v_eci, P_eci_3x3, diag] = get_state_covariance_tca(pathtle, patheop, nut80, datetca)
%GET_STATE_COVARIANCE_TCA Propagate latest TLE to TCA and build 3x3 position
% covariance in ECI from TLE pairwise residuals.
%
% Conceptual model:
%   TLE pairwise differencing produces residuals r_ric(deltaT) where deltaT
%   is the propagation lag between two TLE epochs. The sample variance of
%   these residuals at lag = (TCA - t_lastTLE) is, by construction, the
%   covariance of the position error one incurs when propagating a TLE
%   over that same interval. We therefore:
%     1. bin residuals at lag ~ interval
%     2. estimate the 3x3 RIC position covariance from that bin
%     3. rotate it to ECI using the RIC frame defined at TCA
%        (because we want the covariance attached to the propagated state
%         at TCA, not at the last TLE epoch)
%   No additional dynamics propagation is applied: that would double-count
%   the propagation lag already encoded in the binning.
%
% Outputs:
%   r_eci, v_eci  - ECI state at TCA (km, km/s)
%   P_eci_3x3     - 3x3 position covariance at TCA (km^2)
%   diag          - struct with diagnostics:
%                   .residuals_ric_all (6 x N : full residual set, RIC)
%                   .lag_days_all      (1 x N : per-residual lag in days)
%                   .used_ind          (indices selected by the binning)
%                   .mean_residual_ric (6x1 : mean of the *used* residuals)
%                   .P_ric_6x6         (6x6 sample covariance in RIC, used bin)
%                   .P_ric_3x3         (3x3 position block in RIC)

WINDOW_DAYS_INIT = 0.5;
WINDOW_DAYS_MAX  = 5.0;
WINDOW_STEP      = 0.5;
NMIN             = 6;

% Pairwise residuals
infosat   = tle_pairwise(pathtle, patheop, nut80);
epochobj  = infosat{1,end}.jdsatepoch + infosat{1,end}.jdsatepochf;
epochtca  = juliandate(datetca);
interval  = epochtca - epochobj;            % days from latest TLE to TCA

% Collect all residuals (rows 1-6 = RIC pos/vel, row 7 = lag in days)
residuals = [];
for i = 2:size(infosat, 2)
    if ~isempty(infosat{5,i})
        residuals = [residuals, infosat{5,i}];   %#ok<AGROW>
    end
end
if isempty(residuals)
    error('get_state_covariance_tca:noResiduals', ...
        'No pairwise residuals available from TLE history.');
end

% Adaptive binning around the desired lag
lags   = residuals(7,:);
window = WINDOW_DAYS_INIT;
ind    = find(abs(lags - interval) <= window);
while numel(ind) < NMIN && window < WINDOW_DAYS_MAX
    window = window + WINDOW_STEP;
    ind    = find(abs(lags - interval) <= window);
end
if numel(ind) < NMIN
    [~, idx] = sort(abs(lags - interval));
    ind = idx(1:min(20, numel(idx)));
    warning('get_state_covariance_tca:fallback', ...
        ['Insufficient residuals within %.1f days of TCA-lag=%.3f days; ', ...
         'falling back to %d nearest residuals (lag range %.3f..%.3f days).'], ...
         WINDOW_DAYS_MAX, interval, numel(ind), min(lags(ind)), max(lags(ind)));
end

res     = residuals(1:6, ind);
res_all = residuals(1:6, :);
lag_all = lags;

% Unbiased sample covariance (6x6 in RIC)
N = size(res, 2);
if N >= 2
    P_ric_6x6 = cov(res.');             % MATLAB cov: divides by (N-1)
else
    P_ric_6x6 = res * res.';            % degenerate fallback
end
P_ric_6x6 = (P_ric_6x6 + P_ric_6x6.')/2;
P_ric_3x3 = P_ric_6x6(1:3, 1:3);
mean_res  = mean(res, 2);

% Propagate latest TLE to TCA via SGP4 to obtain the ECI state at TCA
[~, rteme, vteme] = sgp4(infosat{1,end}, interval * 1440);
dateeop           = datetime(epochtca, 'convertfrom', 'juliandate', 'Format', 'yyyy-MM-dd');
t                 = datevec(datetime(epochtca, 'convertfrom', 'juliandate'));
eop               = EOP_struct(patheop, string(dateeop));
[jdut1, jdut1frac, ttt]       = convtime(t(1), t(2), t(3), t(4), t(5), t(6), 0, eop.dut1, eop.dat);
[r_eci, v_eci, ~] = teme2eci(rteme', vteme', 0, ttt, eop.ddpsi, eop.ddeps, nut80);
%[~,az_,el_,~,~,~,rs,vs] = rv2razel(r_eci, v_eci, pi/180*41.7653, pi/180*13.3750, 0.555, ttt, jdut1+jdut1frac, eop.lod, eop.xp, eop.yp, 2, eop.ddpsi, eop.ddeps, nut80);
r_eci = r_eci(:);
v_eci = v_eci(:);

% RIC -> ECI rotation at TCA
M_tca     = rot_eci2rtc(r_eci, v_eci);     % ECI -> RIC at TCA
P_eci_3x3 = M_tca.' * P_ric_3x3 * M_tca;   % rotate position cov RIC -> ECI
P_eci_3x3 = (P_eci_3x3 + P_eci_3x3.')/2;

% Diagnostics
diag.residuals_ric_all = res_all;
diag.lag_days_all      = lag_all;
diag.used_ind          = ind;
diag.mean_residual_ric = mean_res;
diag.P_ric_6x6         = P_ric_6x6;
diag.P_ric_3x3         = P_ric_3x3;
end

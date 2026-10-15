function out = mc_state_chan(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR, N, opts)
%MC_STATE_CHAN Monte Carlo simulation by perturbing positions and velocities.
%
% This function samples object states from the 6x6 ECI covariance matrices:
%
%   x1_sample = [reci1; veci1] + dx1
%   x2_sample = [reci2; veci2] + dx2
%
% Then it computes:
%   1. Direct Monte Carlo hit probability:
%        PcMC = number of b-plane miss distances <= HBR divided by N
%
%   2. A distribution of Chan Pc values evaluated at the perturbed states,
%      using the nominal covariance matrices.
%
% Inputs:
%   reci1, veci1    Object 1 ECI position [m] and velocity [m/s], 3x1
%   Ceci1           Object 1 ECI covariance, 6x6
%   reci2, veci2    Object 2 ECI position [m] and velocity [m/s], 3x1
%   Ceci2           Object 2 ECI covariance, 6x6
%   HBR             Hard-body radius [m]
%   N               Number of Monte Carlo samples
%   opts            Optional struct:
%                   opts.StateSigmaScale  multiplier on sampled state error, default 1
%                   opts.MakePlots        true/false, default true
%                   opts.Seed             random seed, default []
%
% Output:
%   out.PcMC                 direct Monte Carlo hit-count probability
%   out.PcChanNominal        nominal Chan Pc
%   out.PcChanAtSamples      N x 1 Chan Pc at perturbed states
%   out.Hit                  N x 1 logical collision flags
%   out.rMiss2D              N x 2 sampled b-plane miss vectors [m]
%   out.bPlaneMissDistance   N x 1 sampled b-plane miss distances [m]
%   out.MissDistance3D       N x 1 sampled 3D relative distances [m]
%   out.RelativeSpeed        N x 1 sampled relative speeds [m/s]

    if nargin < 8 || isempty(N)
        N = 5000;
    end

    if nargin < 9 || isempty(opts)
        opts = struct();
    end

    opts = localDefaultOptsState(opts);

    if ~isempty(opts.Seed)
        rng(opts.Seed);
    end

    reci1 = reci1(:);
    veci1 = veci1(:);
    reci2 = reci2(:);
    veci2 = veci2(:);

    x1 = [reci1; veci1];
    x2 = [reci2; veci2];

    Ceci1 = localSymmetrize(Ceci1);
    Ceci2 = localSymmetrize(Ceci2);

    L1 = localCovSqrt(Ceci1, opts.EigenFloorRel);
    L2 = localCovSqrt(Ceci2, opts.EigenFloorRel);

    [PcChanNominal, rMiss2DNominal, C2DNominal] = localChanPc(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR);

    PcChanAtSamples    = zeros(N, 1);
    Hit                = false(N, 1);
    rMiss2D            = zeros(N, 2);
    bPlaneMissDistance = zeros(N, 1);
    MissDistance3D     = zeros(N, 1);
    RelativeSpeed      = zeros(N, 1);

    for k = 1:N

        dx1 = opts.StateSigmaScale * L1 * randn(6, 1);
        dx2 = opts.StateSigmaScale * L2 * randn(6, 1);

        x1k = x1 + dx1;
        x2k = x2 + dx2;

        reci1k = x1k(1:3);
        veci1k = x1k(4:6);

        reci2k = x2k(1:3);
        veci2k = x2k(4:6);

        [PcChanAtSamples(k), r2dk] = localChanPc(reci1k, veci1k, Ceci1, reci2k, veci2k, Ceci2, HBR);

        rMiss2D(k, :) = r2dk(:).';

        bPlaneMissDistance(k) = norm(r2dk);
        MissDistance3D(k)     = norm(reci2k - reci1k);
        RelativeSpeed(k)      = norm(veci2k - veci1k);

        Hit(k) = bPlaneMissDistance(k) <= HBR;

    end

    out = struct();
    out.PcMC                 = mean(Hit);
    out.PcMCStd              = sqrt(out.PcMC * (1 - out.PcMC) / N);
    out.PcChanNominal        = PcChanNominal;
    out.PcChanAtSamples      = PcChanAtSamples;
    out.rMiss2DNominal       = rMiss2DNominal;
    out.C2DNominal           = C2DNominal;
    out.Hit                  = Hit;
    out.rMiss2D              = rMiss2D;
    out.bPlaneMissDistance   = bPlaneMissDistance;
    out.MissDistance3D       = MissDistance3D;
    out.RelativeSpeed        = RelativeSpeed;
    out.HBR                  = HBR;
    out.Options              = opts;
    out.StatsChanAtSamples   = localStats(PcChanAtSamples);
    out.StatsMissDistance2D  = localStats(bPlaneMissDistance);
    out.StatsMissDistance3D  = localStats(MissDistance3D);

    fprintf("\nState MC results\n");
    fprintf("Nominal Chan Pc             : %.6e\n", out.PcChanNominal);
    fprintf("Direct MC Pc estimate        : %.6e +/- %.6e 1-sigma\n", out.PcMC, out.PcMCStd);
    fprintf("Mean Chan Pc at samples      : %.6e\n", out.StatsChanAtSamples.Mean);
    fprintf("Median Chan Pc at samples    : %.6e\n", out.StatsChanAtSamples.Median);
    fprintf("5%% - 95%% Chan Pc at samples : %.6e  %.6e\n", ...
        out.StatsChanAtSamples.P05, out.StatsChanAtSamples.P95);

    if out.PcMC == 0
        fprintf("No direct hits found. For very small Pc, increase N significantly.\n");
    end

    if opts.MakePlots
        localPlotStateMC(out);
    end

end

function opts = localDefaultOptsState(opts)

    if ~isfield(opts, "StateSigmaScale")
        opts.StateSigmaScale = 1.0;
    end

    if ~isfield(opts, "MakePlots")
        opts.MakePlots = true;
    end

    if ~isfield(opts, "Seed")
        opts.Seed = [];
    end

    if ~isfield(opts, "EigenFloorRel")
        opts.EigenFloorRel = 1e-14;
    end

end

function [Pc, rMiss2D, C2D, R_eci2conj] = localChanPc(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR)

    Ccomb = Ceci1(1:3,1:3) + Ceci2(1:3,1:3);
    Ccomb = localSymmetrize(Ccomb);

    rRel = reci2 - reci1;
    vRel = veci2 - veci1;

    [rMiss2D, C2D, R_eci2conj] = conjunction_plane_2d(rRel, vRel, Ccomb);

    C2D = localSymmetrize(C2D);

    Pc = chan_pc(rMiss2D, C2D, HBR);

end

function L = localCovSqrt(C, eigenFloorRel)

    C = localMakeSPD(C, eigenFloorRel);

    [L, p] = chol(C, "lower");

    if p ~= 0
        [V, D] = eig(C);
        lambda = max(real(diag(D)), 0);
        L = V * diag(sqrt(lambda));
    end

end

function C = localSymmetrize(C)
    C = 0.5 * (C + C.');
end

function C = localMakeSPD(C, eigenFloorRel)

    C = localSymmetrize(C);

    [V, D] = eig(C);
    lambda = real(diag(D));

    scale = max(1, max(abs(lambda)));
    lambdaFloor = eigenFloorRel * scale;

    lambda(lambda < lambdaFloor) = lambdaFloor;

    C = V * diag(lambda) * V.';
    C = localSymmetrize(C);

end

function s = localStats(x)

    x = x(:);

    p = localPercentile(x, [5, 50, 95]);

    s = struct();
    s.Mean   = mean(x);
    s.Median = p(2);
    s.Std    = std(x);
    s.Min    = min(x);
    s.Max    = max(x);
    s.P05    = p(1);
    s.P95    = p(3);

end

function p = localPercentile(x, perc)

    x = sort(x(:));
    n = numel(x);

    p = zeros(size(perc));

    for i = 1:numel(perc)

        q = perc(i) / 100;
        idx = 1 + q * (n - 1);

        idxLow  = floor(idx);
        idxHigh = ceil(idx);

        if idxLow == idxHigh
            p(i) = x(idxLow);
        else
            w = idx - idxLow;
            p(i) = (1 - w) * x(idxLow) + w * x(idxHigh);
        end

    end

end

function [xs, F] = localEmpiricalCDF(x)

    xs = sort(x(:));
    n = numel(xs);
    F = (1:n).' / n;

end

function localPlotStateMC(out)

    PcPlot = max(out.PcChanAtSamples, realmin);

    figure("Name", "Monte Carlo - State Perturbation");

    subplot(2,2,1)
    histogram(log10(PcPlot), 50);
    grid on
    xlabel("log_{10}(Chan Pc)");
    ylabel("Count");
    title("Chan Pc at perturbed states");

    subplot(2,2,2)
    histogram(out.bPlaneMissDistance, 50);
    hold on
    xline(out.HBR, "--", "HBR");
    grid on
    xlabel("B-plane miss distance [m]");
    ylabel("Count");
    title("Sampled B-plane miss distance");

    subplot(2,2,3)
    scatter(out.rMiss2D(:,1), out.rMiss2D(:,2), 8, "filled");
    hold on
    localPlotCircle(out.HBR);
    localPlotEllipse(out.rMiss2DNominal(:), out.C2DNominal, [1, 2, 3]);
    plot(out.rMiss2DNominal(1), out.rMiss2DNominal(2), "kx", "LineWidth", 2, "MarkerSize", 10);
    axis equal
    grid on
    xlabel("B-plane axis 1 [m]");
    ylabel("B-plane axis 2 [m]");
    title(sprintf("B-plane samples, PcMC = %.3e", out.PcMC));

    subplot(2,2,4)
    scatter(out.bPlaneMissDistance, PcPlot, 12, "filled");
    hold on
    xline(out.HBR, "--", "HBR");
    yline(out.PcChanNominal, "--", "Nominal Chan Pc");
    grid on
    set(gca, "YScale", "log");
    xlabel("B-plane miss distance [m]");
    ylabel("Chan Pc");
    title("Pc sensitivity to miss distance");

end

function localPlotCircle(radius)

    th = linspace(0, 2*pi, 300);
    x = radius * cos(th);
    y = radius * sin(th);

    plot(x, y, "LineWidth", 1.5);

end

function localPlotEllipse(mu, C, sigmas)

    C = localSymmetrize(C);

    [V, D] = eig(C);
    lambda = max(real(diag(D)), 0);

    th = linspace(0, 2*pi, 300);
    unitCircle = [cos(th); sin(th)];

    for i = 1:numel(sigmas)

        s = sigmas(i);
        ellipse = mu + s * V * diag(sqrt(lambda)) * unitCircle;

        plot(ellipse(1,:), ellipse(2,:), "LineWidth", 1.2);

    end

end
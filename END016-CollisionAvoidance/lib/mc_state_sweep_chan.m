function out = mc_state_sweep_chan(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR, NperLevel, sigmaScaleVec, opts)
%MC_STATE_SWEEP_CHAN Sweep state perturbation magnitude.
%
% Perturbs position and velocity using the 6x6 covariance matrices:
%
%   x = [r; v]
%   dx = sigmaScale * L * randn(6,1)
%   x_pert = x + dx
%
% where:
%
%   C = L * L'
%
% Therefore:
%
%   sigmaScale = 0.1   small 0.1-sigma perturbations
%   sigmaScale = 1.0   nominal covariance perturbations
%   sigmaScale = 2.0   two-sigma-scale perturbations
%
% The function evaluates Chan Pc at each perturbed state while keeping the
% covariance matrices fixed.
%
% Inputs:
%   reci1, veci1     Object 1 ECI state [m], [m/s]
%   Ceci1            Object 1 6x6 ECI covariance
%   reci2, veci2     Object 2 ECI state [m], [m/s]
%   Ceci2            Object 2 6x6 ECI covariance
%   HBR              Hard-body radius [m]
%   NperLevel        Samples per perturbation magnitude
%   sigmaScaleVec    Vector of state sigma scales
%
% Output:
%   out.Pc
%   out.PcNominal
%   out.PercentDeviation
%   out.BPlaneMissDistance
%   out.Hit
%   out.Stats

    if nargin < 8 || isempty(NperLevel)
        NperLevel = 1000;
    end

    if nargin < 9 || isempty(sigmaScaleVec)
        sigmaScaleVec = [0 0.1 0.25 0.50 1.00 1.50 2.00];
    end

    if nargin < 10 || isempty(opts)
        opts = struct();
    end

    opts = localDefaultStateSweepOpts(opts);

    if ~isempty(opts.Seed)
        rng(opts.Seed);
    end

    reci1 = reci1(:);
    veci1 = veci1(:);
    reci2 = reci2(:);
    veci2 = veci2(:);

    x1 = [reci1; veci1];
    x2 = [reci2; veci2];

    Ceci1 = localSym(Ceci1);
    Ceci2 = localSym(Ceci2);

    L1 = localCovSqrt(Ceci1);
    L2 = localCovSqrt(Ceci2);

    PcNominal = localChanPc(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR);

    nLevels = numel(sigmaScaleVec);

    Pc                    = zeros(NperLevel, nLevels);
    relativeDeviation     = zeros(NperLevel, nLevels);
    percentDeviation      = zeros(NperLevel, nLevels);
    log10Ratio            = zeros(NperLevel, nLevels);
    bPlaneMissDistance    = zeros(NperLevel, nLevels);
    missDistance3D        = zeros(NperLevel, nLevels);
    relativeSpeed         = zeros(NperLevel, nLevels);
    hit                   = false(NperLevel, nLevels);
    actualStateSigmaRMS   = zeros(NperLevel, nLevels);

    for j = 1:nLevels

        sigmaScale = sigmaScaleVec(j);

        for k = 1:NperLevel

            z1 = randn(6,1);
            z2 = randn(6,1);

            dx1 = sigmaScale * L1 * z1;
            dx2 = sigmaScale * L2 * z2;

            x1k = x1 + dx1;
            x2k = x2 + dx2;

            reci1k = x1k(1:3);
            veci1k = x1k(4:6);

            reci2k = x2k(1:3);
            veci2k = x2k(4:6);

            [Pc(k,j), rMiss2D] = localChanPcWithMiss(reci1k, veci1k, Ceci1, reci2k, veci2k, Ceci2, HBR);

            relativeDeviation(k,j) = (Pc(k,j) - PcNominal) / PcNominal;
            percentDeviation(k,j)  = 100 * relativeDeviation(k,j);
            log10Ratio(k,j)        = log10(max(Pc(k,j), realmin) / max(PcNominal, realmin));

            bPlaneMissDistance(k,j) = norm(rMiss2D);
            missDistance3D(k,j)     = norm(reci2k - reci1k);
            relativeSpeed(k,j)      = norm(veci2k - veci1k);
            hit(k,j)                = bPlaneMissDistance(k,j) <= HBR;

            actualStateSigmaRMS(k,j) = sigmaScale * sqrt(mean([z1; z2].^2));

        end

    end

    stats = localSweepStats(Pc, relativeDeviation, percentDeviation, log10Ratio, bPlaneMissDistance, hit);

    out = struct();
    out.Pc = Pc;
    out.PcNominal = PcNominal;
    out.SigmaScaleVec = sigmaScaleVec(:);
    out.RelativeDeviation = relativeDeviation;
    out.PercentDeviation = percentDeviation;
    out.Log10Ratio = log10Ratio;
    out.BPlaneMissDistance = bPlaneMissDistance;
    out.MissDistance3D = missDistance3D;
    out.RelativeSpeed = relativeSpeed;
    out.Hit = hit;
    out.PcDirectMC = mean(hit, 1);
    out.ActualStateSigmaRMS = actualStateSigmaRMS;
    out.HBR = HBR;
    out.Stats = stats;
    out.Options = opts;

    fprintf("\nState perturbation sweep\n");
    fprintf("Nominal Pc: %.6e\n", PcNominal);
    fprintf("\n");
    fprintf("sigmaScale      min dev [%%]      median dev [%%]      max dev [%%]      direct MC Pc\n");

    for j = 1:nLevels
        fprintf("%10.3f      %+12.3f      %+15.3f      %+12.3f      %.6e\n", ...
            sigmaScaleVec(j), stats.Percent.Min(j), stats.Percent.Median(j), stats.Percent.Max(j), out.PcDirectMC(j));
    end

    if opts.MakePlots
        localPlotStateSweep(out);
    end

end

function opts = localDefaultStateSweepOpts(opts)

    if ~isfield(opts, "MakePlots")
        opts.MakePlots = true;
    end

    if ~isfield(opts, "Seed")
        opts.Seed = [];
    end

end

function Pc = localChanPc(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR)

    [Pc, ~] = localChanPcWithMiss(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR);

end

function [Pc, rMiss2D, C2D] = localChanPcWithMiss(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR)

    Ccomb = localSym(Ceci1(1:3,1:3) + Ceci2(1:3,1:3));

    rRel = reci2 - reci1;
    vRel = veci2 - veci1;

    [rMiss2D, C2D] = conjunction_plane_2d(rRel, vRel, Ccomb);

    Pc = chan_pc(rMiss2D, localSym(C2D), HBR);

end

function L = localCovSqrt(C)

    C = localMakeSPD(C);

    [L,p] = chol(C, "lower");

    if p ~= 0
        [V,D] = eig(C);
        lambda = max(real(diag(D)), 0);
        L = V * diag(sqrt(lambda));
    end

end

function stats = localSweepStats(Pc, relDev, pctDev, log10Ratio, miss2D, hit)

    stats = struct();

    stats.Pc.Min    = min(Pc, [], 1);
    stats.Pc.P05    = localPercentileCols(Pc, 5);
    stats.Pc.Median = localPercentileCols(Pc, 50);
    stats.Pc.P95    = localPercentileCols(Pc, 95);
    stats.Pc.Max    = max(Pc, [], 1);

    stats.Relative.Min    = min(relDev, [], 1);
    stats.Relative.P05    = localPercentileCols(relDev, 5);
    stats.Relative.Median = localPercentileCols(relDev, 50);
    stats.Relative.P95    = localPercentileCols(relDev, 95);
    stats.Relative.Max    = max(relDev, [], 1);

    stats.Percent.Min    = min(pctDev, [], 1);
    stats.Percent.P05    = localPercentileCols(pctDev, 5);
    stats.Percent.Median = localPercentileCols(pctDev, 50);
    stats.Percent.P95    = localPercentileCols(pctDev, 95);
    stats.Percent.Max    = max(pctDev, [], 1);

    stats.Log10Ratio.Min    = min(log10Ratio, [], 1);
    stats.Log10Ratio.P05    = localPercentileCols(log10Ratio, 5);
    stats.Log10Ratio.Median = localPercentileCols(log10Ratio, 50);
    stats.Log10Ratio.P95    = localPercentileCols(log10Ratio, 95);
    stats.Log10Ratio.Max    = max(log10Ratio, [], 1);

    stats.Miss2D.Min    = min(miss2D, [], 1);
    stats.Miss2D.P05    = localPercentileCols(miss2D, 5);
    stats.Miss2D.Median = localPercentileCols(miss2D, 50);
    stats.Miss2D.P95    = localPercentileCols(miss2D, 95);
    stats.Miss2D.Max    = max(miss2D, [], 1);

    stats.DirectMCPc = mean(hit, 1);

end

function p = localPercentileCols(X, q)

    X = sort(X, 1);
    n = size(X, 1);

    idx = 1 + (q/100) * (n - 1);
    lo = floor(idx);
    hi = ceil(idx);

    if lo == hi
        p = X(lo,:);
    else
        w = idx - lo;
        p = (1 - w) * X(lo,:) + w * X(hi,:);
    end

end

function C = localSym(C)

    C = 0.5 * (C + C.');

end

function C = localMakeSPD(C)

    C = localSym(C);

    [V,D] = eig(C);
    lambda = real(diag(D));

    floorVal = max(1, max(abs(lambda))) * 1e-14;
    lambda(lambda < floorVal) = floorVal;

    C = V * diag(lambda) * V.';
    C = localSym(C);

end

function localPlotStateSweep(out)

    x = out.SigmaScaleVec(:).';

    figure("Name", "State perturbation sweep");

    tiledlayout(2,2);

    nexttile
    hold on
    fill([x fliplr(x)], [out.Stats.Percent.P05 fliplr(out.Stats.Percent.P95)], [0.85 0.85 0.85], "EdgeColor", "none");
    plot(x, out.Stats.Percent.Min, "--", "LineWidth", 1.0);
    plot(x, out.Stats.Percent.Median, "LineWidth", 2.0);
    plot(x, out.Stats.Percent.Max, "--", "LineWidth", 1.0);
    yline(0, "k:");
    grid on
    xlabel("State perturbation scale [sigma]");
    ylabel("Pc deviation from nominal [%]");
    title("Min / median / max Pc deviation");
    legend("5-95% band", "min", "median", "max", "Location", "best");

    nexttile
    semilogy(x, out.Stats.Pc.Min, "--", "LineWidth", 1.0);
    hold on
    semilogy(x, out.Stats.Pc.P05, ":", "LineWidth", 1.0);
    semilogy(x, out.Stats.Pc.Median, "LineWidth", 2.0);
    semilogy(x, out.Stats.Pc.P95, ":", "LineWidth", 1.0);
    semilogy(x, out.Stats.Pc.Max, "--", "LineWidth", 1.0);
    yline(out.PcNominal, "k:", "Nominal");
    grid on
    xlabel("State perturbation scale [sigma]");
    ylabel("Pc");
    title("Pc range vs state perturbation");
    legend("min", "5%", "median", "95%", "max", "nominal", "Location", "best");

    nexttile
    X = repmat(x, size(out.PercentDeviation,1), 1);
    scatter(X(:), out.PercentDeviation(:), 8, "filled", "MarkerFaceAlpha", 0.25);
    yline(0, "k:");
    grid on
    xlabel("State perturbation scale [sigma]");
    ylabel("Pc deviation from nominal [%]");
    title("All samples");

    nexttile
    scatter(out.BPlaneMissDistance(:), out.Log10Ratio(:), 8, "filled", "MarkerFaceAlpha", 0.25);
    xline(out.HBR, "k:", "HBR");
    yline(0, "k:");
    grid on
    xlabel("B-plane miss distance [m]");
    ylabel("log_{10}(Pc / Pc_{nominal})");
    title("Pc deviation vs sampled miss distance");

end
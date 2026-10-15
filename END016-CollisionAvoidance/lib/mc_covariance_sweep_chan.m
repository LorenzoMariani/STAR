function out = mc_covariance_sweep_chan(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR, NperLevel, sigmaLogVec, opts)
%MC_COVARIANCE_SWEEP_CHAN Sweep covariance perturbation magnitude.
%
% Perturbs the covariance matrices and evaluates the deviation of Chan Pc
% with respect to the nominal probability.
%
% Covariance perturbation model:
%
%   scalar mode:
%       C_pert = alpha * C
%       alpha = exp(sigmaLog * randn)
%
%   eigen mode:
%       C = V * diag(lambda) * V'
%       lambda_pert = lambda .* exp(sigmaLog * randn(6,1))
%       C_pert = V * diag(lambda_pert) * V'
%
% Inputs:
%   reci1, veci1     Object 1 ECI state [m], [m/s]
%   Ceci1            Object 1 6x6 ECI covariance
%   reci2, veci2     Object 2 ECI state [m], [m/s]
%   Ceci2            Object 2 6x6 ECI covariance
%   HBR              Hard-body radius [m]
%   NperLevel        Samples per perturbation magnitude
%   sigmaLogVec      Vector of lognormal perturbation magnitudes
%   opts.Mode        "eigen" or "scalar", default "eigen"
%   opts.MakePlots   true/false, default true
%   opts.Seed        random seed, default []
%
% Output:
%   out.Pc
%   out.PcNominal
%   out.RelativeDeviation
%   out.PercentDeviation
%   out.Log10Ratio
%   out.Stats

    if nargin < 8 || isempty(NperLevel)
        NperLevel = 1000;
    end

    if nargin < 9 || isempty(sigmaLogVec)
        sigmaLogVec = [0 0.025 0.05 0.10 0.20 0.30 0.50];
    end

    if nargin < 10 || isempty(opts)
        opts = struct();
    end

    opts = localDefaultCovSweepOpts(opts);

    if ~isempty(opts.Seed)
        rng(opts.Seed);
    end

    reci1 = reci1(:);
    veci1 = veci1(:);
    reci2 = reci2(:);
    veci2 = veci2(:);

    Ceci1 = localSym(Ceci1);
    Ceci2 = localSym(Ceci2);

    PcNominal = localChanPc(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR);

    nLevels = numel(sigmaLogVec);

    Pc                    = zeros(NperLevel, nLevels);
    relativeDeviation     = zeros(NperLevel, nLevels);
    percentDeviation      = zeros(NperLevel, nLevels);
    log10Ratio            = zeros(NperLevel, nLevels);
    actualPerturbationRMS = zeros(NperLevel, nLevels);

    for j = 1:nLevels

        sigmaLog = sigmaLogVec(j);

        for k = 1:NperLevel

            [Ceci1k, s1] = localPerturbCovariance(Ceci1, sigmaLog, opts.Mode);
            [Ceci2k, s2] = localPerturbCovariance(Ceci2, sigmaLog, opts.Mode);

            Pc(k,j) = localChanPc(reci1, veci1, Ceci1k, reci2, veci2, Ceci2k, HBR);

            relativeDeviation(k,j) = (Pc(k,j) - PcNominal) / PcNominal;
            percentDeviation(k,j)  = 100 * relativeDeviation(k,j);
            log10Ratio(k,j)        = log10(max(Pc(k,j), realmin) / max(PcNominal, realmin));

            actualPerturbationRMS(k,j) = sqrt(mean(log([s1(:); s2(:)]).^2));

        end

    end

    stats = localSweepStats(Pc, relativeDeviation, percentDeviation, log10Ratio);

    out = struct();
    out.Pc = Pc;
    out.PcNominal = PcNominal;
    out.SigmaLogVec = sigmaLogVec(:);
    out.RelativeDeviation = relativeDeviation;
    out.PercentDeviation = percentDeviation;
    out.Log10Ratio = log10Ratio;
    out.ActualPerturbationRMS = actualPerturbationRMS;
    out.Stats = stats;
    out.Options = opts;

    fprintf("\nCovariance perturbation sweep\n");
    fprintf("Nominal Pc: %.6e\n", PcNominal);
    fprintf("\n");
    fprintf("sigmaLog      min dev [%%]      median dev [%%]      max dev [%%]\n");

    for j = 1:nLevels
        fprintf("%8.3f      %+12.3f      %+15.3f      %+12.3f\n", ...
            sigmaLogVec(j), stats.Percent.Min(j), stats.Percent.Median(j), stats.Percent.Max(j));
    end

    if opts.MakePlots
        localPlotCovarianceSweep(out);
    end

end

function opts = localDefaultCovSweepOpts(opts)

    if ~isfield(opts, "Mode")
        opts.Mode = "eigen";
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

function Pc = localChanPc(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR)

    Ccomb = localSym(Ceci1(1:3,1:3) + Ceci2(1:3,1:3));

    rRel = reci2 - reci1;
    vRel = veci2 - veci1;

    [rMiss2D, C2D] = conjunction_plane_2d(rRel, vRel, Ccomb);

    Pc = chan_pc(rMiss2D, localSym(C2D), HBR);

end

function [Cpert, scaleFactors] = localPerturbCovariance(C, sigmaLog, mode)

    C = localMakeSPD(C);

    switch lower(char(mode))

        case "scalar"

            scaleFactors = exp(sigmaLog * randn(1,1));
            Cpert = scaleFactors * C;

        case "eigen"

            [V,D] = eig(C);
            lambda = real(diag(D));

            scaleFactors = exp(sigmaLog * randn(size(lambda)));

            Cpert = V * diag(lambda .* scaleFactors) * V.';

        otherwise

            error("Unknown covariance perturbation mode: %s", string(mode));

    end

    Cpert = localMakeSPD(Cpert);

end

function stats = localSweepStats(Pc, relDev, pctDev, log10Ratio)

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

function localPlotCovarianceSweep(out)

    x = out.SigmaLogVec(:).';

    figure("Name", "Covariance perturbation sweep");

    tiledlayout(2,2);

    nexttile
    hold on
    fill([x fliplr(x)], [out.Stats.Percent.P05 fliplr(out.Stats.Percent.P95)], [0.85 0.85 0.85], "EdgeColor", "none");
    plot(x, out.Stats.Percent.Min, "--", "LineWidth", 1.0);
    plot(x, out.Stats.Percent.Median, "LineWidth", 2.0);
    plot(x, out.Stats.Percent.Max, "--", "LineWidth", 1.0);
    yline(0, "k:");
    grid on
    xlabel("\sigma_{log}");
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
    xlabel("\sigma_{log}");
    ylabel("Pc");
    title("Pc range vs covariance perturbation");
    legend("min", "5%", "median", "95%", "max", "nominal", "Location", "best");

    nexttile
    X = repmat(x, size(out.PercentDeviation,1), 1);
    scatter(X(:), out.PercentDeviation(:), 8, "filled", "MarkerFaceAlpha", 0.25);
    yline(0, "k:");
    grid on
    xlabel("\sigma_{log}");
    ylabel("Pc deviation from nominal [%]");
    title("All samples");

    nexttile
    X = out.ActualPerturbationRMS;
    scatter(X(:), out.Log10Ratio(:), 8, "filled", "MarkerFaceAlpha", 0.25);
    yline(0, "k:");
    grid on
    xlabel("Actual RMS log covariance scale");
    ylabel("log_{10}(Pc / Pc_{nominal})");
    title("Deviation vs actual perturbation magnitude");

end
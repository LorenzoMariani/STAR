function out = mc_covariance_chan(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR, N, opts)
%MC_COVARIANCE_CHAN Monte Carlo sensitivity of Chan 2D Pc to covariance changes.
%
% This function perturbs the two 6x6 ECI covariance matrices and recomputes
% Chan 2D collision probability for each perturbed covariance.
%
% Inputs:
%   reci1, veci1    Object 1 ECI position [m] and velocity [m/s], 3x1
%   Ceci1           Object 1 ECI covariance, 6x6
%   reci2, veci2    Object 2 ECI position [m] and velocity [m/s], 3x1
%   Ceci2           Object 2 ECI covariance, 6x6
%   HBR             Hard-body radius [m]
%   N               Number of Monte Carlo samples
%   opts            Optional struct:
%                   opts.SigmaLog      lognormal sigma, default 0.25
%                   opts.Perturbation  "eigen" or "scalar", default "eigen"
%                   opts.MakePlots     true/false, default true
%                   opts.Seed          random seed, default []
%
% Output:
%   out.Pc                  N x 1 Chan Pc samples
%   out.PcNominal           nominal Chan Pc
%   out.C2dAreaScale        N x 1 projected covariance area scale
%   out.CovarianceScaleMean N x 1 average applied covariance scale
%   out.Stats               summary statistics

    if nargin < 8 || isempty(N)
        N = 5000;
    end

    if nargin < 9 || isempty(opts)
        opts = struct();
    end

    opts = localDefaultOptsCov(opts);

    if ~isempty(opts.Seed)
        rng(opts.Seed);
    end

    reci1 = reci1(:);
    veci1 = veci1(:);
    reci2 = reci2(:);
    veci2 = veci2(:);

    Ceci1 = localSymmetrize(Ceci1);
    Ceci2 = localSymmetrize(Ceci2);

    [Pc0, r2d0, C2d0] = localChanPc(reci1, veci1, Ceci1, reci2, veci2, Ceci2, HBR);

    Pc                  = zeros(N, 1);
    C2dAreaScale        = zeros(N, 1);
    CovarianceScaleMean = zeros(N, 1);

    detC2d0 = max(det(localSymmetrize(C2d0)), realmin);

    for k = 1:N

        [Ceci1k, scale1] = localPerturbCovariance(Ceci1, opts);
        [Ceci2k, scale2] = localPerturbCovariance(Ceci2, opts);

        [Pc(k), ~, C2dk] = localChanPc(reci1, veci1, Ceci1k, reci2, veci2, Ceci2k, HBR);

        detC2dk = max(det(localSymmetrize(C2dk)), realmin);

        C2dAreaScale(k)        = sqrt(detC2dk / detC2d0);
        CovarianceScaleMean(k) = mean([scale1(:); scale2(:)]);

    end

    out = struct();
    out.Pc                  = Pc;
    out.PcNominal           = Pc0;
    out.rMiss2DNominal      = r2d0;
    out.C2DNominal          = C2d0;
    out.C2dAreaScale        = C2dAreaScale;
    out.CovarianceScaleMean = CovarianceScaleMean;
    out.Options             = opts;
    out.Stats               = localStats(Pc);

    fprintf("\nCovariance MC results\n");
    fprintf("Nominal Pc       : %.6e\n", out.PcNominal);
    fprintf("Mean Pc          : %.6e\n", out.Stats.Mean);
    fprintf("Median Pc        : %.6e\n", out.Stats.Median);
    fprintf("5%% - 95%% Pc      : %.6e  %.6e\n", out.Stats.P05, out.Stats.P95);
    fprintf("Min - Max Pc     : %.6e  %.6e\n", out.Stats.Min, out.Stats.Max);

    if opts.MakePlots
        localPlotCovMC(out);
    end

end

function opts = localDefaultOptsCov(opts)

    if ~isfield(opts, "SigmaLog")
        opts.SigmaLog = 0.25;
    end

    if ~isfield(opts, "Perturbation")
        opts.Perturbation = "eigen";
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

function [Cpert, scaleFactors] = localPerturbCovariance(C, opts)

    C = localMakeSPD(C, opts.EigenFloorRel);
    n = size(C, 1);

    switch lower(char(opts.Perturbation))

        case "scalar"

            scaleFactors = exp(opts.SigmaLog * randn(1, 1));
            Cpert = scaleFactors * C;

        case "eigen"

            [V, D] = eig(C);
            lambda = real(diag(D));

            scaleFactors = exp(opts.SigmaLog * randn(n, 1));

            Cpert = V * diag(lambda .* scaleFactors) * V.';

        otherwise

            error("Unknown covariance perturbation mode: %s", string(opts.Perturbation));

    end

    Cpert = localSymmetrize(Cpert);
    Cpert = localMakeSPD(Cpert, opts.EigenFloorRel);

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

function localPlotCovMC(out)

    PcPlot = max(out.Pc, realmin);

    figure("Name", "Monte Carlo - Covariance Perturbation");

    subplot(2,2,1)
    histogram(out.Pc, 50);
    grid on
    xlabel("Pc");
    ylabel("Count");
    title("Chan Pc distribution");

    subplot(2,2,2)
    histogram(log10(PcPlot), 50);
    grid on
    xlabel("log_{10}(Pc)");
    ylabel("Count");
    title("Log Pc distribution");

    subplot(2,2,3)
    [xs, F] = localEmpiricalCDF(out.Pc);
    plot(xs, F, "LineWidth", 1.5);
    hold on
    xline(out.PcNominal, "--", "Nominal");
    grid on
    xlabel("Pc");
    ylabel("Empirical CDF");
    title("Pc cumulative distribution");

    subplot(2,2,4)
    scatter(out.C2dAreaScale, PcPlot, 12, "filled");
    hold on
    yline(out.PcNominal, "--", "Nominal");
    grid on
    set(gca, "YScale", "log");
    xlabel("Projected 2D covariance area scale");
    ylabel("Pc");
    title("Pc sensitivity to covariance size");

end
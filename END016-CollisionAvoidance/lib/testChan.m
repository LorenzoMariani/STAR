%% Collision Probability Method Comparison
%  Compares Chan 2D, PcCircle, Foster 2D, Hall 2D, Hall 3D
%  against CARA reference values (cara2DPc), matched by Conjunction ID.

clear; clc; close all;
addpath("C:\Users\s5oss\Desktop\software_s5lab\STAR\END016-CollisionAvoidance\CARA_Analysis_Tools\DistributedMatlab\ProbabilityOfCollision")

%% ── Paths ───────────────────────────────────────────────────────────────
folder   = "C:\Users\s5oss\Desktop\software_s5lab\STAR\END016-CollisionAvoidance\CARA_Analysis_Tools\DataFiles\PcTestCaseCDMs";
fileCara = fullfile(folder, "CARA_PcMethod_Test_Conjunctions.xlsx");

%% ── Load CARA reference data ────────────────────────────────────────────
caraData  = readtable(fileCara);
cara2DPc  = caraData.Pc2D;
caraCdmId = string(caraData.Conjunction_ID);

%% ── List CDM files ──────────────────────────────────────────────────────
cdmFiles = dir(fullfile(folder, "*.cdm"));
names    = string(extractfield(cdmFiles, 'name'));
nCdm     = numel(names);

%% ── Pre-allocate result arrays ──────────────────────────────────────────
conjId       = strings(nCdm, 1);
Pc_chan      = nan(nCdm, 1);
Pc_circle    = nan(nCdm, 1);
Pc_foster    = nan(nCdm, 1);
Pc_hall2d    = nan(nCdm, 1);
Pc_hall3d    = nan(nCdm, 1);
Pc_cara_ref  = nan(nCdm, 1);

%% ── Process each CDM ────────────────────────────────────────────────────
for i = 1:nCdm

    filename = fullfile(folder, names(i));
    cdm      = parseCDMcara(filename);

    % ── Extract Conjunction ID from filename ─────────────────────────────
    [~, conjId(i), ~] = fileparts(names(i));

    % ── Object 1 ─────────────────────────────────────────────────────────
    obj1 = cdm.Objects(1);
    validateObject(obj1, names(i));

    reci1 = [obj1.X.Value; obj1.Y.Value; obj1.Z.Value] .* 1e3;
    veci1 = [obj1.X_DOT.Value; obj1.Y_DOT.Value; obj1.Z_DOT.Value] .* 1e3;
    Crtc1 = buildCovMatrix(obj1);
    M1    = rot_eci2rtc(reci1, veci1);
    Ceci1 = blkdiag(M1.', M1.') * Crtc1 * blkdiag(M1, M1);

    % ── Object 2 ─────────────────────────────────────────────────────────
    obj2 = cdm.Objects(2);
    validateObject(obj2, names(i));

    reci2 = [obj2.X.Value; obj2.Y.Value; obj2.Z.Value] .* 1e3;
    veci2 = [obj2.X_DOT.Value; obj2.Y_DOT.Value; obj2.Z_DOT.Value] .* 1e3;
    Crtc2 = buildCovMatrix(obj2);
    M2    = rot_eci2rtc(reci2, veci2);
    Ceci2 = blkdiag(M2.', M2.') * Crtc2 * blkdiag(M2, M2);

    % ── Conjunction plane ────────────────────────────────────────────────
    Ccomb   = Ceci1(1:3, 1:3) + Ceci2(1:3, 1:3);
    r_rel   = reci2 - reci1;
    v_rel   = veci2 - veci1;
    [r_miss_2d, C_2d, ~] = conjunction_plane_2d(r_rel, v_rel, Ccomb);
    HBR     = cdm.Header.CommentFields.HBR.Value;

    % ── Probability of Collision methods ─────────────────────────────────
    Pc_chan(i)   = chan_pc(r_miss_2d, C_2d, HBR);
    Pc_circle(i) = PcCircle(reci1', veci1', Ceci1, reci2', veci2', Ceci2, HBR);
    [Pc_foster(i), ~, ~, ~] = Pc2D_Foster(reci1', veci1', Ceci1, ...
                                           reci2', veci2', Ceci2, HBR, 1e-8, 'circle');
    [Pc_hall2d(i), ~] = Pc2D_Hall(reci1', veci1', Ceci1, reci2', veci2', Ceci2, HBR);
    [Pc_hall3d(i), ~] = Pc3D_Hall(reci1', veci1', Ceci1, reci2', veci2', Ceci2, HBR);

    % ── Match to CARA reference ──────────────────────────────────────────
    idx = find(caraCdmId == conjId(i), 1);
    if ~isempty(idx)
        Pc_cara_ref(i) = cara2DPc(idx);
    else
        warning("No CARA reference found for conjunction ID: %s", conjId(i));
    end

    fprintf("[%3d/%3d] %s  Pc_chan=%.3e  Pc_CARA=%.3e\n", ...
            i, nCdm, conjId(i), Pc_chan(i), Pc_cara_ref(i));
end

%% ── Build comparison table ──────────────────────────────────────────────
T = table(conjId, Pc_cara_ref, Pc_chan, Pc_circle, Pc_foster, Pc_hall2d, Pc_hall3d, ...
    'VariableNames', { ...
        'ConjunctionID', 'CARA_2D_Ref', ...
        'Chan_2D', 'PcCircle', 'Foster_2D', 'Hall_2D', 'Hall_3D'});

% Absolute errors with respect to CARA reference
T.Err_Chan   = abs(T.Chan_2D   - T.CARA_2D_Ref);
T.Err_Circle = abs(T.PcCircle  - T.CARA_2D_Ref);
T.Err_Foster = abs(T.Foster_2D - T.CARA_2D_Ref);
T.Err_Hall2D = abs(T.Hall_2D   - T.CARA_2D_Ref);
T.Err_Hall3D = abs(T.Hall_3D   - T.CARA_2D_Ref);

% Relative errors (%)
T.RelErr_Chan   = 100 * T.Err_Chan   ./ T.CARA_2D_Ref;
T.RelErr_Circle = 100 * T.Err_Circle ./ T.CARA_2D_Ref;
T.RelErr_Foster = 100 * T.Err_Foster ./ T.CARA_2D_Ref;
T.RelErr_Hall2D = 100 * T.Err_Hall2D ./ T.CARA_2D_Ref;
T.RelErr_Hall3D = 100 * T.Err_Hall3D ./ T.CARA_2D_Ref;

disp("=== Probability of Collision Comparison Table ===");
disp(T(:, 1:7));   % show Pc values
disp("=== Absolute Errors vs CARA 2D Reference ===");
disp(T(:, [1 8:12]));
disp("=== Relative Errors (%) vs CARA 2D Reference ===");
disp(T(:, [1 13:17]));

%% ── Plot: Absolute Error per method ─────────────────────────────────────
methodLabels = {'Chan 2D', 'PcCircle', 'Foster 2D', 'Hall 2D', 'Hall 3D'};
errMatrix    = [T.Err_Chan, T.Err_Circle, T.Err_Foster, T.Err_Hall2D, T.Err_Hall3D];
nMethods     = numel(methodLabels);
colors       = lines(nMethods);

xTick = 1:nCdm;

figure('Name','Absolute Error vs CARA 2D Pc','Color','w','Position',[100 100 1200 500]);
semilogy(xTick, errMatrix, 'o-', 'LineWidth', 1.2, 'MarkerSize', 5);
set(gca, 'ColorOrder', colors, 'XTick', xTick, ...
         'XTickLabel', T.ConjunctionID, 'XTickLabelRotation', 45);
legend(methodLabels, 'Location','best','FontSize',9);
xlabel('Conjunction ID');
ylabel('|Pc_{method} - Pc_{CARA}|  (absolute error)');
title('Absolute Error of Each Pc Method vs CARA 2D Reference');
grid on; grid minor;
xlim([0.5, nCdm + 0.5]);

%% ── Plot: Relative Error (%) per method ─────────────────────────────────
relErrMatrix = [T.RelErr_Chan, T.RelErr_Circle, T.RelErr_Foster, ...
                T.RelErr_Hall2D, T.RelErr_Hall3D];

figure('Name','Relative Error vs CARA 2D Pc','Color','w','Position',[100 650 1200 500]);
semilogy(xTick, relErrMatrix, 's--', 'LineWidth', 1.2, 'MarkerSize', 5);
set(gca, 'ColorOrder', colors, 'XTick', xTick, ...
         'XTickLabel', T.ConjunctionID, 'XTickLabelRotation', 45);
legend(methodLabels, 'Location','best','FontSize',9);
xlabel('Conjunction ID');
ylabel('Relative Error (%)');
title('Relative Error (%) of Each Pc Method vs CARA 2D Reference');
grid on; grid minor;
xlim([0.5, nCdm + 0.5]);

%% ── Plot: Pc values side-by-side (log scale) ────────────────────────────
pcMatrix = [T.CARA_2D_Ref, T.Chan_2D, T.PcCircle, T.Foster_2D, T.Hall_2D, T.Hall_3D];
allLabels = [{'CARA Ref'}, methodLabels];

figure('Name','Pc Method Comparison','Color','w','Position',[100 1200 1200 500]);
semilogy(xTick, pcMatrix, '-o', 'LineWidth', 1.2, 'MarkerSize', 5);
set(gca, 'XTick', xTick, 'XTickLabel', T.ConjunctionID, 'XTickLabelRotation', 45);
legend(allLabels, 'Location','best','FontSize',9);
xlabel('Conjunction ID');
ylabel('Probability of Collision');
title('Pc Values — All Methods vs CARA 2D Reference');
grid on; grid minor;
xlim([0.5, nCdm + 0.5]);

%% ── Helper functions ────────────────────────────────────────────────────

function validateObject(obj, fname)
%VALIDATEOBJECT  Warn if reference frame or covariance scale are unexpected.
    if ~strcmp(obj.REF_FRAME.Value, "EME2000")
        warning("Non-inertial reference frame in CDM: %s", fname);
    end
    if obj.CommentFields.COVARIANCE_SCALE_FACTOR.Value ~= 1
        warning("Covariance scale factor ≠ 1 in CDM: %s", fname);
    end
end

function C = buildCovMatrix(obj)
%BUILDCOVMATRIX  Assemble 6×6 RTN covariance from CDM object fields.
    C = [obj.CR_R.Value      obj.CT_R.Value      obj.CN_R.Value      obj.CRDOT_R.Value      obj.CTDOT_R.Value      obj.CNDOT_R.Value;
         obj.CT_R.Value      obj.CT_T.Value      obj.CN_T.Value      obj.CRDOT_T.Value      obj.CTDOT_T.Value      obj.CNDOT_T.Value;
         obj.CN_R.Value      obj.CN_T.Value      obj.CN_N.Value      obj.CRDOT_N.Value      obj.CTDOT_N.Value      obj.CNDOT_N.Value;
         obj.CRDOT_R.Value   obj.CRDOT_T.Value   obj.CRDOT_N.Value   obj.CRDOT_RDOT.Value   obj.CTDOT_RDOT.Value   obj.CNDOT_RDOT.Value;
         obj.CTDOT_R.Value   obj.CTDOT_T.Value   obj.CTDOT_N.Value   obj.CTDOT_RDOT.Value   obj.CTDOT_TDOT.Value   obj.CNDOT_TDOT.Value;
         obj.CNDOT_R.Value   obj.CNDOT_T.Value   obj.CNDOT_N.Value   obj.CNDOT_RDOT.Value   obj.CNDOT_TDOT.Value   obj.CNDOT_NDOT.Value];
end
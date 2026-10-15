% star_power_budget.m
% STAR END-004 Power Budget module.
%
% The script can be executed directly by the STAR Python runner.  It also
% exposes the local function STAR_END004_POWER_BUDGET(configFile, outputFolder)
% used as the computational entry point.

clear; clc; close all;
set(0, 'DefaultFigureVisible', 'off');
addpath(fileparts(mfilename('fullpath')));

default_file_input = "C:\Users\s5oss\Desktop\software_s5lab\STAR\Input\input_power_budget.json";
default_path_output = "C:\Users\s5oss\Desktop\software_s5lab\STAR\Output\output_power_budget";

star_input_override = getenv('STAR_END004_INPUT_FILE');
star_output_override = getenv('STAR_END004_OUTPUT_DIR');
if isempty(star_output_override)
    star_output_override = getenv('STAR_MODULE_OUTPUT_DIR');
end

if ~isempty(star_input_override)
    file_input = string(star_input_override);
else
    file_input = default_file_input;
end

if ~isempty(star_output_override)
    path_output = string(star_output_override);
else
    path_output = default_path_output;
end

fprintf('[STAR END-004] Input JSON: %s\n', file_input);
fprintf('[STAR END-004] Output folder: %s\n', path_output);

entryPoint = which('STAR_END004_POWER_BUDGET');
if isempty(entryPoint)
    error('STAR_END004_POWER_BUDGET:EntryPointNotFound', ...
        'The MATLAB entry point STAR_END004_POWER_BUDGET.m was not found on the MATLAB path. Check END004-PowerBudget installation.');
end
fprintf('[STAR END-004] MATLAB entry point: %s\n', entryPoint);

try
    status = STAR_END004_POWER_BUDGET(file_input, path_output);
catch ME
    % Backward compatibility: an earlier END-004 package defined
    % STAR_END004_POWER_BUDGET(configFile, outputFolder) with no return
    % argument. Calling it as "status = ..." triggers:
    % "Incorrect number or types of inputs or outputs".
    isTopLevelSignatureMismatch = contains(ME.message, 'Incorrect number or types of inputs or outputs') ...
        && ~isempty(ME.stack) ...
        && contains(ME.stack(1).name, 'star_power_budget');
    isTooManyOutputs = contains(ME.message, 'Too many output arguments') ...
        && ~isempty(ME.stack) ...
        && contains(ME.stack(1).name, 'star_power_budget');

    if isTopLevelSignatureMismatch || isTooManyOutputs
        fprintf('[STAR END-004] Entry point does not return a status argument. Re-running without output capture.\n');
        STAR_END004_POWER_BUDGET(file_input, path_output);
        status = "completed";
    else
        rethrow(ME);
    end
end

if isstring(status) || ischar(status)
    fprintf('[STAR END-004] Completed with status: %s\n', char(status));
else
    fprintf('[STAR END-004] Completed with numeric status: %g\n', status);
end


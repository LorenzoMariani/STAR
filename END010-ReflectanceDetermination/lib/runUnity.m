function [status, cmdout] = runUnity(exePath, opts)

    args = {};
    opts.timeOutSec = 300;
    % Key (unity) - Value (matlab) input encoding (string/path)
    addString('-csvFile',             'csvFile');
    addString('-lightCurveFilename',  'lightCurveFilename');
    addString('-outputFolder',        'outputFolder');
    
    % Key (unity) - Value (matlab) input encoding (numeric)
    addNumeric('-maxFrameToRender',   'maxFrameToRender');
    addNumeric('-maxFrameToSave',     'maxFrameToSave');
    addNumeric('-camWidth',           'camWidth');
    addNumeric('-camHeight',          'camHeight');
    addNumeric('-exposure',           'exposure');
    addNumeric('-focalLength',        'focalLength');
    addNumeric('-camSize',            'camSize');
    % STAR CubeSat build (unity_project): scale of the csv positions (km) and class of the NASA-style CDS model (1, 2, 3, 6, 12)
    addNumeric('-sceneScale',         'sceneScale');
    addNumeric('-cubesatClass',       'cubesatClass');
    
    % Key (unity) - Value (matlab) input encoding (presence == true)
    addBool('-drawAxis',              'drawAxis');
    addBool('-useOrtographic',        'useOrtographic');
    addBool('-useLinearSpace',        'useLinearSpace');
    addBool('-enableView',            'enableView');
    addBool('-saveFrames',            'saveFrames');
    addBool('-sumFlux',               'sumFlux');
    addBool('-UseRadiometricModel',   'UseRadiometricModel');
    addBool('-UseFacetSum',           'UseFacetSum');
    
    % Optional Unity player log redirection
    if isfield(opts,'logFile') && ~isempty(opts.logFile)
        args{end+1} = '-logFile';
        args{end+1} = char(string(opts.logFile));
    end
    
    % Final argument list (no shell quoting needed here)
    cmdArgs = [{'-batchmode', '-quit'}, args];
    
    % Per-worker temp files for stdout/stderr capture
    stdoutFile = [tempname '_unity_stdout.txt'];
    stderrFile = [tempname '_unity_stderr.txt'];
    cleaner = onCleanup(@() cleanupFiles({stdoutFile, stderrFile})); %#ok<NASGU>
    
    % Build Java ProcessBuilder command list
    cmdList = java.util.ArrayList();
    cmdList.add(java.lang.String(exePath));
    for k = 1:numel(cmdArgs)
        cmdList.add(java.lang.String(char(string(cmdArgs{k}))));
    end
    
    pb = java.lang.ProcessBuilder(cmdList);
    pb.redirectOutput(java.io.File(stdoutFile));
    pb.redirectError(java.io.File(stderrFile));
    
    % Start process
    proc = pb.start();
    
    % Wait with timeout
    timedOut = false;
    if isfinite(opts.timeOutSec)
        finished = proc.waitFor(int64(ceil(opts.timeOutSec)), ...
            java.util.concurrent.TimeUnit.SECONDS);
    else
        proc.waitFor();
        finished = true;
    end
    
    if ~finished
        timedOut = true;
    
        % Try to get PID (available in newer Java versions used by MATLAB)
        pid = [];
        try
            pid = double(proc.pid());
        catch
        end
    
        % First try graceful stop, then force
        try
            proc.destroy();
        catch
        end
        pause(0.5);
    
        try
            if proc.isAlive()
                proc.destroyForcibly();
                pause(0.5);
            end
        catch
        end
    
        % Extra safety on Windows: kill whole process tree
        if ispc && ~isempty(pid)
            try
                system(sprintf('taskkill /PID %d /T /F >NUL 2>&1', pid));
            catch
            end
        end
    
        status = 124;  % standard timeout-like code
    else
        status = double(proc.exitValue());
    end
    
    % Read captured output
    stdoutTxt = readIfExists(stdoutFile);
    stderrTxt = readIfExists(stderrFile);
    
    parts = {};
    
    if timedOut
        parts{end+1} = sprintf('Unity timed out after %.3f s and was terminated.', opts.timeOutSec);
    end
    
    if ~isempty(strtrim(stdoutTxt))
        parts{end+1} = sprintf('=== STDOUT ===\n%s', stdoutTxt);
    end
    
    if ~isempty(strtrim(stderrTxt))
        parts{end+1} = sprintf('=== STDERR ===\n%s', stderrTxt);
    end
    
    % If nothing came to stdout/stderr, optionally read Unity log
    if isempty(parts) && isfield(opts,'logFile') && ~isempty(opts.logFile) && isfile(opts.logFile)
        try
            parts{end+1} = sprintf('=== UNITY LOG ===\n%s', fileread(opts.logFile));
        catch
        end
    end
    
    if isempty(parts)
        cmdout = '';
    else
        cmdout = strjoin(parts, sprintf('\n\n'));
    end
    
    % ------------------------------------------------------------------ %
    % Helpers
    % ------------------------------------------------------------------ %
    function addString(flag, field)
        if isfield(opts, field) && ~isempty(opts.(field))
            args{end+1} = flag;
            args{end+1} = char(string(opts.(field)));
        end
    end

    function addNumeric(flag, field)
        if isfield(opts, field) && ~isempty(opts.(field))
            args{end+1} = flag;
            % Preserve non-integer numeric values too
            args{end+1} = sprintf('%.17g', opts.(field));
        end
    end

    function addBool(flag, field)
        if isfield(opts, field) && islogical(opts.(field)) && opts.(field)
            args{end+1} = flag;
        end
    end

    function txt = readIfExists(f)
        txt = '';
        try
            if isfile(f)
                txt = fileread(f);
            end
        catch
            txt = '';
        end
    end

    function cleanupFiles(files)
        for i = 1:numel(files)
            try
                if isfile(files{i})
                    delete(files{i});
                end
            catch
            end
        end
    end
end
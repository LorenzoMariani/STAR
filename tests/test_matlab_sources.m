function tests = test_matlab_sources
%TEST_MATLAB_SOURCES  Code Analyzer errors in the MATLAB sources of STAR (2026-10-20).
%
%   From the STAR folder:   results = runtests('tests/test_matlab_sources.m')     (run_all_tests.py: suite MCODE)
%
%   checkcode -m2 reports only the errors of the Code Analyzer (red in the editor): syntax errors, which stop a file
%   from running at all, and constructs it knows to be wrong (e.g. isempty on a logical expression). Warnings are not
%   checked, nor run-time errors such as an undefined variable in a script.
%   Folders: END-003, END-004, END-010, END-016, END-018 and tests. Left out, as code STAR does not maintain here:
%   END-001 (its own repository, a git submodule), CARA_Analysis_Tools (NASA CARA), the lib/sgp4 folders (Vallado's
%   SGP4; in END-010, ecef2lle.m and mincomb.m are Fortran-like and do not parse, and nothing calls them), the Unity
%   project of END-010 and the _old* copies.
    tests = functiontests(localfunctions);
end

function test_no_code_analyzer_errors(tc)
    root = fileparts(fileparts(mfilename('fullpath')));
    [files, rel] = star_sources(root);
    verifyGreaterThan(tc, numel(files), 50);                                      % 74 on 2026-10-20
    msgs = checkcode(cellstr(files), '-id', '-m2');
    problems = strings(0, 1);
    for k = find(~cellfun(@isempty, msgs))'
        for m = msgs{k}(:)'
            problems(end + 1) = sprintf('%s:%d [%s] %s', rel(k), m.line, m.id, m.message); %#ok<AGROW>
        end
    end
    verifyEmpty(tc, problems, strjoin(problems, newline));
end

function test_the_check_sees_a_syntax_error(tc)
    % the -m2 level of this MATLAB release still reports a parse error, and not a warning
    folder = tempname;
    mkdir(folder);
    cleanup = onCleanup(@() rmdir(folder, 's'));
    bad = fullfile(folder, 'broken.m');
    fid = fopen(bad, 'w'); fprintf(fid, 'function y = broken(x)\ny = (x + 1;\nend\n'); fclose(fid);
    ok = fullfile(folder, 'warned.m');
    fid = fopen(ok, 'w'); fprintf(fid, 'function y = warned(x)\nz = 3;\ny = x\nend\n'); fclose(fid);
    msgs = checkcode({bad, ok}, '-id', '-m2');
    verifyEqual(tc, {msgs{1}.id}, {'NOPAR'});
    verifyEmpty(tc, msgs{2});
    clear cleanup
end

%% =========================================================================
function [files, rel] = star_sources(root)
    folders = ["END003-AttitudePropagation", "END004-PowerBudget", "END010-ReflectanceDetermination", ...
        "END016-CollisionAvoidance", "END018-ComponentsThermalAnalysis", "tests"];
    files = strings(0, 1);
    for f = folders
        d = dir(fullfile(root, f, '**', '*.m'));
        files = [files; string(fullfile({d.folder}, {d.name}))']; %#ok<AGROW>
    end
    rel = erase(replace(files, '\', '/'), replace(string(root), '\', '/') + "/");
    skip = contains(rel, ["/CARA_Analysis_Tools/", "/sgp4/", "/unity_project/", "/_old"]);
    files = files(~skip); rel = rel(~skip);
end

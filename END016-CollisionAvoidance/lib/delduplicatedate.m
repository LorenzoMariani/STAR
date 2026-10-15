function delduplicatedate(in, out, epochTol)
% -------------------------------------------------------------------------
% Delete duplicate TLEs with the same satellite number and epoch.
%
% Handles cases where satellite IDs are written as:
%   745
%   00745
%
% Also handles tiny epoch differences due to rounding, e.g.
%   26116.89383913
%   26116.89383914
%
% Usage:
%   delduplicatedate('input.txt', 'output.txt')
%   delduplicatedate('input.txt', 'output.txt', 1e-8)
% -------------------------------------------------------------------------

if nargin < 3
    epochTol = 1e-7;
end

fid1 = fopen(in, 'r');
if fid1 == -1
    error('Could not open input file: %s', in);
end

fid2 = fopen(out, 'w');
if fid2 == -1
    fclose(fid1);
    error('Could not open output file: %s', out);
end

seen = containers.Map('KeyType', 'char', 'ValueType', 'logical');

line = fgetl(fid1);

while ischar(line)

    l0 = line;
    l1 = fgetl(fid1);
    l2 = fgetl(fid1);

    if ~ischar(l1) || ~ischar(l2)
        warning('Incomplete TLE block found at end of file. Skipping.');
        break;
    end

    % Split TLE line 1
    parts    = strsplit(strtrim(l1));
    satField = parts{2};
    epoch    = str2double(parts{4});

    % Extract only the numeric satellite ID, ignoring U/C/S/etc.
    satNumStr = regexp(satField, '\d+', 'match', 'once');
    satNum    = str2double(satNumStr);

    % Round epoch to tolerance to avoid tiny last-digit differences
    epochRounded = round(epoch / epochTol);

    % Unique key: same satellite + same epoch
    key = sprintf('%05d_%d', satNum, epochRounded);

    if ~isKey(seen, key)
        fprintf(fid2, '%s\n', l0);
        fprintf(fid2, '%s\n', l1);
        fprintf(fid2, '%s\n', l2);

        seen(key) = true;
    end

    line = fgetl(fid1);
end

fclose(fid1);
fclose(fid2);

end
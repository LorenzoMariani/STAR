function getTle(start_date, end_date, norad, tlePath)

% URL
url = sprintf([ ...
    'https://www.space-track.org/basicspacedata/query/' ...
    'class/gp_history/NORAD_CAT_ID/%d/orderby/TLE_LINE1%%20ASC/' ...
    'EPOCH/%s--%s/format/3le'], ...
    str2double(norad), start_date, end_date);


% Cmd
cmd = sprintf('curl -s -b "%s" -c "%s" "%s"', "cookie.txt", "cookie.txt", url);
[status, tle_data] = system(cmd);

if status ~= 0
    fprintf('[ID %d] Error downloading tle: %s', norad, status);
end

lines = regexp(tle_data, '\r?\n', 'split');
lines = lines(~cellfun(@(s) isempty(strtrim(s)), lines));

if ~isempty(lines)
    fid = fopen(tlePath,'w');
    for i = 1:numel(lines)
        fprintf(fid, '%s\n', lines{i});
    end
else
    fprintf("Missing TLEs\n")
end
fclose(fid);





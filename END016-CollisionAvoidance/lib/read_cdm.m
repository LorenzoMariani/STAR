function [obj1, obj2, tca, R1_km, R2_km] = read_cdm(filename)
%READ_CDM Parse Conjunction Data Message (CDM) file.
%   [obj1, obj2, tca] = read_cdm(filename) returns primary object ID, secondary
%   object ID, and time of closest approach string.
%   [obj1, obj2, tca, R1_km, R2_km] = read_cdm(filename) also returns
%   hard-body radii in km from SAT_1_EXCL_VOL and SAT_2_EXCL_VOL (assumed
%   radius in m in CDM). Default 5e-3 km (5 m) if missing.

DEFAULT_RADIUS_M = 5;  % default radius in meters if not in CDM

fid = fopen(filename,'r');
line = fgetl(fid);

obj1 = '';
obj2 = '';
tca = '';
R1_km = DEFAULT_RADIUS_M * 1e-3;
R2_km = DEFAULT_RADIUS_M * 1e-3;
R1_set = false;
R2_set = false;

while ischar(line)
    if contains(line,"TCA")
        parts = strsplit(line);
        tca = parts{2}(2:end);
    elseif contains(line,"SAT_1_ID")
        parts = strsplit(line);
        obj1 = parts{2}(2:end);
    elseif contains(line,"SAT_2_ID")
        parts = strsplit(line);
        obj2 = parts{2}(2:end);
    elseif contains(line,"SAT_1_EXCL_VOL")
        parts = strsplit(line);
        val = str2double(strtrim(parts{2}(2:end)));
        if ~isnan(val) && val > 0
            R1_km  = val * 1e-3;  
            R1_set = true;
        end
    elseif contains(line,"SAT_2_EXCL_VOL")
        parts = strsplit(line);
        val = str2double(strtrim(parts{2}(2:end)));
        if ~isnan(val) && val > 0
            R2_km  = val * 1e-3;
            R2_set = true;
        end
    end
    line = fgetl(fid);
end

fclose(fid);

if ~R1_set
    warning('read_cdm:defaultRadius', ...
        'CDM missing SAT_1_EXCL_VOL; using default hard-body radius %g m for SAT_1.', ...
        DEFAULT_RADIUS_M);
end
if ~R2_set
    warning('read_cdm:defaultRadius', ...
        'CDM missing SAT_2_EXCL_VOL; using default hard-body radius %g m for SAT_2.', ...
        DEFAULT_RADIUS_M);
end
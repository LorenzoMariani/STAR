function tle = sorttle(path)


tle = readTleFile(path);

for i = 1:length(tle)
    t = tle{1,i};
    line  = char(t(1));
    ind   = strsplit(string(line));
    epoch = str2double(ind(4));
    e(1,i) = epoch;
end

[~,i] = sort(e);
tle = tle(i);

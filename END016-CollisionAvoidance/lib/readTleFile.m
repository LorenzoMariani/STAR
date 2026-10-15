function tle = readTleFile(filename)

tle = {};
str = string;
i=0;

fid = fopen(filename,'r');

line = fgetl(fid);

while ischar(line)
    i=i+1;
    if strcmp(line(1),'0')
        str(1) = fgetl(fid);
        str(2) = fgetl(fid);
    end
    tle{i} = str;
    line = fgetl(fid);
end

fclose(fid);
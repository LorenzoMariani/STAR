function geteop(patheop)

date        = datetime('today');
date.Format = 'yyyy-MM-dd';
if isfile(patheop)
    if update_EOP(patheop,date)
        options = weboptions('Timeout',Inf);
        out     = webread('https://celestrak.org/SpaceData/EOP-All.txt',options);
        fid     = fopen(patheop,'w'); fprintf(fid,out); fclose(fid);
    end
else
    options = weboptions('Timeout',Inf);
    out     = webread('https://celestrak.org/SpaceData/EOP-All.txt',options);
    fid     = fopen(patheop,'w'); fprintf(fid,out); fclose(fid);
end
end
%% Helper
function flag = update_EOP(filepath,date)

fid   = fopen(filepath,'r');
line  = fgetl(fid);
line  = fgetl(fid);

year  = line(9:12);
month = line(14:16);
day   = line(18:19);

dateop = datetime(strcat(year,'-',month,'-',day),"InputFormat","y-MMM-d");

if dateop == date; flag = 0; else; flag = 1; end

fclose(fid);
end
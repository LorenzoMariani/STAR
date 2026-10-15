%% ---------------------------------------------------------------------- %
% Find EOP by date. Reads the input EOP file available at celestrak.org and
% returns a structure packing the EOP at the input date.
%
% Input:  filepath - [string 1x1]   = absoulte path to EOP filename
%         date     - [datetime 1x1] = reference date in format 'yyyy-mm-dd'
%
%
% Output: eop:     - struct struct with fields:
%                         xp in radians
%                         yp in radians
%                         dut1
%                         lod
%                         ddpsi in radians
%                         ddeps in radians
%                         dx in radians
%                         dy in radians
%                         dat
% ----------------------------------------------------------------------- %
function EOP = readEOPfile(filename,date)

if ~exist(filename, 'file')
    error("File at %s doesn't exist", filename);
end

EOP   = struct;

date  = strrep(date,'-',' ');
fid   = fopen(filename,'r');
mat   = textscan(fid,'%s','Delimiter','\n','HeaderLines',24);
fclose(fid);

for i = 1:length(mat{1})
    line = mat{1}{i,1};
    if ~isempty(line)
        if line(1:10) == date
            eop = line;
        end
    end
end

ind = strsplit(eop,' ');

if isempty(ind)
    warning("EOP not found")
    EOP.xp    = 0;
    EOP.yp    = 0;
    EOP.dut1  = 0;
    EOP.lod   = 0;
    EOP.ddpsi = 0;
    EOP.ddeps = 0;
    EOP.dx    = 0;
    EOP.dy    = 0;
    EOP.dat   = 37;
else

    EOP.xp    = str2double(ind{5})*pi/(180*3600);
    EOP.yp    = str2double(ind{6})*pi/(180*3600);
    EOP.dut1  = str2double(ind{7});
    EOP.lod   = str2double(ind{8});
    EOP.ddpsi = str2double(ind{9})*pi/(180*3600);
    EOP.ddeps = str2double(ind{10})*pi/(180*3600);
    EOP.dx    = str2double(ind{11})*pi/(180*3600);
    EOP.dy    = str2double(ind{12})*pi/(180*3600);
    EOP.dat   = str2double(ind{13});

end

end
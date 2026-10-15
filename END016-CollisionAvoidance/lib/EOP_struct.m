function EOP = EOP_struct(filepath,date)

%--------------------------------------------------------------------------
% Find EOP by date
%                                                                         
% Input: filepath: path to EOP.txt (downloaded by celestrak)
%        date:     reference date 'yyyy-mm-dd'
%
% Output eop:      line with eop at date  [char]
%
%--------------------------------------------------------------------------

EOP   = struct;

date  = strrep(date,'-',' ');
fid   = fopen(filepath,'r');
mat   = textscan(fid,'%s','Delimiter','\n','HeaderLines',24);

for i = 1:length(mat{1})
    line = mat{1}{i,1};
    if ~isempty(line)
        if line(1:10) == date
            eop = line;
        end
    end
end

fclose(fid);

ind = strsplit(eop,' ');

EOP.xp    = str2double(ind{5})*pi/(180*3600);
EOP.yp    = str2double(ind{6})*pi/(180*3600);
EOP.dut1  = str2double(ind{7});
EOP.lod   = str2double(ind{8});
EOP.ddpsi = str2double(ind{9})*pi/(180*3600);
EOP.ddeps = str2double(ind{10})*pi/(180*3600);
EOP.dx    = str2double(ind{11})*pi/(180*3600);
EOP.dy    = str2double(ind{12})*pi/(180*3600);
EOP.dat   = str2double(ind{13});



%% Help ------------------------------------------------------------------%
% 
% Asset to get relevant quantities from the propagation of an object
% orbiting the Earth.
%
% Input: inputStruct - [struct] - structure with the following fields
%                    getGeodetic    [bool] true to get obj lon lat in rad
%                    getVisibility  [bool] true to get obj visibility
%                    getAzEl        [bool] true to get obj az el in deg
%                    getRaDec       [bool] true to get obj tra tdec in deg
%                    getRange       [bool] true to get obj-obs range in km
%                    getSunRange    [bool] true to get obj.sun range in km
%                    getSunGeodetic [bool] true to get sun lon lat in rad
%                    getSun         [bool] true to get sun eci pos in km
%                    getObs         [bool] true to get obs eci pos in km
%                    getEcef        [bool] true to get obj ecef pv in km
%                    times          [datetime Nx1] propagation times utc
%                    tlefile        [string Nx1] abs path to obj tle (optional if reci is provided)
%                    reci           [double Nx3] optional - external ECI position from CSV
%                    veci           [double Nx3] optional - external ECI velocity from CSV
%                    eopfile        [string Nx1] abs path to eop
%                    lla            [double 3x1] lat lon alt in rad rad km
%                    mask           [double 1x1] obs mask angle in deg
%                    nutParams                   nut params from Vallado
%                    DE440Coeff                  planetary ephemeris coeff
%
% Output:
% ------------------------------------------------------------------------%
function out = propagation_from_reci(inputStruct)
%% Get input
getGeodetic    = inputStruct.getGeodetic;
getVisibility  = inputStruct.getVisibility;
getAzEl        = inputStruct.getAzEl;
getRaDec       = inputStruct.getRaDec;
getRange       = inputStruct.getRange;
getSunRange    = inputStruct.getSunRange;
getSunGeodetic = inputStruct.getSunGeodetic;
getSun         = inputStruct.getSun;
getObs         = inputStruct.getObs;
getEcef        = inputStruct.getEcef;
times          = inputStruct.times;
eopfile        = inputStruct.eopfile;
lla            = inputStruct.lla;
mask           = inputStruct.mask;
DE440Coeff     = inputStruct.DE440Coeff;
nutParams      = inputStruct.nutParams;

lat_gs = lla(1);
lon_gs = lla(2);
alt_gs = lla(3);

%% Init
recef     = zeros(numel(times),3);
vecef     = zeros(numel(times),3);
rseci     = zeros(numel(times),3);
rsun      = zeros(numel(times),3);
latgd_sat = zeros(numel(times),1);
latgd_sun = zeros(numel(times),1);
lon_sat   = zeros(numel(times),1);
lon_sun   = zeros(numel(times),1);
access    = zeros(length(times),1);
r         = zeros(length(times),1);
az        = zeros(length(times),1);
el        = zeros(length(times),1);
ra        = zeros(length(times),1);
dec       = zeros(length(times),1);
s         = zeros(length(times),1);

%% Get EOP
patheop = eopfile;
pathweb = 'https://celestrak.org/SpaceData/EOP-Last5Years.txt';
options = weboptions('Timeout',Inf);
% Check existance
if exist(patheop,'file')
    fid = fopen(patheop,'r');
    mat = textscan(fid,'%s','Delimiter','\n','HeaderLines',24);
    fclose(fid);
    line = mat{1}{end-1,1};
    lastdate = datetime(line(1:10),'InputFormat','yyyy MM dd');
    % Check update
    if lastdate < times(1)
        out = webread(pathweb,options);
        fid = fopen(patheop,'w'); fprintf(fid,out); fclose(fid);
    end
else
     out = webread(pathweb,options);
     fid = fopen(patheop,'w'); fprintf(fid,out); fclose(fid);
end
% Save EOP
date = times(1);
date.Format = 'yyyy MM dd';
eop  = readEOPfile(patheop,string(date));

%% Check Orbit Source: External CSV vs TLE Propagation
useInputReci = isfield(inputStruct, 'reci') && ~isempty(inputStruct.reci);

if ~useInputReci
    % --- Modalità standard: Propagazione da TLE ---
    tlefile = inputStruct.tlefile;
    if ~exist(tlefile,'file')
        error("propagation: TLE file not found at %s\n", tlefile);
    end
    fid  = fopen(tlefile);
    line = fgetl(fid);
    str1 = fgetl(fid);
    str2 = fgetl(fid);
    fclose(fid);
    
    % Process TLE
    [~, ~, ~, satrec] = twoline2rv(str1, str2, 'c', [], [], 84);
    % Tle Time
    epochtle  = satrec.jdsatepoch + satrec.jdsatepochf;
    if epochtle > juliandate(times(1))
        error("generateCSVunity::call_sgp4: tle epoch is larger than propagation epoch.")
    end
    
    reci = zeros(numel(times),3);
    veci = zeros(numel(times),3);
else
    % --- Modalità esterna: Caricamento dati da CSV ---
    reci = inputStruct.reci;
    if isfield(inputStruct, 'veci') && ~isempty(inputStruct.veci)
        veci = inputStruct.veci;
    else
        veci = zeros(size(reci)); % Vettore nullo se la velocità non è fornita
    end
end

%% Main loop
for i = 1:length(times)
    t = datevec(times(i));
    [jdut1,jdut1frac,ttt] = convtime(t(1),t(2),t(3),t(4),t(5),t(6),0,eop.dut1,eop.dat);
    
    % Se non abbiamo i dati esterni, propaghiamo l'orbita con SGP4
    if ~useInputReci
        epochsgp4 = juliandate(times(i));
        tsince    = (epochsgp4 - epochtle)*1440;
        % Propagation
        [~, rteme, vteme] = sgp4(satrec, tsince);
        % eci
        [reci(i,:), veci(i,:), ~] = teme2eci(rteme',vteme', 0, ttt, eop.ddpsi, eop.ddeps, nutParams);
    end
    
    % Geodetic
    if getGeodetic || getEcef
        % ecef
        [recef(i,:),vecef(i,:),~] = eci2ecef(reci(i,:)',veci(i,:)',0,ttt,jdut1+jdut1frac,eop.lod,eop.xp,eop.yp,2,eop.ddpsi,eop.ddeps,nutParams);
        % lla
        [~,latgd_sat(i,:),lon_sat(i,:),~] = ecef2ll(recef(i,:)');
    end
    
    % AZEL
    if getVisibility || getAzEl
        [~,az_,el_,~,~,~,rs,vs] = rv2razel(reci(i,:)', veci(i,:)', lat_gs, lon_gs, alt_gs, ttt, jdut1+jdut1frac, eop.lod, eop.xp, eop.yp, 2, eop.ddpsi, eop.ddeps, nutParams);
        el(i) = el_*180/pi;
        az(i) = az_*180/pi;
    end
    
    % RADEC
    if getRaDec
        [~,ra_,dec_,~,~,~] = rv2tradc (reci(i,:)', veci(i,:)', lat_gs, lon_gs, alt_gs, ttt, jdut1+jdut1frac, eop.lod, eop.xp, eop.yp, eop.ddpsi, eop.ddeps, nutParams);
        ra(i)  = ra_*180/pi;
        dec(i) = dec_*180/pi;
    end
    
    % Sun
    if getSun || getVisibility || getSunRange
        [~,~,MJD_TDB]  = barycentric_dynamical_time(times(i));
        [rsun(i,:), ~] = JPL_Eph_DE440(MJD_TDB,DE440Coeff);
        lit            = sight(rsun(i,:),reci(i,:));
    end
     
    % Sun geodetic
    if getSun && getSunGeodetic
        [recefs,~,~]                      = eci2ecef(rsun(i,:)',0,0,ttt,jdut1+jdut1frac,eop.lod,eop.xp,eop.yp,2,eop.ddpsi,eop.ddeps,nutParams);
        [~,latgd_sun(i,:),lon_sun(i,:),~] = ecef2ll(recefs);
    end
    
    % Observatory
    if getObs || getRange
        % Se usiamo dati esterni rseci viene ricavata rigenerando le coordinate della stazione rs
        if useInputReci && (~getVisibility && ~getAzEl)
            [~,~,~,~,~,~,rs,vs] = rv2razel(reci(i,:)', veci(i,:)', lat_gs, lon_gs, alt_gs, ttt, jdut1+jdut1frac, eop.lod, eop.xp, eop.yp, 2, eop.ddpsi, eop.ddeps, nutParams);
        end
        [rseci(i,:),~] = ecef2eci(rs, vs, ttt, jdut1+jdut1frac , eop.lod, eop.xp, eop.yp, 2, eop.ddpsi, eop.ddeps, nutParams);
    end
    
    % Range
    if getRange
        r(i) = norm(reci(i,:)-rseci(i,:));
    end
    
    % Sun range
    if getSunRange
        s(i) = norm(reci(i,:)-rsun(i,:));
    end
    
    % Visibility
    if getVisibility
        if el(i) > mask && lit
            access(i) = 1;
        end
    end
   
end

if getVisibility && ~all(access)
    warning("Object is not visible at some moments")
end

%% Pack output
if getGeodetic
    out.lonObj = lon_sat;
    out.latObj = latgd_sat;
end
if getSunGeodetic
    out.lonSun = lon_sun;
    out.latSun = latgd_sun;
end
if getVisibility
    out.access = access;
end
if getAzEl
    out.Az = az;
    out.El = el;
end
if getRaDec
    out.RA  = ra;
    out.Dec = dec;
end
if getRange
    out.r  = r;
end
if getSunRange
    out.s  = s;
end
        
if getSun
    out.rsun  = rsun;
end
if getObs
    out.rseci  = rseci;
end
if getEcef
    out.recef  = recef;
    out.vecef  = vecef;
end
out.reci = reci;
out.veci = veci;
end
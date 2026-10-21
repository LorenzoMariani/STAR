clear, clc, close all
%% generateCSVunity ----------------------------------------------------- %
% Generate input csv file for unity light curve simulator. The CSV file
% contains N lines where N is the number of epochs. At each epoch the
% object, observer and sun positions are computed in km in ECI. These
% ephemerides can be either generated or retrieved by exisiting ones
% (OEMs). Also the satellite attitude is computed, either propagated or via
% ephemeris (PROQUA or OEM). Additional information like sun-obj range,
% obj-obs range and obj elevation is provided. Support for multi latitude
% simulations can be enabled
% ----------------------------------------------------------------------- %

%% INPUT
debug = true;

% Set environment: lib/ di END-010, da qualunque cartella si lanci lo script
parentDir = fileparts(mfilename('fullpath'));
addpath(genpath(parentDir));
dataFiles = {fullfile(parentDir,'sgp4','nut80.dat'), fullfile(parentDir,'data','DE440.mat')};

for f = dataFiles
    if ~exist(f{1},'file')
        error('generateCSVunity: Required file not found: %s.', f{1});
    end
    load(f{1});
end

[iar80, rar80]  = iau80in(nut80);
nutParams.iar80 = iar80;
nutParams.rar80 = rar80;

ii = 11;

% Files
eopfile     = fullfile(parentDir, "data", "EOP.txt");
tlefile     = fullfile(parentDir, "data", "TLE_AQUA27052026.txt");
pathjson    = fullfile(parentDir, "data", "stations.json");

% Output: la cartella Output di STAR
outF        = fullfile(fileparts(fileparts(parentDir)), "Output");
if ~isfolder(outF), mkdir(outF); end

% Enable ephemeris
orbitEphemeris = false;
sunEphemeris   = false;
attEphemeris   = false;
obsEphemeris   = false;
timeList       = true;
extendTime     = false;
spaceBased     = false;

howMany = 2;

% Station
mask        = 10;
observatory = "SCUDO";
[lat, lon, alt, city] = readStationFile(pathjson,observatory);
lla = [lat*pi/180, lon*pi/180, alt*1e-3];

% Time - UTC
delta    = 1;
duration = 180;
start    = "2026-05-27T02:59:47";
times_   = string;
tsim  = 0:delta:duration-1;
len   = length(tsim);
times = NaT(1,len);
for i = 1:len
    times(i) = datetime(start) + seconds(tsim(i));
    times_(i) = datestr(times(i),'yyyy-mm-ddTHH:MM:SS');
end


% Set propagator
inputStruct.getGeodetic     = true;
inputStruct.getVisibility   = true;
inputStruct.getAzEl         = true;
inputStruct.getRaDec        = true;
inputStruct.getRange        = true;
inputStruct.getSunRange     = true;
inputStruct.getEcef         = true;
inputStruct.getSunGeodetic  = true;
inputStruct.getSun          = true;
inputStruct.getObs          = true;

inputStruct.times           = times;
inputStruct.tlefile         = tlefile;
inputStruct.eopfile         = eopfile;
inputStruct.mask            = mask;
inputStruct.lla             = lla;

inputStruct.DE440Coeff      = DE440Coeff;
inputStruct.nutParams       = nutParams;

%% Orbit-Sun-Observatory-Attitude
if ~orbitEphemeris || ~sunEphemeris || ~obsEphemeris || ~attEphemeris
    out = propagation(inputStruct);
    reci  = out.reci;
    rseci = out.rseci;
    rsun  = out.rsun;
    r     = out.r;
    s     = out.s;
    e     = out.El;
end

if ~attEphemeris
    % Initial conditions
    q0 = [1, 0.0, 0.0, 0.0];
    q0 = q0/norm(q0);
    w0 = [0.0, 0.1, 0.0];
    att0 = [q0 w0];
    att0 = att0(:);
    % Propagation
    I = [41815, 0, 0; 0, 41815, 0; 0, 0, 6570];
    att = propAttitude(att0, tsim, I);
end

%% Use external ephemeris if available

% Orbit
if orbitEphemeris
    [file, path]  = uigetfile(pwd, 'Select object OEM');
    filepath      = fullfile(path,file);
    [newtimes, reci] = readOEM(filepath, times);
end
% Sun
if sunEphemeris
    [file, path]  = uigetfile(pwd, 'Select Sun OEM');
    filepath      = fullfile(path,file);
    [newtimes, rsun] = readOEM(filepath, times);
end
% Observatory
if obsEphemeris
    [file, path]   = uigetfile(pwd, 'Select observatory OEM');
    filepath       = fullfile(path,file);
    [newtimes, rseci] = readOEM(filepath, times);
end
% Attitude
if attEphemeris
    [file, path] = uigetfile(pwd, 'Select attitude DBL, OEM or CSV');
    filepath     = fullfile(path,file);
    if endsWith(filepath,'.DBL')
        times = times + seconds(18);
        att   = readPROQUA(filepath, times);
    elseif endsWith(filepath,'.txt')
        [newtimes, att]  = readOEM(filepath, times);
    elseif endsWith(filepath,'.csv')
        tmp  = readmatrix(filepath);
        att  = tmp(:,2:end);
    end
end

csv_lines = [times_(:), reci, rseci, rsun, e(:), r(:), s(:), att(:,1:4)];

outfile = fullfile(outF,sprintf('csvUnity.csv'));
writematrix(csv_lines, outfile)

reciUnity  = [reci(:,1), reci(:,3), reci(:,2)];
rsunUnity  = [rsun(:,1), rsun(:,3), rsun(:,2)];
rseciUnity = [rseci(:,1), rseci(:,3), rseci(:,2)];

if debug

    lonSun  = out.lonSun;
    latSun  = out.latSun;
    lonObj  = out.lonObj;
    latObj  = out.latObj;

    for i = 1:size(reci,1)
        % Phase angle right/left handed
        objSun = rsun(i,:) - reci(i,:);
        objSun = objSun/norm(objSun);
        objObs = rseci(i,:) - reci(i,:);
        objObs = objObs/norm(objObs);
        dotP = dot(objSun,objObs);
        phaseAngleEci(i) = acosd(dotP);
        objSun = rsunUnity(i,:) - reciUnity(i,:);
        objSun = objSun/norm(objSun);
        objObs = rseciUnity(i,:) - reciUnity(i,:);
        objObs = objObs/norm(objObs);
        dotP = dot(objSun,objObs);
        phaseAngleUnity(i) = acosd(dotP);
        % Cam angle
        camSun = (rsun(i,:) - rseci(i,:))/norm(rsun(i,:) - rseci(i,:));
        camObj = (reci(i,:) - rseci(i,:))/norm(reci(i,:) - rseci(i,:));
        camAng(i) = acosd(dot(camSun,camObj));
        reci(i,:)  = (reci(i,:) - rseci(i,:))/norm(reci(i,:) - rseci(i,:));
        rsun(i,:)  = (rsun(i,:) - rseci(i,:))/norm(rsun(i,:) - rseci(i,:));
        rseci(i,:) = [0,0,0];
        camSun = rsun(i,:);
        camObj = reci(i,:);
        camAngTrasl(i) = acosd(dot(camSun,camObj));
        camSun = (camSun/100)/norm(camSun/100);
        camObj = (camObj/100)/norm(camSun/100);
        camAngTraslNorm(i) = acosd(dot(camSun,camObj));

    end
    figure(1)
    plot(phaseAngleUnity)
    figure(2)
    plot(phaseAngleEci)
    figure(3)
    geoshow('landareas.shp','FaceColor','white')
    hold on
    plot(lonSun(1)*180/pi, latSun(1)*180/pi, 'o','MarkerfaceColor','r', 'MarkerSize',15)
    hold on
    plot(lonObj*180/pi, latObj*180/pi, '*', 'MarkerSize',10)
    hold on
    plot(lon, lat, 'o','MarkerfaceColor','b',  'MarkerSize',15)
    xlabel("Lon")
    ylabel("Lat")
    figure(4)
    plot(camAng)
    figure(5)
    plot(camAngTrasl)
    figure(6)
    plot(camAngTraslNorm)
end
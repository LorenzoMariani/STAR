%% Help ----------------------------------------------------------------- %
% Get the input observatory geodetic coordinates longitude latitude and 
% altitude in degrees an meters
%
% Input:  observatory - [string 1x1] - station name
%         filename    - [string 1x1] - path to json file
%
% Output: lat         - [double 1x1] - station WGS84 latitude in deg
%         lon         - [double 1x1] - station WGS84 longitude in deg
%         alt         - [double 1x1] - station WGS84 altitude in m
%         city        - [string 1x1] - station closest city
% ----------------------------------------------------------------------- %
function [lat, lon, alt, city] = readStationFile(filename,observatory)

if ~exist(filename, 'file')
    error("File at %s doesn't exist", filename);
end
% Read JSON file
jsonData = fileread(filename);
% Parse JSON
data = jsondecode(jsonData);

% Check if the observatory exists in the JSON
if isfield(data, observatory)
    lat = data.(observatory).lat;
    lon = data.(observatory).lon;
    alt = data.(observatory).alt;
    city = data.(observatory).city;
else
    error('generateCSVunity::getstation: Observatory not found in JSON data.');
end
end
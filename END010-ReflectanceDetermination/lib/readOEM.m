%% Help ----------------------------------------------------------------- %
% Read CCSDS OEM files and output times and data. If an array of datetime
% is provided as input it interpolates the collected data at given times
%
% Input:  filename - [string 1x1]   - path to OEM file
%         t        - [datetime Nx1] - optional, interpolation times
%
% OUTPUT: times    - [datetime Nx1] - Nx1 array of times
%         data     - [double Nx3]   - Nx3 array of data
%
% ----------------------------------------------------------------------- %
function [times, data] = readOEM(filename, varargin)

if nargin > 1
    t = varargin{1};
elseif nargin > 2
    error("readOEM: too many arguments, no more than two are allowed.");
end

fid = fopen(filename,'r');
if fid == -1
    error(':readOEM: FileOpen Cannot open file "%s".', filename);
end

% Skip everything until the metadata terminator
while true
    ln = fgetl(fid);
    if ~ischar(ln)
        fclose(fid);
        error('readOEM: bad file, META_STOP not found before end of file.');
    end
    if contains(ln, 'META_STOP')
        break
    end
end

% Read the epoch line
fmt = '%s %f %f %f %f %f %f';
C   = textscan(fid, fmt, 'CollectOutput', true);
fclose(fid);

rawTime = C{1};
state   = C{2};          

% Remove any blank lines the scan may have read
valid   = ~cellfun('isempty', rawTime);
rawTime = rawTime(valid);
state   = state(valid, :);

% Convert the ISO strings to datetime
if isempty(rawTime)
    error('readOEM: times array is empty.');
else
    fmt   = 'yyyy-MM-dd''T''HH:mm:ss.SSSSSS';
    times = datetime(rawTime, 'InputFormat', fmt);
end

if exist('t','var')
    
    % Check that start time is before end time
    if t(end) <= t(1)
        error('generateCSVunity::readOEM: end time must be after start time.');
    end

    % Check that start time and end time are within bounds
    if t(1) < min(times) || t(end) > max(times)
        error('generateCSVunity::readOEM: start time and/or end time are outside the times range.');
    end

    % Extract data
    data_ = state(:, any(~isnan(state), 1));
    data  = zeros(numel(t),size(data_,2));
    % Interpolate if necessary
    for i = 1:size(data_,2)
        data(:,i) = interp1(times, data_(:,i), t);
    end
else
    data = state(:, any(~isnan(state), 1));
end

debug = false;
if debug
    figure
    plot(times,data_(:,1),times,data_(:,2),times,data_(:,3))
    hold on
    plot(t,data(:,1),'o',t,data(:,2),'o',t,data(:,3),'o')
    grid on
    grid minor
    legend('X','Y','Z')
end
end

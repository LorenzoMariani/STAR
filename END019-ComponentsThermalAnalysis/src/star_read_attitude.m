function att = star_read_attitude(csvfile, sim_start, convention)
% STAR_READ_ATTITUDE  Legge un CSV di assetto di END-003 (pos ECI + quaternione).
%   convention: 'body2eci' (default; output_attitude_propagation_ECI.csv) oppure
%   'eci2body' (output_attitude_propagation.csv, il file per Unreal: coniugato).
%   att.quat e' sempre body->ECI [w x y z].
if nargin < 3 || isempty(convention), convention = 'body2eci'; end
T = readtable(csvfile,'TextType','string','Delimiter',',');
fmt = 'yyyy-MM-dd''T''HH:mm:ss''Z''';
att.t_utc = datetime(T.timestamp_utc,'InputFormat',fmt,'TimeZone','UTC');
att.tsec  = seconds(att.t_utc - sim_start);
att.eci   = [T.eci_x_km T.eci_y_km T.eci_z_km]*1000;   % [m]
att.quat  = [T.q_w T.q_x T.q_y T.q_z];                  % [w x y z]
if strcmpi(convention, 'eci2body')
    att.quat(:, 2:4) = -att.quat(:, 2:4);              % coniugato: body->ECI
end
att.nadir_offset = T.nadir_offset_deg;
end

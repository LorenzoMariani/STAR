function att = star_read_attitude(csvfile, sim_start)
% STAR_READ_ATTITUDE  Legge output_attitude_propagation.csv (pos ECI + quaternione).
T = readtable(csvfile,'TextType','string','Delimiter',',');
fmt = 'yyyy-MM-dd''T''HH:mm:ss''Z''';
att.t_utc = datetime(T.timestamp_utc,'InputFormat',fmt,'TimeZone','UTC');
att.tsec  = seconds(att.t_utc - sim_start);
att.eci   = [T.eci_x_km T.eci_y_km T.eci_z_km]*1000;   % [m]
att.quat  = [T.q_w T.q_x T.q_y T.q_z];                  % body->ECI [w x y z]
att.nadir_offset = T.nadir_offset_deg;
end

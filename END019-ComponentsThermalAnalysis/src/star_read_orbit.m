function orb = star_read_orbit(jsonfile)
% STAR_READ_ORBIT  Legge un satellite_XX.json (constellation_optimizer).
s = jsondecode(fileread(jsonfile));
orb.alt       = (s.orbit.alt_perigee_m + s.orbit.alt_apogee_m)/2;   % [m] (circolare)
orb.incl      = s.orbit.inclination_deg;
orb.raan      = s.orbit.raan_deg;
orb.omega     = s.orbit.omega_deg;
orb.nu        = s.orbit.nu_deg;
orb.start     = datetime(s.sim_start_date,'InputFormat','yyyy-MM-dd HH:mm:ss','TimeZone','UTC');
orb.sim_hours = s.sim_hours;
[~,nm] = fileparts(jsonfile);
orb.source = [nm '.json'];
% indice satellite dal nome file (satellite_01 -> 1), fallback 1
tok = regexp(nm,'(\d+)','tokens','once');
if ~isempty(tok), orb.index = str2double(tok{1}); else, orb.index = 1; end
end
